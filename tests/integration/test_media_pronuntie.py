"""F8.2 — dicționarul de pronunție pe client (Postgres real, RLS): termenii unui client nu ajung la altul."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable

import pytest

from app import media
from app.db import sesiune_tenant
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401

pytestmark = pytest.mark.db


def test_dictionarul_clientului_se_aplica_doar_lui(
    tenant: uuid.UUID, fabrica_clienti: Callable[[], uuid.UUID]
) -> None:
    altul = fabrica_clienti()
    with sesiune_tenant(tenant) as db:
        media.pronuntie.adauga(db, tenant, "V60", "vi 60")
        media.pronuntie.adauga(db, tenant, "Guji", "Gugi")
        media.pronuntie.adauga(db, tenant, "guji", "Gudji")  # același termen: se înlocuiește
        assert media.pronuntie.dictionar(db, tenant) == {"V60": "vi șaizeci", "Guji": "Gudji"}
        txt = media.pronuntie.pentru_voce(db, tenant, "Etiopia Guji la V60 costă 49 lei.")
        assert txt == "Etiopia Gudji la vi șaizeci costă patruzeci și nouă de lei."
    with sesiune_tenant(altul) as db:
        assert media.pronuntie.dictionar(db, altul) == {}
        assert media.pronuntie.pentru_voce(db, altul, "Guji la V60") == "Guji la V șaizeci"
