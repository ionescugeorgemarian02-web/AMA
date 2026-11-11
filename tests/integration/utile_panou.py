"""Ajutoare comune pentru testele panoului, livrării și Telegram (integrare, bază reală)."""

import json
import re
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.config import get_settings
from app.connectors import telegram
from app.connectors.telegram import TelegramClient
from app.operare import notificari
from app.operare.notificari import AbonamentMort, Destinatar
from tests.integration.conftest import Cont, cod_totp, login, post_cod

META_CSRF = re.compile(r'name="csrf-token" content="([^"]+)"')
TOKEN_LIVRARE = "d" * 40
TOKEN_BOT = "123456:" + "T" * 35  # nu este un jeton real
CHAT = "424242"
SECRET_WEBHOOK = "w" * 32
CHEIE_PUBLICA = "B" + "p" * 86  # formă de cheie VAPID publică (nu este una reală)
CHEIE_PRIVATA = "k" * 43


def autentifica(client: TestClient, cont: Cont, ceas: dict[str, float]) -> None:
    assert cont.secret
    r = login(client, cont.email, cont.parola)
    assert r.status_code == 303 and r.headers["location"] == "/conturi/2fa"
    ceas["t"] += 31  # alt pas de timp decât cel deja folosit (anti-reluare)
    r = post_cod(client, "/conturi/2fa", cod_totp(cont.secret, ceas["t"]))
    assert r.status_code == 303, r.text


def csrf(client: TestClient, cale: str = "/meniu") -> str:
    m = META_CSRF.search(client.get(cale).text)
    assert m, f"fără jeton CSRF pe {cale}"
    return m.group(1)


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Setează variabile de mediu pentru test și golește cache-ul configurării."""

    def seteaza(**valori: str) -> None:
        for k, v in valori.items():
            monkeypatch.setenv(f"AMA_{k.upper()}", v)
        get_settings.cache_clear()

    return seteaza


@pytest.fixture(autouse=True)
def _curata_panou(admin_engine: Engine) -> Iterator[None]:
    """Tabelele panoului sunt globale (nivel de agenție): fiecare test pornește de la zero."""
    with admin_engine.begin() as c:
        c.execute(
            text(
                "TRUNCATE oprituri, cereri_livrare, livrari, telegram_actualizari, telegram_confirmari, "
                "abonamente_push"
            )
        )
    yield
    notificari.reseteaza_trimitator()
    telegram.seteaza_client(None)


class TrimitatorFals:
    """SIMULAT: ține locul serviciului push real (fără rețea în CI)."""

    def __init__(self) -> None:
        self.apeluri: list[tuple[Destinatar, dict[str, Any]]] = []
        self.moarte: set[str] = set()
        self.cade: bool = False

    def __call__(self, dest: Destinatar, payload: str) -> None:
        if dest.endpoint in self.moarte:
            raise AbonamentMort
        if self.cade:
            raise RuntimeError("serviciul push nu răspunde")
        self.apeluri.append((dest, json.loads(payload)))


@pytest.fixture
def push() -> TrimitatorFals:
    f = TrimitatorFals()
    notificari.seteaza_trimitator(f)
    return f


class BotFals:
    """SIMULAT: ține locul Bot API (fără rețea în CI). Răspunsurile au forma celor reale."""

    def __init__(self) -> None:
        self.cereri: list[httpx.Request] = []
        self.status = 200
        self.corp: dict[str, Any] | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.cereri.append(request)
        if self.corp is not None:
            return httpx.Response(self.status, json=self.corp)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 7, "date": 1800000000}})

    def mesaje(self) -> list[str]:
        return [json.loads(r.content)["text"] for r in self.cereri if r.url.path.endswith("/sendMessage")]


@pytest.fixture
def bot_fals(config: Callable[..., None]) -> BotFals:
    config(telegram_bot_token=TOKEN_BOT, telegram_chat_id=CHAT, telegram_webhook_secret=SECRET_WEBHOOK)
    fals = BotFals()
    telegram.seteaza_client(TelegramClient(TOKEN_BOT, transport=httpx.MockTransport(fals.handler)))
    return fals


def actualizare(update_id: int, text_: str, chat: str = CHAT) -> dict[str, Any]:
    """O actualizare în forma Bot API (cu câmpuri în plus, ca cele reale)."""
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id + 1000,
            "from": {"id": int(chat), "is_bot": False, "first_name": "Cineva", "language_code": "ro"},
            "chat": {"id": int(chat), "first_name": "Cineva", "type": "private"},
            "date": 1800000000,
            "text": text_,
            "entities": [{"offset": 0, "length": len(text_.split()[0]), "type": "bot_command"}],
        },
    }
