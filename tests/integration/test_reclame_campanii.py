"""F13.4 — constructorul de campanii, propunerile de schimbare și executorul (I2). „Gata când”: o campanie de
probă apare în pauză pe contul agenției, iar o schimbare aplicată se poate anula dintr-o atingere. Platformele
sunt SIMULATE (# SIMULAT)."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.connectors.contract import Token
from app.connectors.publicare.baza import DepozitInMemorie
from app.connectors.reclame.google import CANAL_TOKEN as TOKEN_GOOGLE
from app.conturi import Rol
from app.db import sesiune_agentie
from app.reclame import Campanie, Propunere, constructor, propuneri
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti, om  # noqa: F401
from tests.integration.utile_reclame import (  # noqa: F401
    AZI,
    autorizeaza,
    construieste,
    cont_agentie,
    depozit,
    executa_efecte,
    google,
    meta,
)
from tests.platforme.google_ads import GoogleAdsSimulat
from tests.platforme.meta_ads import MarketingSimulat

pytestmark = pytest.mark.db
Fabrica = Callable[..., tuple[uuid.UUID, uuid.UUID]]


def campanie(cid: uuid.UUID) -> Campanie:
    with sesiune_agentie() as db:
        c = db.get(Campanie, cid)
        assert c is not None
        db.expunge(c)
        return c


def test_campania_apare_in_pauza_si_o_schimbare_se_anuleaza_dintr_o_atingere(
    meta: MarketingSimulat,
    depozit: DepozitInMemorie,
    cont_agentie: Fabrica,
    om: uuid.UUID,
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
) -> None:
    tenant, cont_id = cont_agentie()
    autorizeaza(depozit, meta, tenant)
    meta.injecteaza("pierde_raspunsul")  # prima creare ajunge la platformă, dar răspunsul se pierde
    scalare, test = construieste(cont_id, om)
    executa_efecte()  # reîncercarea găsește campania după nume: nu o dublează
    assert len(meta.campanii()) == 2 and {c["status"] for c in meta.campanii()} == {"PAUSED"}
    s = campanie(scalare)
    assert s.stare == "in_pauza" and s.id_extern in meta.obiecte
    assert len(meta.reclame(campanie(test).id_extern)) == 3, "o reclamă pe variantă"
    assert "utm_source=meta" in meta.reclame(s.id_extern)[0]["creative"]["link_url"]
    meta.zi(AZI)
    assert meta.manager(AZI, AZI)["bani"] == 0, "în pauză nu se cheltuie nimic"

    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    h = client.get(f"/reclame/cont/{cont_id}").text
    assert f'data-campanie-id="{scalare}" data-stare="in_pauza"' in h
    r = client.post(
        f"/reclame/campanie/{scalare}/activeaza", data={"csrf_token": csrf(client)}, follow_redirects=False
    )
    assert r.status_code == 303
    executa_efecte()
    assert meta.obiecte[s.id_extern]["status"] == "ACTIVE" and campanie(scalare).stare == "activa"

    with sesiune_agentie() as db:  # o schimbare de buget, aprobată de om
        p = propuneri.propune(
            db,
            scalare,
            "buget",
            {"buget_zilnic_bani": 7_000},
            motiv="Rezultate bune",
            sursa="om",
            utilizator_id=om,
        )
        propuneri.aproba(db, p.id, utilizator_id=om)
        pid = p.id
    executa_efecte()
    assert meta.obiecte[s.id_extern]["daily_budget"] == 7_000
    with sesiune_agentie() as db:
        pr = db.get(Propunere, pid)
        assert pr is not None and pr.stare == "aplicata"
        assert pr.inainte == {"stare": "activa", "buget_zilnic_bani": 6_400} and pr.dupa == {
            "buget_zilnic_bani": 7_000
        }

    h = client.get(f"/reclame/cont/{cont_id}").text
    assert f'action="/reclame/propunere/{pid}/anuleaza"' in h
    r = client.post(
        f"/reclame/propunere/{pid}/anuleaza", data={"csrf_token": csrf(client)}, follow_redirects=False
    )
    assert "mesaj=propunere_anuleaza" in r.headers["location"]
    executa_efecte()
    assert meta.obiecte[s.id_extern]["daily_budget"] == 6_400 and campanie(scalare).buget_zilnic_bani == 6_400
    with sesiune_agentie() as db:
        [inv] = db.execute(select(Propunere).where(Propunere.anuleaza_id == pid)).scalars()
        assert inv.stare == "aplicata" and inv.sursa == "anulare"
        with pytest.raises(propuneri.PropunereRefuzata, match="deja anulată"):
            propuneri.anuleaza(db, pid, utilizator_id=om)
    assert "Anulare: Rezultate bune" in client.get(f"/reclame/cont/{cont_id}").text


def test_campania_google_se_creeaza_in_pauza_si_se_poate_pune_pe_pauza(
    google: GoogleAdsSimulat, depozit: DepozitInMemorie, cont_agentie: Fabrica, om: uuid.UUID
) -> None:
    tenant, cont_id = cont_agentie("google", "1234567890")
    depozit.pune(tenant, TOKEN_GOOGLE, Token(acces=google.token_nou("ya29")))
    scalare, _ = construieste(cont_id, om)
    c = campanie(scalare)
    assert c.stare == "in_pauza" and google.campanii_[c.id_extern]["status"] == "PAUSED"  # type: ignore[index]
    assert google.buget_bani(c.id_extern) == 6_400  # type: ignore[arg-type]
    with sesiune_agentie() as db:
        for dupa in ({"stare": "activa"}, {"buget_zilnic_bani": 5_000}):
            p = propuneri.propune(
                db, scalare, "stare" if "stare" in dupa else "buget", dupa, motiv="Probă", sursa="om"
            )
            propuneri.aproba(db, p.id, utilizator_id=om)
    executa_efecte()
    assert google.campanii_[c.id_extern]["status"] == "ENABLED" and google.buget_bani(c.id_extern) == 5_000  # type: ignore[index,arg-type]


def test_constructorul_cere_plan_aprobat(cont_agentie: Fabrica, om: uuid.UUID) -> None:
    from app.reclame import plan
    from tests.integration.utile_reclame import PARAMETRI_PLAN, creative

    _, cont_id = cont_agentie()
    with sesiune_agentie() as db:
        r = plan.propune(db, cont_id, **PARAMETRI_PLAN)
        with pytest.raises(constructor.ConstructieRefuzata, match="plan aprobat"):
            constructor.construieste(db, r.id, creative(r.id))  # type: ignore[arg-type]


def test_fara_conector_efectul_esueaza_si_campania_ramane_neconstruita(
    cont_agentie: Fabrica, om: uuid.UUID
) -> None:
    _, cont_id = cont_agentie()
    scalare, _ = construieste(cont_id, om)
    assert campanie(scalare).stare == "esuata" and campanie(scalare).id_extern is None
