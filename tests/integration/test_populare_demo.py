"""Modul local: popularea demo creează proprietarul, brandul „Cafeneaua Zorilor” și brieful aprobat; e idempotentă."""

import pytest
from sqlalchemy import Engine, text

from app import creier
from app.creier.compartimente import Compartiment
from app.db import sesiune_tenant
from app.demo import BRAND_DEMO, populeaza
from app.onboarding import brief, completare

pytestmark = pytest.mark.db


def test_populare_idempotenta(admin_engine: Engine) -> None:
    r1 = populeaza("admin@local.test", "parola-demo-locala-123")
    assert r1.creat_acum == ("proprietar", "client", "brief")
    r2 = populeaza("admin@local.test", "parola-demo-locala-123")
    assert r2.creat_acum == () and (r2.client_id, r2.proprietar_id) == (r1.client_id, r1.proprietar_id)
    with admin_engine.begin() as c:
        assert (
            c.execute(text("SELECT count(*) FROM clienti WHERE nume = :n"), {"n": BRAND_DEMO}).scalar() == 1
        )
    with sesiune_tenant(r1.client_id, r1.proprietar_id) as db:
        i = creier.gaseste_intrare(
            db, tenant_id=r1.client_id, compartiment=Compartiment.BRIEF, cheie=completare.CHEIE_BRIEF
        )
        assert i is not None
        v = creier.versiune_aprobata(db, i.id)
        assert v is not None and brief.este_complet(v.continut)
