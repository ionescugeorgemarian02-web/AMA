"""F6.8 — proba de două săptămâni, ACCELERATĂ (# SIMULAT). „Gata când”: trec 14 zile fără incident critic și rata de aprobare
din prima este măsurată. Două branduri proprii FICTIVE (amândouă pe materialele „Cafeneaua Zorilor”), la L1, modele FALSE,
omul care decide și publică e simulat; zilele urmează ceasul calendarului (nu se așteaptă). Proba pe conținut real: la
migrare."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable
from types import SimpleNamespace

import pytest

from app import continut, productie, publicare
from app.continut import proba
from app.db import sesiune_tenant
from app.productie import Stare
from tests.continut_utile import calendar_valid, model_brief, model_postari, model_scripturi
from tests.integration.lant_continut import INCEPUT, calendar_aprobat, fara_cereri_ramase  # noqa: F401
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele  # noqa: F401

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fara_cereri_ramase")]
ZILNIC = calendar_valid(
    formate=[
        {"canal": "facebook", "tip": "postare", "pe_saptamana": 7},
        {"canal": "facebook", "tip": "script_video_scurt", "pe_saptamana": 1},
    ]
)
EDITAT = (
    "Știi ce înseamnă data prăjirii?\n\nLa Cafeneaua Zorilor prăjim cafeaua în loturi mici, cu data scrisă pe "
    "pachet. Comandă acum din magazinul online."
)


def decident(_db: object, _ap: productie.Aprobare, lv: productie.Livrabil, n: int) -> proba.Decizie:
    """Omul simulat: respinge una din șase (hook slab), editează câte o postare din zece, aprobă restul."""
    if n % 6 == 0:
        return proba.Decizie("respinge", motiv_standard="hook_slab", motiv="Prea general pentru ziua asta")
    if n % 10 == 7 and lv.tip == "postare":
        return proba.Decizie("editeaza", text=EDITAT)
    return proba.Decizie("aproba")


def test_paisprezece_zile_fara_incident_critic_cu_rata_de_aprobare_din_prima_masurata(
    fabrica_clienti: Callable[[], uuid.UUID],
    tenant: uuid.UUID,
    om: uuid.UUID,
    modele: ModelFals,
    executor: None,
) -> None:
    al_doilea = fabrica_clienti()
    branduri = []
    for t in (tenant, al_doilea):
        cal, _ = calendar_aprobat(t, om, modele, calendar=ZILNIC)
        with sesiune_tenant(t) as db:
            assert productie.autonomie.nivel(db, t, productie.Clasa.PUBLICARE_CONTINUT) == productie.Nivel.L1
        branduri.append((t, cal))
    model_brief(modele)
    model_postari(modele, stricate={4, 15})  # două postări ies stricate și se repară în validare
    model_scripturi(modele)
    r = proba.ruleaza(
        branduri, om=om, inceput=INCEPUT, decident=decident,
        publicator=lambda p, n: f"https://www.facebook.com/zorilor/posts/{n}",
    )  # fmt: skip
    assert r.zile == 14 and len(r.pe_zi) == 14
    assert all(z["produse"] >= 2 for z in r.pe_zi), r.pe_zi  # zilnic, pentru amândouă brandurile
    assert r.incidente_critice == [], r.incidente_critice
    assert r.produse == r.decise >= 28 and r.respinse >= 4 and r.editate >= 1
    assert r.rata_aprobare_din_prima is not None and 0.5 < r.rata_aprobare_din_prima < 1
    assert r.publicate == r.decise - r.respinse  # tot ce a aprobat omul s-a publicat, cu link
    for t, cal in branduri:
        with sesiune_tenant(t) as db:
            for i in continut.calendar.intrari(db, cal):
                lv = productie.citeste(db, i.livrabil_id)  # type: ignore[arg-type]
                assert lv is not None
                zi = (i.slot_la.astimezone(continut.calendar.FUS).date() - INCEPUT).days
                if zi >= 14:
                    assert lv.stare == Stare.PLANIFICAT.value  # în afara ferestrei nu s-a produs nimic
                elif lv.stare == Stare.PUBLICAT.value:
                    [p] = [x for x in publicare.asistata.ale_livrabilului(db, lv.id) if x.stare == "publicat"]
                    assert p.link and proba.verifica_publicarea(db, lv.id) == []
                else:
                    assert lv.stare == Stare.RESPINS.value


def test_verificarea_prinde_publicarile_ilegitime(tenant: uuid.UUID, monkeypatch: pytest.MonkeyPatch) -> None:
    """Drumul ilegitim spre „publicat” e refuzat de producție; iar dacă ar exista, verificarea probei îl semnalează."""
    with sesiune_tenant(tenant) as db:
        lid = productie.creeaza(db, tenant_id=tenant, tip="postare", canal="facebook").id
        s = Stare.PLANIFICAT
        for x in (Stare.BRIEFAT, Stare.IN_SCRIERE, Stare.IN_VALIDARE, Stare.VALIDAT):
            productie.muta(db, lid, s, x, componenta="test")
            s = x
        with pytest.raises(productie.TranzitieNepermisa, match="cere o aprobare"):
            productie.muta(db, lid, Stare.VALIDAT, Stare.APROBAT, componenta="test")
    pachet = SimpleNamespace(stare="publicat", versiune=1)
    monkeypatch.setattr(productie, "citeste", lambda _db, _id: SimpleNamespace(stare="publicat"))
    monkeypatch.setattr(publicare.asistata, "ale_livrabilului", lambda _db, _id: [pachet, pachet])
    monkeypatch.setattr(
        proba.validare, "rulari", lambda _db, _id: [SimpleNamespace(versiune=1, decizie="reparatie")]
    )
    monkeypatch.setattr(productie.aprobari, "ale_livrabilului", lambda _db, _id: [])
    probleme = proba.verifica_publicarea(None, lid)  # type: ignore[arg-type]
    assert [p.split(": ", 1)[1] for p in probleme] == [
        "aceeași versiune publicată de două ori",
        "versiunea 1 publicată fără validare trecută",
        "versiunea 1 publicată fără aprobarea unui om",
        "versiunea 1 publicată fără validare trecută",
        "versiunea 1 publicată fără aprobarea unui om",
    ]
