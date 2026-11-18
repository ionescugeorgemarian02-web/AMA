"""F12.1 — CRM-ul e al agenției: un client nu vede și nu scrie nimic în el; istoricul consimțământului și
activitățile nu se pot schimba sau șterge nici de către aplicație."""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.crm import registru
from app.db import ContextDb, sesiune
from tests.integration.utile_crm import TABELE_CRM
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]
TABELE = TABELE_CRM


@pytest.fixture(autouse=True)
def _curat(admin_engine: Engine) -> None:
    with admin_engine.begin() as c:
        for t in TABELE:
            c.execute(text(f"DELETE FROM {t}"))


def test_clientul_nu_vede_si_nu_scrie_in_crm(date: Date) -> None:
    with sesiune(ContextDb(agency=True)) as s:
        registru.primeste(s, email="ana@izolare.example", firma="Firma Izolată", sursa="formular_audit")
    for ctx in (ContextDb(tenant_id=date.a, user_id=date.user_a), ContextDb()):
        with sesiune(ctx) as s:
            for t in TABELE:
                assert s.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() == 0, t
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as s:
        registru.primeste(s, email="alt@izolare.example", firma="Firma Străină", sursa="recomandare")
    with sesiune(ContextDb(agency=True)) as s:
        assert s.execute(text("SELECT count(*) FROM crm_contacte")).scalar_one() == 1


@pytest.mark.parametrize("tabel", ["crm_consimtamant", "crm_activitati"])
@pytest.mark.parametrize("comanda", ["DELETE FROM {t}", "UPDATE {t} SET la = now()"])
def test_urma_nu_se_poate_schimba_sau_sterge(tabel: str, comanda: str) -> None:
    with sesiune(ContextDb(agency=True)) as s:
        registru.primeste(s, email="urma@izolare.example", firma="Firma cu Urmă", sursa="formular_audit")
    with pytest.raises(DBAPIError, match="permission denied"), sesiune(ContextDb(agency=True)) as s:
        s.execute(text(comanda.format(t=tabel)))
