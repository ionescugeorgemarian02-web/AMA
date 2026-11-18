"""F14.3 — Predictorul de performanță, doar la pragul de date. „Gata când”: pe date trecute, predicția bate
alegerea la întâmplare cu o marjă măsurată. Datele trecute sunt SIMULATE (600 de postări cu un tipar real în
recompensă), scrise în `etichete_postari` ca de colector."""

# ruff: noqa: F811
import datetime as dt
import random
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import Engine, text

from app.db import sesiune_tenant
from app.ids import new_id
from app.invatare import predictiv, predictor
from tests.integration.utile_productie import fabrica_clienti, livrabil  # noqa: F401

pytestmark = pytest.mark.db
TIPARE = ["intrebare", "cifra", "poveste", "rezultat"]
SQL = (
    "INSERT INTO etichete_postari (id, tenant_id, livrabil_id, canal, publicat_la, tipar_hook, format, pilon, "
    "zi_saptamana, ora, recompensa, recompensa_tip, recompensa_interval) VALUES (:i, :t, :l, 'facebook', :p, :h, "
    "'postare', :pi, :zi, :o, :r, 'interactiuni_pe_afisari', '72h')"
)


def populeaza(admin: Engine, t: uuid.UUID, n: int, *, semnal: bool = True, seed: int = 7) -> None:
    """# SIMULAT: n postări trecute; cu `semnal`, întrebările de seară au recompensa clar mai mare."""
    rng = random.Random(seed)  # noqa: S311
    model = livrabil(t)
    inceput = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
    with admin.begin() as c:
        ids = c.execute(
            text(
                "INSERT INTO livrabile SELECT (jsonb_populate_record(NULL::livrabile, to_jsonb(l) || "
                "jsonb_build_object('id', gen_random_uuid()))).* FROM livrabile l, generate_series(1, :n) "
                "WHERE l.id = :l RETURNING id"
            ),
            {"n": n, "l": model},
        ).scalars().all()  # fmt: skip
        randuri = []
        for k, lid in enumerate(ids):
            tipar, ora = rng.choice(TIPARE), rng.randrange(8, 22)
            efect = (0.04 if tipar == "intrebare" else 0.0) + (0.03 if 17 <= ora <= 20 else 0.0)
            r = max(0.0, 0.02 + (efect if semnal else 0.0) + rng.gauss(0, 0.015))
            randuri.append(
                {
                    "i": new_id(),
                    "t": t,
                    "l": lid,
                    "p": inceput + dt.timedelta(hours=12 * k),
                    "h": tipar,
                    "pi": rng.choice(["educatie", "oferta"]),
                    "zi": rng.randrange(1, 8),
                    "o": ora,
                    "r": r,
                }
            )
        c.execute(text(SQL), randuri)  # fmt: skip


def test_sub_prag_nu_se_antreneaza_peste_prag_bate_intamplarea(
    fabrica_clienti: Callable[[], uuid.UUID], admin_engine: Engine
) -> None:
    t = fabrica_clienti()
    populeaza(admin_engine, t, 60)
    with sesiune_tenant(t) as db:
        r = predictor.ruleaza_client(db, t, "facebook")
        assert (r.stare, r.n_exemple, r.metrici) == ("sub_prag", 60, {"lipsesc": predictor.PRAG - 60})
        assert r.model == {} and predictor.sansa(db, t, "facebook", {"tipar_hook": "intrebare"}) is None
    populeaza(admin_engine, t, 560, seed=8)
    with sesiune_tenant(t) as db:
        r = predictor.ruleaza_client(db, t, "facebook")
        assert r.stare == "valid" and r.n_exemple == 620, r.metrici
        m = r.metrici
        assert m["auc_model"] > m["auc_referinta"] + predictiv.MARJA and m["interval"][0] > predictiv.MARJA
        assert m["n_test"] == 186 and m["n_antrenare"] == 434
        seara = predictor.sansa(
            db, t, "facebook", {"tipar_hook": "intrebare", "ora": 18.0, "format": "postare"}
        )
        dimineata = predictor.sansa(
            db, t, "facebook", {"tipar_hook": "cifra", "ora": 9.0, "format": "postare"}
        )
        assert seara is not None and dimineata is not None and seara > dimineata


def test_fara_semnal_modelul_nu_bate_si_nu_se_foloseste(
    fabrica_clienti: Callable[[], uuid.UUID], admin_engine: Engine
) -> None:
    t, alt = fabrica_clienti(), fabrica_clienti()
    populeaza(admin_engine, t, 520, semnal=False)
    with sesiune_tenant(t) as db:
        r = predictor.ruleaza_client(db, t, "facebook")
        assert (
            r.stare == "nu_bate" and predictor.sansa(db, t, "facebook", {"tipar_hook": "intrebare"}) is None
        )
    with sesiune_tenant(alt) as db:  # izolare: celălalt client nu vede modelul și nu are date
        assert predictiv.ultimul(db, "performanta", tenant_id=t, canal="facebook") is None
        assert predictor.ruleaza_client(db, alt, "facebook").stare == "sub_prag"
    with admin_engine.connect() as c:
        assert c.execute(
            text("SELECT count(*) FROM urme WHERE componenta = 'invatare.predictiv' AND tenant_id = :t"), {"t": t}
        ).scalar_one() == 1  # fmt: skip
