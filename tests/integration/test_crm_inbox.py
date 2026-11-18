"""F12.7 — inboxul social. „Gata când”: mesajele de test sunt clasificate corect. Canalele sunt SIMULATE."""

import datetime as dt
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text

from app.connectors import inbox as conector
from app.conturi import Rol
from app.crm import inbox
from app.crm.modele import MesajInbox
from app.db import sesiune_agentie
from tests.integration.conftest import Cont
from tests.integration.utile_crm import curata_crm
from tests.integration.utile_panou import autentifica, csrf
from tests.unit.test_crm_inbox import MESAJE_DE_TEST

pytestmark = pytest.mark.db
ACUM = dt.datetime.now(dt.UTC).replace(microsecond=0)


@pytest.fixture(autouse=True)
def _curat(admin_engine: Engine) -> Iterator[None]:
    curata_crm(admin_engine)
    conector.INBOX.primite.clear()
    yield
    conector.INBOX.primite.clear()
    curata_crm(admin_engine)


def primit(canal: str, i: int, text_: str, tip: str = "mesaj", minute: int = 0) -> conector.MesajPrimit:
    return conector.MesajPrimit(
        canal,
        f"{canal}-{i}",
        tip,
        f"fir-{i}",
        f"persoana_{i}",
        text_,
        ACUM - dt.timedelta(minutes=60 - minute),
    )


def test_mesajele_de_test_de_pe_canalele_aprobate_sunt_clasificate_corect(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float], admin_engine: Engine
) -> None:
    for i, (t, _) in enumerate(MESAJE_DE_TEST):
        conector.INBOX.primite.append(primit("instagram", i, t, "comentariu" if i % 2 else "mesaj", i))
    conector.INBOX.primite.append(primit("facebook", 99, "Cât costă?"))  # canal neaprobat
    assert inbox.ruleaza() == {}, "niciun canal aprobat: nu se citește nimic"

    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    jeton = csrf(client, "/crm/inbox")
    r = client.post(
        "/crm/inbox/canal", data={"csrf_token": jeton, "canal": "instagram"}, follow_redirects=False
    )
    assert r.status_code == 303
    assert client.post("/crm/inbox/canal", data={"csrf_token": jeton, "canal": "whatsapp"}).status_code == 422

    noi = inbox.ruleaza()
    assert sum(noi.values()) == len(MESAJE_DE_TEST)
    assert inbox.ruleaza() == {}, "recitirea nu dublează"
    with sesiune_agentie() as db:
        dupa_text = {m.text: m for m in db.scalars(select(MesajInbox))}
        assert {m.canal for m in dupa_text.values()} == {"instagram"}, "canalul neaprobat nu se citește"
        for t, clasa in MESAJE_DE_TEST:
            assert dupa_text[t].clasa == clasa, t
    h = client.get("/crm/inbox?clasa=critica").text
    assert "Groaznic serviciu" in h and "Cât costă pachetul" not in h
    assert client.get("/crm/inbox?clasa=necunoscuta").status_code == 404

    # un mesaj nou, după oprirea canalului, nu se mai citește
    conector.INBOX.primite.append(primit("instagram", 200, "Mulțumesc!", minute=59))
    client.post("/crm/inbox/canal", data={"csrf_token": jeton, "canal": "instagram", "actiune": "opreste"})
    assert inbox.ruleaza() == {}
    with admin_engine.begin() as c:
        n = c.execute(
            text("SELECT count(*) FROM urme WHERE componenta = 'inbox' AND actiune = 'clasificare'")
        ).scalar_one()
    assert n >= len(MESAJE_DE_TEST)


def test_operatorul_nu_vede_inboxul(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float]
) -> None:
    autentifica(client, fabrica_conturi(Rol.OPERATOR, cu_totp=True), ceas)
    assert client.get("/crm/inbox").status_code == 403
