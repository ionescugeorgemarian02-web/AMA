"""F12.9 — lista de conturi-țintă. „Gata când”: o listă de firme dintr-o nișă are mini-audit și nu conține date
personale. Sursa de firme și motorul de audit sunt SIMULATE."""

import ast
import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app import gateway
from app.conturi import Rol
from app.crm import conturi_tinta
from app.db import sesiune_agentie
from tests.integration.conftest import Cont
from tests.integration.utile_crm import curata_crm
from tests.integration.utile_panou import autentifica, csrf

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _curat(admin_engine: Engine) -> Iterator[None]:
    curata_crm(admin_engine)
    yield
    curata_crm(admin_engine)


def test_lista_dintr_o_nisa_are_mini_audit_si_nu_contine_date_personale(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float], admin_engine: Engine
) -> None:
    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    jeton = csrf(client, "/crm/tinta")
    r = client.post(
        "/crm/tinta",
        data={"csrf_token": jeton, "nisa": "horeca", "localitate": "Cluj"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and "lista=horeca-cluj" in r.headers["location"]
    with sesiune_agentie() as db:
        firme = conturi_tinta.din_lista(db, "horeca-cluj")
        assert {f.nume for f in firme} == {"Cafeneaua Boema SRL", "Bistro Central", "Patiseria Dulce SRL"}
        for f in firme:
            assert f.mini_audit["constatari"] and len(f.argumente) == 3 and f.nisa == "horeca"
        boema = next(f for f in firme if f.nume.startswith("Cafeneaua"))
        assert boema.pagini == ["https://facebook.com/cafeneauaboema"], "profilul unui om nu intră"
        assert boema.argumente[0] == "Am observat că site-ul se încarcă greu pe telefon."
    # niciun rând nu conține date personale: nici nume de oameni, nici telefoane sau adrese de email
    with admin_engine.begin() as c:
        randuri = [
            json.dumps(dict(r._mapping), default=str, ensure_ascii=False)
            for r in c.execute(text("SELECT * FROM crm_conturi_tinta"))
        ]
        coloane = {
            r[0]
            for r in c.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'crm_conturi_tinta'"
                )
            )
        }
    tot = "\n".join(randuri)
    assert not gateway.detecteaza_date_personale(tot)
    for interzis in ("Ana Popescu", "Popescu Ion", "ana.popescu", "0722", "rezervari@", "0744"):
        assert interzis not in tot, interzis
    assert not coloane & {"email", "telefon", "persoana", "administrator", "descriere"}

    assert (
        client.post(
            "/crm/tinta", data={"csrf_token": jeton, "nisa": "horeca", "localitate": "Cluj"}
        ).status_code
        == 200
    )
    with sesiune_agentie() as db:
        assert len(conturi_tinta.din_lista(db, "horeca-cluj")) == 3, "a doua construire nu dublează"
    h = client.get("/crm/tinta?lista=horeca-cluj").text
    assert "Cafeneaua Boema SRL" in h and "le contactezi tu, personal" in h
    assert (
        client.post("/crm/tinta", data={"csrf_token": jeton, "nisa": "<x>", "localitate": "!"}).status_code
        == 422
    )


def test_platforma_nu_trimite_singura_nimic_catre_lista() -> None:
    sursa = Path(conturi_tinta.__file__).read_text(encoding="utf-8")
    importuri = {n.module or "" for n in ast.walk(ast.parse(sursa)) if isinstance(n, ast.ImportFrom)} | {
        a.name for n in ast.walk(ast.parse(sursa)) if isinstance(n, ast.Import) for a in n.names
    }
    assert not {
        i for i in importuri if i.startswith(("app.operare.efecte", "app.connectors", "app.crm.email"))
    }
    assert "sistem.cere" not in sursa and "email.trimite" not in sursa
    assert conturi_tinta.persoana_fizica("Popescu Ion PFA") and not conturi_tinta.persoana_fizica(
        "Bistro SRL"
    )
