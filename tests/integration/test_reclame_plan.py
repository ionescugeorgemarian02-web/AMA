"""F13.3 — planificatorul media. „Gata când”: un plan de probă are structură, plafoane și criterii de oprire și
trece verificarea; un plan peste plafoane nu se poate aproba."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.conturi import Rol
from app.db import sesiune_agentie
from app.reclame import plan
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti  # noqa: F401
from tests.integration.utile_reclame import cont_agentie  # noqa: F401

pytestmark = pytest.mark.db
PARAMETRI = {
    "obiectiv": "lead",
    "pagina_destinatie": "https://agentie.example/audit",
    "buget_lunar_bani": 240_000,
    "public": "Proprietari de IMM-uri din România, 25–60 de ani",
    "cost_tinta_bani": 4_000,
    "unghiuri": ["Auditul arată unde pierzi clienți", "Trei greșeli de pe site", "Exemplu: o cafenea"],
    "nume": "Audit gratuit",
}


def test_planul_de_proba_are_structura_plafoane_criterii_si_trece_verificarea(
    cont_agentie: Callable[..., tuple[uuid.UUID, uuid.UUID]],
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
    admin_engine: Engine,
) -> None:
    _, cont_id = cont_agentie()
    with sesiune_agentie() as db:
        r = plan.propune(db, cont_id, **PARAMETRI)
        p = plan.plan_din(r)
        pid = r.id
    assert r.probleme == []
    assert [c.rol for c in p.campanii] == ["scalare", "test"]
    assert p.buget_zilnic_bani == 8_000 and p.campanii[1].buget_zilnic_bani == 1_600
    assert p.campanii[1].variante == PARAMETRI["unghiuri"] and p.campanii[1].variabila == "hook"
    assert (p.plafon_zilnic_bani, p.plafon_campanie_bani) == (10_000, 8_000)
    assert p.criterii_oprire.multiplu_pierdere == 3.0 and p.masurare.utm_campaign == "audit-gratuit"

    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    h = client.get(f"/reclame/cont/{cont_id}").text
    assert f'data-plan="{pid}" data-stare="propus"' in h and "Oprire la cost pe rezultat peste 3.0" in h
    r2 = client.post(f"/reclame/plan/{pid}/aproba", data={"csrf_token": csrf(client)}, follow_redirects=False)
    assert r2.status_code == 303 and "plan_aproba" in r2.headers["location"]
    assert f'data-plan="{pid}" data-stare="aprobat"' in client.get(f"/reclame/cont/{cont_id}").text
    with pytest.raises(DBAPIError), admin_engine.begin() as c:  # un plan aprobat nu se mai schimbă
        c.execute(text("UPDATE reclame_planuri SET continut = '{}' WHERE id = :i"), {"i": pid})


def test_planul_peste_plafoane_nu_se_aproba(
    cont_agentie: Callable[..., tuple[uuid.UUID, uuid.UUID]],
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
) -> None:
    _, cont_id = cont_agentie(plafon_campanie_bani=2_000)
    with sesiune_agentie() as db:
        r = plan.propune(db, cont_id, **PARAMETRI)
        pid = r.id
    assert any("plafonul pe campanie" in x for x in r.probleme)
    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    r2 = client.post(f"/reclame/plan/{pid}/aproba", data={"csrf_token": csrf(client)}, follow_redirects=False)
    assert "eroare=" in r2.headers["location"]
    with sesiune_agentie() as db:
        assert db.get(plan.PlanMediaRand, pid).stare == "propus"  # type: ignore[union-attr]
