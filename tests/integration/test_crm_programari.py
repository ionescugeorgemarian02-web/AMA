"""F12.5 — programări. „Gata când”: rezervi un apel de pe telefon și primești invitația.
Furnizorul de email e cutia poștală SIMULATĂ."""

# ruff: noqa: F811
import datetime as dt
import re
import time
import uuid
from collections.abc import Iterator
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select

from app.connectors.email import CutiePostalaSimulata
from app.crm import CrmRefuzat, Sarcina, calificare, programari, registru
from app.db import sesiune_agentie
from app.site import audit
from tests.integration.conftest import csrf_din
from tests.integration.utile_crm import curata_crm
from tests.integration.utile_site import asteapta, cutie, link_din  # noqa: F401

pytestmark = pytest.mark.db
TELEFON = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148 Safari/604.1"}
SLOT = re.compile(r'name="slot" value="([^"]+)"')


@pytest.fixture(autouse=True)
def _curat(admin_engine: Engine) -> Iterator[None]:
    curata_crm(admin_engine)
    yield
    curata_crm(admin_engine)


def formular(client: TestClient, **extra: str) -> tuple[list[str], dict[str, str]]:
    h = client.get("/site/programare", headers=TELEFON)
    assert h.status_code == 200 and 'name="viewport"' in h.text and "asistentul AI" in h.text
    date = {"csrf_token": csrf_din(h.text), "t": audit.jeton_formular(time.time() - 10), "nume": "Ana Pop",
            "firma": "Cafeneaua Zorilor", "email": "ana@zorilor.example", "telefon": "0722000000", **extra}  # fmt: skip
    return SLOT.findall(h.text), date


def test_rezervi_un_apel_de_pe_telefon_si_primesti_invitatia(
    client: TestClient, cutie: CutiePostalaSimulata, executor: None
) -> None:
    adresa = f"prog-{uuid.uuid4().hex[:8]}@zorilor.example"
    sloturi, date = formular(
        client, email=adresa, nisa="horeca", buget="1000_3000", termen="imediat", decident="da"
    )
    assert sloturi, "sunt intervale libere"
    ales = sloturi[0]
    r = client.post("/site/programare", data={**date, "slot": ales}, headers=TELEFON)
    assert r.status_code == 200 and "Apel programat" in r.text and "invitația de calendar" in r.text
    [m] = asteapta(lambda: cutie.catre(adresa))
    assert m.subiect.startswith("Confirmat:")
    [inv] = m.atasamente
    inceput = dt.datetime.fromisoformat(ales)
    assert inv["nume"] == "invitatie.ics" and inv["tip"].startswith("text/calendar")
    assert (
        "METHOD:REQUEST" in inv["continut"]
        and f"ATTENDEE;ROLE=REQ-PARTICIPANT;RSVP=TRUE:mailto:{adresa}" in inv["continut"]
    )
    assert f"DTSTART:{inceput.astimezone(dt.UTC):%Y%m%dT%H%M%SZ}" in inv["continut"]
    assert "List-Unsubscribe" not in m.antete, "invitația e tranzacțională, nu comercială"

    with sesiune_agentie() as db:
        [(lead, contact, _)] = registru.lista(db)
        assert (lead.etapa, lead.sursa, contact.email, contact.telefon) == (
            "apel_programat",
            "programare",
            adresa,
            "0722000000",
        )
        assert registru.scopuri_acordate(db, contact.id) == [], (
            "o programare nu e acord pentru emailuri comerciale"
        )
        c = calificare.curenta(db, lead.id)
        assert c is not None and c.grupa == "suna_azi"
        assert any(
            "Apel cu" in s.titlu for s in db.scalars(select(Sarcina).where(Sarcina.lead_id == lead.id))
        )
        assert inceput not in programari.sloturi(db), "slotul luat nu mai e oferit"

    # același slot, a doua oară: refuzat, fără a doua programare
    _, alt = formular(client, email="alt@zorilor.example", firma="Altă Firmă")
    r2 = client.post("/site/programare", data={**alt, "slot": ales}, headers=TELEFON)
    assert r2.status_code == 422 and "nu este disponibil" in r2.text
    # capcana și formularul trimis prea repede
    assert (
        client.post("/site/programare", data={**alt, "slot": sloturi[1], "site_web2": "x"}).status_code == 422
    )
    assert (
        client.post(
            "/site/programare", data={**alt, "slot": sloturi[1], "t": audit.jeton_formular()}
        ).status_code
        == 422
    )
    assert (
        client.post("/site/programare", data={**alt, "slot": sloturi[1], "csrf_token": "x"}).status_code
        == 403
    )

    # reamintirile: cu o zi și cu o oră înainte, fiecare o singură dată
    assert programari.ruleaza(inceput - dt.timedelta(hours=30)) == 0
    assert programari.ruleaza(inceput - dt.timedelta(hours=23)) == 1
    assert programari.ruleaza(inceput - dt.timedelta(hours=22)) == 0
    assert programari.ruleaza(inceput - dt.timedelta(minutes=50)) == 1
    asteapta(lambda: (lambda x: x if len(x) == 3 else None)(cutie.catre(adresa)))

    # anularea din linkul din email: deschiderea nu anulează, butonul da; slotul se eliberează
    cale = urlsplit(link_din(m.text, "/programare/anulare/")).path
    h = client.get(cale, headers=TELEFON)
    assert h.status_code == 200 and "Anulează apelul" in h.text
    assert client.post(cale).status_code == 403, "butonul poartă CSRF"
    assert client.post(cale, data={"csrf_token": csrf_din(h.text)}).status_code == 200
    anulare = asteapta(lambda: [x for x in cutie.catre(adresa) if x.subiect == "Apel anulat"] or None)
    assert "METHOD:CANCEL" in anulare[0].atasamente[0]["continut"]
    with sesiune_agentie() as db:
        assert inceput in programari.sloturi(db)
    assert client.get("/site/programare/anulare/" + "x" * 30).status_code == 404


def test_grila_doar_zile_lucratoare_in_program_si_cu_avans() -> None:
    luni_8 = dt.datetime(2026, 11, 23, 6, 0, tzinfo=dt.UTC)  # 08:00 ora României
    g = programari.grila(luni_8)
    locale = [s.astimezone(programari.FUS) for s in g]
    assert locale[0].hour == 10 and locale[0].minute == 0, "primul slot la 10:00 (avans 2 ore)"
    assert all(t.weekday() < 5 and 10 <= t.hour < 17 and t.minute in (0, 30) for t in locale)
    assert max(g) <= luni_8 + programari.ORIZONT
    with sesiune_agentie() as db, pytest.raises(CrmRefuzat):
        programari.rezerva(
            db, inceput=luni_8 + dt.timedelta(minutes=10), email="a@b.example", firma="Firma", acum=luni_8
        )
