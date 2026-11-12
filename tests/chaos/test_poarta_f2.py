"""POARTA F2 (docs/23): „un livrabil de probă parcurge toate stările, supraviețuiește unei reporniri și nu produce
efecte duble”.

Cap-coadă, cu procese reale și Postgres real: un video de probă merge de la `planificat` la `inchis` (cu o rundă de
reparație, deci prin toate cele 16 stări normale). Workerul este omorât cu SIGKILL de două ori:
1. la mijloc, în pasul `in_randare` (după aprobare);
2. în jurul publicării: conectorul fals a înregistrat deja postarea, dar executorul nu a apucat să noteze rezultatul.
Se verifică: toate stările normale în ordine, o singură postare la conectorul fals, nicio tranziție dublată sau refuzată.

SIMULAT: fluxul de probă (`tests/integration/fluxuri_livrabil.py`) și conectorul fals (`tests/conector_fals.py`)."""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import Engine

from app.connectors import registru
from app.conturi import Rol
from app.db import sesiune_tenant
from app.operare import efecte, motor
from app.productie import NORMALE, Hotarare, aprobari
from tests.chaos.utile import Worker, asteapta
from tests.conector_fals import ConectorFals
from tests.conftest import BazaTest
from tests.integration import fluxuri_livrabil as proba
from tests.integration.utile_productie import livrabil, randuri, stare

pytestmark = pytest.mark.db
MODULE = {"AMA_WORKER_MODULE_TEST": "tests.chaos.fluxuri_efecte,tests.integration.fluxuri_livrabil"}

# Toate cele 16 stări normale (7.2); `in_validare` apare de două ori: o rundă de reparație.
TRASEU = [
    (None, "planificat"),
    ("planificat", "briefat"),
    ("briefat", "in_scriere"),
    ("in_scriere", "in_validare"),
    ("in_validare", "in_reparatie"),
    ("in_reparatie", "in_validare"),
    ("in_validare", "validat"),
    ("validat", "asteapta_aprobare"),
    ("asteapta_aprobare", "aprobat"),
    ("aprobat", "in_randare"),
    ("in_randare", "control_media"),
    ("control_media", "gata"),
    ("gata", "programat"),
    ("programat", "in_publicare"),
    ("in_publicare", "publicat"),
    ("publicat", "in_masurare"),
    ("in_masurare", "inchis"),
]


def test_poarta_f2_un_livrabil_parcurge_toate_starile_supravietuieste_repornirilor_fara_efecte_duble(
    baza: BazaTest,
    dir_proba: Path,
    workeri: list[Worker],
    tenant: uuid.UUID,
    om: uuid.UUID,
    admin_engine: Engine,
) -> None:
    registru.uita_tot()
    platforma = ConectorFals(dir_proba)
    registru.inregistreaza("fals", platforma)
    try:
        lid = livrabil(tenant, tip="video", canal="fals")
        (dir_proba / "blocheaza.in_randare").touch()
        (platforma.dir / "blocheaza").touch()
        platforma.scenariu(trimite=["blocheaza_dupa"])

        w1 = Worker(baza, dir_proba, **MODULE).porneste()
        workeri.append(w1)
        w1.asteapta_pornit()

        # --- de la `planificat` până la cererea de aprobare (L1: decide un om) ---
        prima = motor.trimite(proba.proba, str(tenant), str(lid), "o_runda", cheie=f"poarta-1-{lid}")
        assert motor.asteapta_flux(prima, timeout_sec=60).stare is motor.StareJob.TERMINAT
        assert stare(tenant, lid).value == "asteapta_aprobare"
        with sesiune_tenant(tenant) as db:
            cerere = aprobari.cerere_activa(db, lid)
            assert cerere is not None
            aprobari.decide(db, cerere.id, Hotarare.APROBAT, utilizator_id=om, rol=Rol.PROPRIETAR, versiune=2)

        # --- după aprobare: SIGKILL nr. 1, la mijloc, în `in_randare` ---
        a_doua = motor.trimite(proba.proba, str(tenant), str(lid), "o_runda", cheie=f"poarta-2-{lid}")
        asteapta(lambda: (dir_proba / "ajuns.in_randare").exists(), mesaj="pasul in_randare")
        assert stare(tenant, lid).value == "in_randare"
        w1.omoara()
        (dir_proba / "blocheaza.in_randare").unlink()

        # --- repornire: jobul continuă până la publicare; SIGKILL nr. 2, după ce „platforma” a primit postarea ---
        w2 = Worker(baza, dir_proba, **MODULE).porneste()
        workeri.append(w2)
        asteapta(
            lambda: (platforma.dir / "dupa.marcaj").exists(), timeout_sec=60, mesaj="postarea la conector"
        )
        assert stare(tenant, lid).value == "in_publicare"
        assert len(platforma.postari()) == 1
        w2.omoara()
        (platforma.dir / "blocheaza").unlink()

        # --- a doua repornire: executorul verifică la platformă, nu retrimite, iar livrabilul se închide ---
        w3 = Worker(baza, dir_proba, **MODULE).porneste()
        workeri.append(w3)
        final = motor.asteapta_flux(a_doua, timeout_sec=90)
        assert final.stare is motor.StareJob.TERMINAT, final.eroare
        assert stare(tenant, lid).value == "inchis"

        # toate stările normale, în ordine, fiecare tranziție o singură dată, niciun refuz
        toate = randuri(admin_engine, lid)
        assert [(r["din"], r["in_stare"]) for r in toate] == TRASEU, "nicio tranziție dublată sau lipsă"
        assert {r["rezultat"] for r in toate} == {"aplicata"}, "nicio mutare refuzată"
        assert {r["in_stare"] for r in toate} == {s.value for s in NORMALE}, "toate cele 16 stări normale"

        # un singur efect la conectorul fals și în tabelul „de trimis”
        with sesiune_tenant(tenant) as db:
            [efect] = efecte.ale_livrabilului(db, lid)
        assert efect.stare == "trimis" and len(platforma.postari(efect.cheia)) == 1
        assert len(platforma.postari()) == 1
        assert platforma.apeluri("trimite") == [f"trimite {efect.cheia} blocheaza_dupa"], (
            "o singură trimitere"
        )
        assert len(platforma.apeluri("verifica")) >= 1, "după cădere s-a întrebat platforma"
        assert efect.id_extern == platforma.postari()[0]["id"]
        publicat = next(r for r in toate if r["in_stare"] == "publicat")
        assert publicat["detalii"]["id_extern"] == efect.id_extern  # type: ignore[index]
        assert w3.opreste_curat() == 0
    finally:
        registru.uita_tot()
