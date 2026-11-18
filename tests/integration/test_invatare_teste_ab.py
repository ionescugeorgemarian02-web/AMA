"""F14.4 — Teste A/B formale. „Gata când”: un test are ipoteza declarată dinainte și verdictul calculat automat."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.db import sesiune_agentie, sesiune_tenant
from app.invatare import teste_ab
from app.invatare.teste_ab import TestRefuzat
from tests.integration.utile_productie import fabrica_clienti  # noqa: F401

pytestmark = pytest.mark.db
ACUM = dt.datetime.now(dt.UTC)


def declara(**kw: object) -> uuid.UUID:
    with sesiune_agentie() as db:
        t = teste_ab.declara(
            db, ipoteza="Hook-ul cu întrebare crește rata de interacțiune față de cel cu cifră",
            obiect="proba:tipar_hook", varianta_a="cifra", varianta_b="intrebare", indicator="interactiuni",
            efect_minim=0.02, abatere_estimata=0.04, acum=ACUM, **kw,  # type: ignore[arg-type]
        )  # fmt: skip
        return t.id


def observa(tid: uuid.UUID, varianta: str, valori: list[float], prefix: str) -> None:
    with sesiune_agentie() as db:
        for i, v in enumerate(valori):
            teste_ab.observa(db, tid, varianta=varianta, cheie=f"{prefix}-{i}", valoare=v)


def evalueaza(tid: uuid.UUID, acum: dt.datetime = ACUM) -> teste_ab.ExperimentFormal:
    with sesiune_agentie() as db:
        return teste_ab.evalueaza(db, tid, acum=acum)


def test_ipoteza_declarata_dinainte_si_verdictul_calculat_automat(admin_engine: Engine) -> None:
    tid = declara()
    with sesiune_agentie() as db:
        t = db.get(teste_ab.ExperimentFormal, tid)
        assert t is not None and t.n_pe_varianta == teste_ab.marime_esantion(0.02, 0.04) == 63
    # fără „tras cu ochiul”: diferența uriașă de la început nu încheie testul înainte de eșantionul declarat
    observa(tid, "a", [0.05] * 10, "a")
    observa(tid, "b", [0.20] * 10, "b")
    t = evalueaza(tid)
    assert t.stare == "in_curs" and t.rezultat == {"n_a": 10, "n_b": 10, "n_cerut": 63}
    observa(tid, "a", [0.05 + (i % 7) * 0.01 for i in range(60)], "a2")
    observa(tid, "b", [0.08 + (i % 7) * 0.01 for i in range(60)], "b2")
    observa(tid, "b", [0.9], "b")  # aceeași unitate (b-0) a doua oară nu contează
    t = evalueaza(tid)
    assert t.stare == "incheiat" and t.verdict == "castiga_b"
    r = t.rezultat
    assert r["n_a"] == r["n_b"] == 70 and r["p"] < 0.05 and r["interval"][0] > 0 and r["atinge_efectul_minim"]
    # ce s-a declarat nu se schimbă, nici ca proprietar al bazei; un test încheiat nu se mai schimbă
    for sql in (
        "UPDATE teste_ab SET efect_minim = 0.5 WHERE id = :t",
        "UPDATE teste_ab SET rezultat = '{}' WHERE id = :t",
    ):
        with pytest.raises(DBAPIError, match="nu se mai schimbă"), admin_engine.begin() as c:
            c.execute(text(sql), {"t": tid})
    with admin_engine.connect() as c:
        actiuni = c.execute(
            text("SELECT actiune FROM urme WHERE componenta = 'invatare.teste_ab' AND obiect_id = :t ORDER BY la"),
            {"t": str(tid)},
        ).scalars().all()  # fmt: skip
    assert actiuni == ["declara", "verdict"]


def test_fara_diferenta_neconcludent_la_termen_si_refuzuri() -> None:
    tid = declara()
    observa(tid, "a", [0.05 + (i % 9) * 0.01 for i in range(63)], "a")
    observa(tid, "b", [0.05 + ((i + 4) % 9) * 0.01 for i in range(63)], "b")
    assert evalueaza(tid).verdict == "fara_diferenta"
    tid = declara(durata_maxima_zile=10)
    observa(tid, "a", [0.1] * 5, "a")
    assert evalueaza(tid).stare == "in_curs"
    assert evalueaza(tid, ACUM + dt.timedelta(days=11)).verdict == "neconcludent"
    with sesiune_agentie() as db, pytest.raises(TestRefuzat, match="ipoteza"):
        teste_ab.declara(db, ipoteza="scurtă", obiect="x:y", varianta_a="a", varianta_b="b", indicator="ind",
                         efect_minim=0.1, abatere_estimata=0.1)  # fmt: skip


def test_testul_unui_client_e_izolat(fabrica_clienti: Callable[[], uuid.UUID]) -> None:
    t, alt = fabrica_clienti(), fabrica_clienti()
    with sesiune_tenant(t) as db:
        tid = teste_ab.declara(
            db, ipoteza="Slotul de seară bate slotul de dimineață la interacțiuni", obiect="client:slot",
            varianta_a="dimineata", varianta_b="seara", indicator="interactiuni", efect_minim=0.01,
            abatere_estimata=0.01, tenant_id=t,
        ).id  # fmt: skip
        teste_ab.observa(db, tid, varianta="a", cheie="x", valoare=0.1)
    with sesiune_tenant(alt) as db:
        assert db.get(teste_ab.ExperimentFormal, tid) is None
    with sesiune_tenant(t) as db:
        assert teste_ab.evalueaza(db, tid).rezultat["n_a"] == 1
