"""F9.7 — planificarea, alegerea canalelor și zilele blocate (D4). „Gata când”: o postare programată pleacă
la minut, iar pauza de criză oprește tot. Ceasul e controlat (fără așteptări reale); platforma e FALSĂ (#
SIMULAT)."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Iterator

import pytest

from app import productie, publicare, validare
from app.connectors import registru
from app.connectors.publicare import DepozitBaza
from app.connectors.publicare.fals import ConectorFalsPublicare, PlatformaFalsa
from app.conturi import Rol
from app.db import sesiune_agentie, sesiune_tenant
from app.operare import efecte, opriri
from app.productie import Hotarare
from app.productie.stari import Stare
from app.publicare import programare
from tests.integration.publicare_utile import autorizeaza, livrabil_stare
from tests.integration.utile_productie import fabrica_clienti, livrabil, muta, om, tenant  # noqa: F401

pytestmark = pytest.mark.db
TZ = programare.TZ


def local(zi: int, ora: int, minut: int = 0) -> dt.datetime:
    return dt.datetime(2026, 11, zi, ora, minut, tzinfo=TZ).astimezone(dt.UTC)


@pytest.fixture
def platforma() -> Iterator[PlatformaFalsa]:
    registru.uita_tot()
    p = PlatformaFalsa()
    registru.inregistreaza("facebook", ConectorFalsPublicare(p, DepozitBaza(), canal="facebook"))
    yield p
    registru.uita_tot()


def aprobat(tenant: uuid.UUID, om: uuid.UUID, text: str) -> uuid.UUID:
    lid = livrabil(tenant, canal="facebook")
    curenta = Stare.PLANIFICAT
    for s in (Stare.BRIEFAT, Stare.IN_SCRIERE, Stare.IN_VALIDARE, Stare.VALIDAT):
        muta(tenant, lid, curenta, s)
        curenta = s
    with sesiune_tenant(tenant) as db:
        ap = productie.aprobari.cere(db, lid)
        productie.aprobari.decide(
            db, ap.id, Hotarare.APROBAT, utilizator_id=om, rol=Rol.PROPRIETAR, versiune=1
        )
        # conținutul versiunii aprobate (validarea e a F5; aici contează doar ce pleacă)
        validare.continut.scrie(db, lid, text=text, campuri={"hashtaguri": ["#cafea"]}, autor="test")
    return lid


def test_pleaca_la_minut_respecta_frecventa_si_zilele_blocate_iar_criza_opreste_tot(
    tenant: uuid.UUID, om: uuid.UUID, platforma: PlatformaFalsa
) -> None:
    autorizeaza(tenant, om, "facebook", platforma.cod_valid())
    acum = local(16, 8)  # luni, 08:00 la București
    with sesiune_tenant(tenant) as db:
        programare.seteaza_reguli(db, tenant, "facebook", sloturi={"*": ["10:00"]}, max_pe_zi=1)
        programare.blocheaza_zi(db, tenant, dt.date(2026, 11, 16), motiv="doliu național", utilizator_id=om)
    lids = [aprobat(tenant, om, f"Cafeneaua Zorilor, ziua {i}.") for i in range(4)]
    with sesiune_tenant(tenant) as db:
        pp = [programare.programeaza(db, lid, acum=acum, utilizator_id=om) for lid in lids]
        assert [p.la for p in pp] == [local(17, 10), local(18, 10), local(19, 10), local(20, 10)], (
            "ziua blocată sărită, o postare pe zi, la slotul clientului"
        )
        assert programare.programeaza(db, lids[0], acum=acum).id == pp[0].id, "idempotent pe versiune"
    assert all(livrabil_stare(tenant, lid) == "programat" for lid in lids)
    # la minut: 09:59 nu pleacă nimic, 10:00 pleacă
    assert programare.tic_acum(local(17, 9, 59)) == {}
    assert programare.tic_acum(local(17, 10)) == {"plecat": 1}
    assert livrabil_stare(tenant, lids[0]) == "in_publicare"
    with sesiune_tenant(tenant) as db:
        [p0] = programare.a_livrabilului(db, lids[0])
        assert p0.stare == "plecata" and p0.efect_id is not None
        e = efecte.citeste(db, p0.efect_id)
        assert (
            e is not None
            and e.payload["text"] == "Cafeneaua Zorilor, ziua 0."
            and e.payload["taguri"] == ["cafea"]
        )
        assert e.payload["vizibilitate"] == "privat", "aplicația în test: pe contul agenției, restrâns"
    assert efecte.incearca_efect(tenant, p0.efect_id) == "trimis"
    assert livrabil_stare(tenant, lids[0]) == "publicat" and len(platforma.postari) == 1
    # a doua pleacă la minutul ei; pauza de criză (pe client) oprește tot: efectul deja cerut și ce urmează
    assert programare.tic_acum(local(18, 10)) == {"plecat": 1}
    with sesiune_agentie() as db:
        opriri.seteaza(
            db, opriri.Oprire.CLIENT, True, canal="panou", motiv="criză", tenant_id=tenant, utilizator_id=om
        )
    with sesiune_tenant(tenant) as db:
        [p1] = programare.a_livrabilului(db, lids[1])
    assert p1.efect_id is not None and efecte.incearca_efect(tenant, p1.efect_id) == "oprit"
    assert programare.tic_acum(local(19, 10)) == {"oprit": 1}
    assert len(platforma.postari) == 1 and livrabil_stare(tenant, lids[2]) == "programat"
    with sesiune_agentie() as db:
        opriri.seteaza(
            db, opriri.Oprire.CLIENT, False, canal="panou", motiv="gata", tenant_id=tenant, utilizator_id=om
        )
    assert efecte.incearca_efect(tenant, p1.efect_id) == "trimis"
    assert programare.tic_acum(local(19, 10, 1)) == {"plecat": 1}
    # un om trece canalul pe asistat: ce era programat devine pachet asistat
    with sesiune_tenant(tenant) as db:
        assert programare.treci_pe_asistat(db, tenant, "facebook", utilizator_id=om, motiv="test") == 1
        [p3] = programare.a_livrabilului(db, lids[3])
        assert p3.stare == "asistata" and publicare.asistata.al_versiunii(db, lids[3], 1) is not None
    assert programare.tic_acum(local(20, 10)) == {}


def test_slotul_nucleu_pur() -> None:
    r = programare.Reguli({"*": ["09:00", "18:00"]}, max_pe_zi=2, pauza_minima_min=240)
    dupa = local(16, 8)
    assert programare.alege_slot(r, dupa=dupa, ocupate=[], blocate=set()) == local(16, 9)
    assert programare.alege_slot(r, dupa=dupa, ocupate=[local(16, 9)], blocate=set()) == local(16, 18)
    assert programare.alege_slot(r, dupa=dupa, ocupate=[local(16, 9), local(16, 18)], blocate=set()) == local(
        17, 9
    )
    assert programare.alege_slot(r, dupa=dupa, ocupate=[local(16, 16)], blocate=set()) == local(16, 9)
    assert programare.alege_slot(r, dupa=dupa, ocupate=[], blocate={dt.date(2026, 11, 16)}) == local(17, 9)
