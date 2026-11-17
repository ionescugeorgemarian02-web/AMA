"""F13.5 — gardianul de buget și oprirea de urgență. „Gata când”: o propunere peste plafon este refuzată, iar o
anomalie simulată pune totul pe pauză și te anunță. Platforma e SIMULATĂ (# SIMULAT)."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.connectors.publicare.baza import DepozitInMemorie
from app.conturi import Rol
from app.db import sesiune_agentie
from app.operare import opriri
from app.operare.notificari import Nivel
from app.reclame import Campanie, propuneri, rezultate, urgenta
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import AnunturiFalse, anunturi, fabrica_clienti, om  # noqa: F401
from tests.integration.utile_reclame import (  # noqa: F401
    ACUM,
    AZI,
    PAGINI,
    autorizeaza,
    construieste,
    cont_agentie,
    depozit,
    executa_efecte,
    meta,
)
from tests.platforme.meta_ads import MarketingSimulat

pytestmark = pytest.mark.db
Fabrica = Callable[..., tuple[uuid.UUID, uuid.UUID]]


def activeaza(cid: uuid.UUID, om: uuid.UUID) -> None:
    with sesiune_agentie() as db:
        p = propuneri.propune(
            db, cid, "stare", {"stare": "activa"}, motiv="Pornire", sursa="om", utilizator_id=om
        )
        propuneri.aproba(db, p.id, utilizator_id=om)
    executa_efecte()


def stare(cid: uuid.UUID) -> str:
    with sesiune_agentie() as db:
        c = db.get(Campanie, cid)
        assert c is not None
        return c.stare


def test_propunerea_peste_plafon_e_refuzata_si_anomalia_opreste_tot(
    meta: MarketingSimulat,
    depozit: DepozitInMemorie,
    cont_agentie: Fabrica,
    om: uuid.UUID,
    anunturi: AnunturiFalse,
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
) -> None:
    tenant, cont_id = cont_agentie()
    autorizeaza(depozit, meta, tenant)
    scalare, test = construieste(cont_id, om)
    activeaza(scalare, om)
    activeaza(test, om)
    externe = [meta.obiecte[c["id"]]["id"] for c in meta.campanii()]

    with sesiune_agentie() as db:  # 8.000 + 1.600 active; plafonul pe campanie e 8.000
        p = propuneri.propune(
            db, scalare, "buget", {"buget_zilnic_bani": 9_000}, motiv="Mai mult", sursa="strateg"
        )
        assert p.stare == "refuzata" and p.verdict["cere_client"]
        assert any("plafonul pe campanie" in m for m in p.verdict["motive"])
        with pytest.raises(propuneri.PropunereRefuzata):
            propuneri.aproba(db, p.id)
    assert all(meta.obiecte[e]["daily_budget"] != 9_000 for e in externe), "nimic peste plafon la platformă"

    # anomalie: platforma cheltuie azi de patru ori bugetul (o buclă de licitare scăpată)
    meta.zi(AZI, ritm=4.0)
    rezultate.citeste_cont(cont_id, ACUM)
    gasite = urgenta.supravegheaza(ACUM)
    assert [a.cod for a in gasite] == ["ritm"]
    executa_efecte()
    assert {c["status"] for c in meta.campanii()} == {"PAUSED"}, "totul pe pauză la platformă"
    assert stare(scalare) == stare(test) == "in_pauza"
    assert anunturi.nivele() == [Nivel.CRITIC] and "oprite" in anunturi.titluri()[0]
    with sesiune_agentie() as db:
        assert opriri.este_oprit(db, opriri.Oprire.RECLAME)
        # cât timp e oprit, nimic nu pornește; după repornire, campaniile rămân în pauză (repornire manuală)
        p = propuneri.propune(db, scalare, "stare", {"stare": "activa"}, motiv="Repornesc", sursa="om")
        assert p.stare == "refuzata" and "repornirea e manuală" in p.verdict["motive"][0]
    urgenta.supravegheaza(ACUM + dt.timedelta(hours=1))
    assert len(anunturi.trimise) == 1, "nu anunță de două ori aceeași oprire"

    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    h = client.get(f"/reclame/cont/{cont_id}").text
    assert "Oprire de urgență: cheltuiala de azi depășește" in h and "refuzata" in h
    with sesiune_agentie() as db:
        opriri.seteaza(db, opriri.Oprire.RECLAME, False, canal="panou", motiv="verificat", utilizator_id=om)
    assert stare(scalare) == "in_pauza"
    r = client.post(
        f"/reclame/campanie/{scalare}/activeaza", data={"csrf_token": csrf(client)}, follow_redirects=False
    )
    assert "mesaj=campanie_activeaza" in r.headers["location"]
    executa_efecte()
    assert stare(scalare) == "activa"


@pytest.mark.parametrize("semnal", ["urmarire", "cont", "pagina", "autentificare"])
def test_celelalte_semnale_opresc_si_ele(
    semnal: str,
    meta: MarketingSimulat,
    depozit: DepozitInMemorie,
    cont_agentie: Fabrica,
    om: uuid.UUID,
    anunturi: AnunturiFalse,
) -> None:
    tenant, cont_id = cont_agentie()
    autorizeaza(depozit, meta, tenant)
    scalare, _ = construieste(cont_id, om)
    activeaza(scalare, om)
    for i in range(2, 8):
        meta.zi(AZI - dt.timedelta(days=i))
    if semnal == "urmarire":
        meta.zi(AZI - dt.timedelta(days=1), conversie=0.0, ctr=0.03)
    elif semnal == "cont":
        meta.stare_cont = 3
    elif semnal == "pagina":
        PAGINI["https://agentie.example/audit"] = False
    else:
        depozit.tokenuri.clear()
    try:
        rezultate.citeste_cont(cont_id, ACUM)
        assert {a.cod for a in urgenta.supravegheaza(ACUM)} == {semnal}
    finally:
        PAGINI.clear()
    executa_efecte()
    assert anunturi.nivele() == [Nivel.CRITIC]
    if semnal == "autentificare":  # fără token, nici pauza nu poate pleca: anunțul cere oprirea manuală
        assert "managerul de reclame" in anunturi.trimise[0][2]
        with sesiune_agentie() as db:
            [p] = [x for x in propuneri.ale_campaniei(db, scalare) if x.sursa == "urgenta"]
            assert p.stare == "esuata"
    else:
        assert stare(scalare) == "in_pauza"
