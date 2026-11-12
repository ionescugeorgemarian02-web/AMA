"""F3.1 — registrul de furnizori este la nivel de agenție: citit din orice context cu identitate, scris doar de
scopul de agenție; fără context, baza refuză."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.db import ContextDb, sesiune, sesiune_agentie
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]

NUMARA = text("SELECT count(*) FROM gateway_furnizori")


def test_fara_context_baza_nu_arata_nimic() -> None:
    with sesiune(ContextDb()) as db:
        assert db.execute(NUMARA).scalar_one() == 0
        assert db.execute(text("SELECT count(*) FROM gateway_modele")).scalar_one() == 0


def test_un_client_sau_un_utilizator_citesc_registrul_dar_nu_il_scriu(date: Date) -> None:
    for ctx in (
        ContextDb(tenant_id=date.a),
        ContextDb(user_id=date.user_a),
        ContextDb(user_id=date.operator_a),
    ):
        with sesiune(ctx) as db:
            assert db.execute(NUMARA).scalar_one() >= 5
    with sesiune(
        ContextDb(tenant_id=date.a)
    ) as db:  # fără eroare, dar fără efect: politica de UPDATE nu lasă niciun rând
        assert db.execute(text("UPDATE gateway_furnizori SET stare_motiv = 'x'")).rowcount == 0
    with sesiune_agentie() as db:
        assert (
            db.execute(text("SELECT count(*) FROM gateway_furnizori WHERE stare_motiv = 'x'")).scalar_one()
            == 0
        )


def test_un_client_nu_poate_adauga_furnizori_sau_modele(date: Date) -> None:
    with pytest.raises((DBAPIError, ProgrammingError)), sesiune(ContextDb(tenant_id=date.a)) as db:
        db.execute(
            text(
                "INSERT INTO gateway_furnizori (id, cod, nume, tip_api, url_baza, cheie_env, marcaj) VALUES "
                "(:i, 'fals', 'Fals', 'openai_compat', 'https://exemplu.test', 'AMA_CHEIE_FALS', 'I')"
            ),
            {"i": uuid.uuid4()},
        )


def test_agentia_scrie(admin_engine: Engine) -> None:
    with sesiune_agentie() as db:
        db.execute(text("UPDATE gateway_furnizori SET stare_motiv = '' WHERE cod = 'groq'"))


def test_contoarele_si_blocajele_sunt_scrise_doar_de_agentie(date: Date) -> None:
    cheie = f"model:{uuid.uuid4()}"
    inserare = text(
        "INSERT INTO gateway_contoare (cheie, fereastra, inceput, cereri) VALUES (:c, 'minut', now(), 1)"
    )
    with pytest.raises((DBAPIError, ProgrammingError)), sesiune(ContextDb(tenant_id=date.a)) as db:
        db.execute(inserare, {"c": cheie})
    with pytest.raises((DBAPIError, ProgrammingError)), sesiune(ContextDb(tenant_id=date.a)) as db:
        db.execute(text("INSERT INTO gateway_blocaje (cheie, pana_la) VALUES (:c, now())"), {"c": cheie})
    with sesiune_agentie() as db:
        db.execute(inserare, {"c": cheie})
    with sesiune(ContextDb(tenant_id=date.b)) as db:  # citirea e deschisă oricărui context cu identitate
        assert (
            db.execute(
                text("SELECT cereri FROM gateway_contoare WHERE cheie = :c"), {"c": cheie}
            ).scalar_one()
            == 1
        )
        assert db.execute(text("DELETE FROM gateway_contoare WHERE cheie = :c"), {"c": cheie}).rowcount == 0
    with sesiune(ContextDb()) as db:
        assert db.execute(text("SELECT count(*) FROM gateway_contoare")).scalar_one() == 0
    with sesiune_agentie() as db:
        db.execute(text("DELETE FROM gateway_contoare WHERE cheie = :c"), {"c": cheie})
