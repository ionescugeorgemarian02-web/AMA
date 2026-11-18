"""Poarta F15 — întărire și lansare, cap-coadă pe simulare (docs/23 §23.18, docs/25 §25.3–25.6).

1. Avaria: catalogul acoperă cele 14 scenarii; un raport 14/14 de pe staging (# SIMULAT: rularea reală e
   `scripts/avarie.sh` pe VPS) bifează T1.
2. Restaurarea: exercițiul real (backup -> mediu curat -> verificare) trece în ținta de 4 h.
3. Pilotul: trei clienți la L1, cu preț de pilot, patru săptămâni (# SIMULAT: accelerate, începutul mutat cu 27 de
   zile în urmă), aprobări reale (90% din prima), feedback în fiecare săptămână, raportul săptămânal: poarta trece.
4. Lansarea: două studii de caz din cifrele pilotului, publicate cu acord; lista 25.5 calculează T1, Q2, Q3, C2, C6
   ca bifate, iar C1 (avocatul) și C7 (motorul de audit simulat) ca nebifate: lansarea rămâne oprită.
"""

import datetime as dt
import importlib.util
import shutil
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.conturi import Rol
from app.db import sesiune_agentie
from app.lansare import golive, pilot, studii
from app.productie import Clasa, Hotarare, Nivel, autonomie
from app.productie.reguli_aprobare import MOTIVE_RESPINGERE
from tests.avarie.catalog import SCENARII, noduri
from tests.conftest import BazaTest
from tests.integration.test_productie_aprobari import cere, decide, validat

pytestmark = pytest.mark.db
ROOT = Path(__file__).resolve().parents[2]
AZI = dt.datetime.now(dt.UTC).date()


@pytest.fixture(autouse=True)
def _curat(admin_engine: Engine) -> None:
    with admin_engine.begin() as c:
        c.execute(text("DELETE FROM studii_caz; DELETE FROM verificari_lansare; DELETE FROM rezultate_avarie;"
                       " DELETE FROM pilot_rapoarte; DELETE FROM pilot_feedback; DELETE FROM pilot_clienti"))  # fmt: skip


def _restaurare():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "exercitiu_restaurare", ROOT / "scripts" / "exercitiu_restaurare.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_poarta_f15(
    baza: BazaTest,
    client: TestClient,
    fabrica_clienti: Callable[[], uuid.UUID],
    om: uuid.UUID,
    tmp_path: Path,
) -> None:
    # 1. avaria
    assert len(SCENARII) == 14 and all(s.teste for s in SCENARII) and len(noduri()) >= 14
    with sesiune_agentie() as db:
        golive.inregistreaza_avarie(db, {"schema": "ama.avarie/1", "trecute": 14, "total": 14, "scenarii": []},
                                    mediu="staging")  # fmt: skip
    # 2. restaurarea
    if all(shutil.which(u) for u in ("pg_dump", "pg_restore", "psql", "age", "age-keygen", "rclone")):
        rez = _restaurare().exercitiu(baza.admin_url, baza.app_url, lucru=tmp_path / "restaurare")
        assert rez["trecut"] and rez["durata_sec"] < 4 * 3600, rez
    # 3. pilotul
    inceput = AZI - dt.timedelta(days=27)
    clienti = [fabrica_clienti() for _ in range(3)]
    for t in clienti:
        with sesiune_agentie() as db:
            pilot.inscrie(
                db, t, pret_lunar_bani=49_000, utilizator_id=om, rol=Rol.PROPRIETAR, inceput=inceput
            )
            assert set(autonomie.matrice(db, t).values()) == {Nivel.L1} and len(
                autonomie.matrice(db, t)
            ) == len(Clasa)
        for k in range(10):
            ap = cere(t, validat(t))
            if k == 9:
                decide(
                    t, ap.id, Hotarare.RESPINS, om, motiv_standard=next(iter(MOTIVE_RESPINGERE)), motiv="ton"
                )
            else:
                decide(t, ap.id, Hotarare.APROBAT, om)
        with sesiune_agentie() as db:
            for s in range(4):
                pilot.feedback(db, t, zi=inceput + dt.timedelta(weeks=s), satisfactie=4, minute_om=20,
                               frictiuni="", utilizator_id=om)  # fmt: skip
    with sesiune_agentie() as db:
        rapoarte = pilot.raport_saptamanal(db, AZI)
        assert {r["tenant_id"] for r in rapoarte} == {str(t) for t in clienti}
        for p in pilot.clienti(db):
            st = pilot.stare_poarta(db, p, AZI)
            assert st["trece"] and st["rata_aprobare_din_prima"] == 0.9 and st["incidente_critice"] == 0, st
    # 4. lansarea
    with sesiune_agentie() as db:
        for t in clienti[:2]:
            s = studii.ciorna_din_pilot(db, t, titlu="Patru săptămâni la L1", situatie="Fără plan de conținut.",
                                        actiune="Pachetul Creștere, două canale.")  # fmt: skip
            assert "90% aprobate din prima" in s.rezultat
            studii.publica(db, s.id, acord_client=True, utilizator_id=om)
        puncte = {p["cod"]: p for p in golive.evalueaza(db)}
        rez_lista = golive.rezumat(list(puncte.values()))
    for cod in ("T1", "Q2", "Q3", "C2", "C6"):
        assert puncte[cod]["bifat"], (cod, puncte[cod]["detaliu"])
    for cod in ("C1", "C7"):
        assert puncte[cod]["auto"] is False, cod
    assert not rez_lista["gata"] and rez_lista["total"] == 21
    assert client.get("/site/studii-de-caz").text.count("Patru săptămâni la L1") == 2
    assert "necesită revizuirea avocatului" in client.get("/site/legal/contract").text
