"""F15.5 — izolarea pilotului: clientul își vede doar rândurile lui de pilot și nu scrie pe numele altuia."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import ContextDb, sesiune
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]
TABELE = ("pilot_clienti", "pilot_feedback", "pilot_rapoarte")


def _scrie(ctx: ContextDb, t: object) -> None:
    with sesiune(ctx) as s:
        s.execute(text("INSERT INTO pilot_clienti (tenant_id, inceput, pret_lunar_bani) VALUES (:t, current_date, 1)"
                       " ON CONFLICT DO NOTHING"), {"t": t})  # fmt: skip
        s.execute(text("INSERT INTO pilot_feedback (id, tenant_id, saptamana, satisfactie) VALUES (gen_random_uuid(),"
                       " :t, date_trunc('week', current_date)::date, 4) ON CONFLICT DO NOTHING"), {"t": t})  # fmt: skip
        s.execute(text("INSERT INTO pilot_rapoarte (id, tenant_id, saptamana, continut) VALUES (gen_random_uuid(),"
                       " :t, date_trunc('week', current_date)::date, '{}') ON CONFLICT DO NOTHING"), {"t": t})  # fmt: skip


def test_clientul_vede_doar_pilotul_lui_si_nu_scrie_pentru_altul(date: Date) -> None:
    agentie = ContextDb(agency=True)
    _scrie(agentie, date.a)
    _scrie(agentie, date.b)
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        for t in TABELE:
            vazuti = {r[0] for r in s.execute(text(f"SELECT DISTINCT tenant_id FROM {t}"))}
            assert vazuti == {date.a}, t
    with sesiune(ContextDb()) as s:
        assert all(s.execute(text(f"SELECT count(*) FROM {t}")).scalar() == 0 for t in TABELE)
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        s.execute(
            text("UPDATE pilot_clienti SET pret_lunar_bani = 0 WHERE tenant_id = :t RETURNING 1"),
            {"t": date.b},
        )
        s.execute(text("INSERT INTO pilot_feedback (id, tenant_id, saptamana, satisfactie) VALUES (gen_random_uuid(),"
                       " :t, date_trunc('week', current_date)::date + 7, 5)"), {"t": date.b})  # fmt: skip


def test_studiile_de_caz_si_lista_de_go_live_sunt_izolate(date: Date) -> None:
    with sesiune(ContextDb(agency=True)) as s:
        for t, slug in ((date.a, "studiu-a"), (date.b, "studiu-b")):
            s.execute(text("INSERT INTO studii_caz (id, tenant_id, slug, titlu, situatie, actiune, rezultat) VALUES "
                           "(gen_random_uuid(), :t, :s, 'Titlu', 's', 'a', 'r') ON CONFLICT DO NOTHING"),
                      {"t": t, "s": slug})  # fmt: skip
        s.execute(
            text("INSERT INTO verificari_lansare (cod, bifat) VALUES ('T5', true) ON CONFLICT DO NOTHING")
        )
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        assert {r[0] for r in s.execute(text("SELECT slug FROM studii_caz"))} == {"studiu-a"}
        assert s.execute(text("SELECT count(*) FROM verificari_lansare")).scalar() == 0, "doar agenția"
        assert s.execute(text("SELECT count(*) FROM rezultate_avarie")).scalar() == 0
