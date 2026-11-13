"""F4.6 — faptele, ofertele și extragerile sunt date de client: citirea pentru context și tabelul de extrageri respectă RLS."""

import datetime as dt
import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError

from app import creier
from app.creier import fapte, oferte
from app.creier.compartimente import SursaTip
from app.creier.versiuni import Sursa
from app.db import ContextDb, sesiune
from app.ids import new_id
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]


def fapt_aprobat(tenant: uuid.UUID, user: uuid.UUID, afirmatie: str) -> uuid.UUID:
    with sesiune(ContextDb(tenant_id=tenant, user_id=user)) as db:
        i, _, _ = fapte.propune_fapt(
            db, tenant_id=tenant, continut={"tip": "caracteristica", "subiect": "x", "afirmatie": afirmatie},
            sursa=Sursa(SursaTip.DECLARATIE_CLIENT), utilizator_id=user,
        )  # fmt: skip
        fapte.aproba_fapt(db, i.id, 1, utilizator_id=user)
        return i.id


def test_contextul_unui_client_contine_doar_faptele_si_ofertele_lui(date: Date) -> None:
    fa = fapt_aprobat(date.a, date.user_a, "Fapt al clientului A")
    fb = fapt_aprobat(date.b, date.user_b, "Fapt al clientului B")
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as db:
        oferte.propune_oferta(
            db, tenant_id=date.a, continut={"tip": "produs", "nume": "Produs A", "pret": {"numar": "10"}, "fapte": [str(fa)]},
            sursa=Sursa(SursaTip.DECLARATIE_CLIENT), utilizator_id=date.user_a,
        )  # fmt: skip
        with pytest.raises(creier.RegulaCreier):  # o ofertă nu se poate lega de faptul altui client
            oferte.propune_oferta(
                db, tenant_id=date.a, continut={"tip": "produs", "nume": "Produs A2", "pret": {"numar": "10"}, "fapte": [str(fb)]},
                sursa=Sursa(SursaTip.DECLARATIE_CLIENT), utilizator_id=date.user_a,
            )  # fmt: skip
    ctx_a, ctx_b = (
        ContextDb(tenant_id=date.a, user_id=date.user_a),
        ContextDb(tenant_id=date.b, user_id=date.user_b),
    )
    ACUM = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=5)
    with sesiune(ctx_a) as db:
        assert [f.afirmatie for f in fapte.pentru_context(db, date.a, ACUM)] == ["Fapt al clientului A"]
        assert fapte.pentru_context(db, date.b, ACUM) == []  # nici cerând explicit clientul B
        assert [f.afirmatie for f in fapte.propuneri(db)] == []
    with sesiune(ctx_b) as db:
        assert [f.afirmatie for f in fapte.pentru_context(db, date.b, ACUM)] == ["Fapt al clientului B"]
        assert oferte.pentru_context(db, date.b, ACUM) == [] and oferte.pentru_context(db, date.a, ACUM) == []
    with sesiune(ContextDb()) as db:  # fără client, baza nu arată nimic
        assert fapte.pentru_context(db, date.a, ACUM) == []


def test_extragerile_se_vad_doar_la_clientul_lor(date: Date, admin_engine: Engine) -> None:
    ids = {}
    with admin_engine.begin() as c:
        for cheie, tenant in (("a", date.a), ("b", date.b)):
            ids[cheie] = new_id()
            c.execute(
                text(
                    "INSERT INTO creier_extrageri (id, tenant_id, pasaj_id, document_id, prompt, propuse) VALUES (:i, :t, :p, :d, 'p@1', 2)"
                ),
                {"i": ids[cheie], "t": tenant, "p": new_id(), "d": new_id()},
            )

    def vazute(ctx: ContextDb) -> set[uuid.UUID]:
        with sesiune(ctx) as s:
            return {r[0] for r in s.execute(text("SELECT id FROM creier_extrageri"))}

    a = vazute(ContextDb(tenant_id=date.a, user_id=date.user_a))
    assert ids["a"] in a and ids["b"] not in a
    assert {ids["a"], ids["b"]} <= vazute(ContextDb(agency=True)) and vazute(ContextDb()) == set()
    with pytest.raises(ProgrammingError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        s.execute(
            text("UPDATE creier_extrageri SET propuse = 99 WHERE id = :i"), {"i": ids["b"]}
        )  # doar adăugări
