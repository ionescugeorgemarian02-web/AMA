"""F1.10 — contractul cu Telegram Bot API: forma cererilor trimise și a răspunsurilor primite.

SIMULAT: transportul este `httpx.MockTransport`; răspunsurile au forma celor din documentația Bot API
(https://core.telegram.org/bots/api). Nu există apeluri de rețea reale (AGENTS.md)."""

import json
import logging
from typing import Any

import httpx
import pytest

from app.connectors.telegram import TelegramClient, TelegramEroare
from app.connectors.telegram.cli import main as cli_main
from app.connectors.telegram.modele import Actualizare

TOKEN = "123456:" + "T" * 35


def client_cu(handler: Any) -> TelegramClient:
    return TelegramClient(TOKEN, transport=httpx.MockTransport(handler))


def test_send_message_formeaza_cererea_corect_si_intoarce_message_id() -> None:
    vazute: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        vazute.append(req)
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "message_id": 77,
                    "from": {"id": 123456, "is_bot": True, "first_name": "AMA", "username": "ama_bot"},
                    "chat": {"id": 424242, "first_name": "Prop", "type": "private"},
                    "date": 1800000000,
                    "text": "salut",
                },
            },
        )

    assert client_cu(handler).send_message(424242, "salut") == 77
    (req,) = vazute
    assert req.method == "POST" and req.url.host == "api.telegram.org"
    assert req.url.path == f"/bot{TOKEN}/sendMessage"
    corp = json.loads(req.content)
    assert corp == {"chat_id": 424242, "text": "salut", "disable_web_page_preview": True}
    assert "parse_mode" not in corp  # text simplu: nimic din mesaj nu este interpretat


def test_mesajul_prea_lung_este_taiat_la_limita_telegram() -> None:
    vazute: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        vazute.append(req)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    client_cu(handler).send_message(1, "x" * 5000)
    assert len(json.loads(vazute[0].content)["text"]) == 4096


def test_eroare_a_api_ului_devine_telegram_eroare_fara_jeton_in_mesaj() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"},
        )

    with pytest.raises(TelegramEroare) as e:
        client_cu(handler).send_message(1, "x")
    assert "403" in str(e.value) and "blocked" in str(e.value) and TOKEN not in str(e.value)


def test_eroare_de_retea_si_raspuns_nevalid_nu_scurg_adresa_cu_jeton() -> None:
    def cade(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("conexiune refuzată", request=req)

    with pytest.raises(TelegramEroare) as e1:
        client_cu(cade).send_message(1, "x")
    assert TOKEN not in str(e1.value) and "ConnectError" in str(e1.value)

    with pytest.raises(TelegramEroare) as e2:
        client_cu(lambda r: httpx.Response(502, text="<html>Bad Gateway</html>")).send_message(1, "x")
    assert TOKEN not in str(e2.value) and "502" in str(e2.value)


def test_jetonul_nu_ajunge_in_jurnale_nici_la_nivel_info(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    client_cu(lambda r: httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})).send_message(
        1, "x"
    )
    assert TOKEN not in caplog.text


def test_set_webhook_trimite_adresa_secretul_si_doar_mesajele() -> None:
    vazute: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        vazute.append(req)
        return httpx.Response(200, json={"ok": True, "result": True, "description": "Webhook was set"})

    assert client_cu(handler).set_webhook("https://app.exemplu.ro/telegram/webhook", "s" * 32) is True
    corp = json.loads(vazute[0].content)
    assert vazute[0].url.path.endswith("/setWebhook")
    assert corp["url"] == "https://app.exemplu.ro/telegram/webhook" and corp["secret_token"] == "s" * 32
    assert corp["allowed_updates"] == ["message"]


def test_get_webhook_info_si_delete_webhook() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/getWebhookInfo"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "url": "https://x.example/telegram/webhook",
                        "has_custom_certificate": False,
                        "pending_update_count": 2,
                    },
                },
            )
        return httpx.Response(200, json={"ok": True, "result": True})

    c = client_cu(handler)
    assert c.get_webhook_info()["pending_update_count"] == 2
    assert c.delete_webhook() is True


def test_o_actualizare_reala_se_analizeaza_si_campurile_in_plus_se_ignora() -> None:
    brut = {
        "update_id": 10000,
        "message": {
            "message_id": 1365,
            "from": {"id": 424242, "is_bot": False, "first_name": "Prop", "language_code": "ro"},
            "chat": {"id": 424242, "first_name": "Prop", "type": "private"},
            "date": 1800000000,
            "text": "/stare",
            "entities": [{"offset": 0, "length": 6, "type": "bot_command"}],
        },
    }
    u = Actualizare.model_validate(brut)
    assert u.update_id == 10000 and u.message and u.message.chat.id == 424242 and u.message.text == "/stare"


def test_actualizare_fara_mesaj_text_se_analizeaza_dar_fara_text() -> None:
    u = Actualizare.model_validate({"update_id": 1, "edited_message": {"message_id": 1}})
    assert u.message is None
    u2 = Actualizare.model_validate(
        {
            "update_id": 2,
            "message": {"message_id": 3, "chat": {"id": 5, "type": "private"}, "sticker": {"file_id": "x"}},
        }
    )
    assert u2.message and u2.message.text is None


def test_actualizare_invalida_este_respinsa_de_model() -> None:
    from pydantic import ValidationError

    for rau in ({}, {"update_id": "abc"}, {"update_id": 1, "message": {"message_id": 1}}):
        with pytest.raises(ValidationError):
            Actualizare.model_validate(rau)


# ---- comanda de gestiune (CLI) ----------------------------------------------------------------------------


def test_cli_seteaza_webhook_info_si_sterge(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("AMA_TELEGRAM_WEBHOOK_SECRET", "w" * 32)
    get_settings.cache_clear()
    vazute: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        vazute.append(req.url.path.rsplit("/", 1)[1])
        if vazute[-1] == "getWebhookInfo":
            return httpx.Response(200, json={"ok": True, "result": {"url": "", "pending_update_count": 0}})
        return httpx.Response(200, json={"ok": True, "result": True})

    c = client_cu(handler)
    assert cli_main(["seteaza-webhook", "--url", "https://app.exemplu.ro/telegram/webhook"], client=c) == 0
    assert cli_main(["info"], client=c) == 0
    assert cli_main(["sterge-webhook"], client=c) == 0
    assert vazute == ["setWebhook", "getWebhookInfo", "deleteWebhook"]
    iesire = capsys.readouterr().out
    assert "Webhook înregistrat" in iesire and "(niciunul)" in iesire and "Webhook șters" in iesire
    assert TOKEN not in iesire and "w" * 32 not in iesire
    get_settings.cache_clear()


def test_cli_refuza_adresa_nehttps_si_secretul_lipsa(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.config import get_settings

    c = client_cu(lambda r: httpx.Response(200, json={"ok": True, "result": True}))
    monkeypatch.setenv("AMA_TELEGRAM_WEBHOOK_SECRET", "w" * 32)
    get_settings.cache_clear()
    assert cli_main(["seteaza-webhook", "--url", "http://nesigur.example/x"], client=c) == 2
    monkeypatch.delenv("AMA_TELEGRAM_WEBHOOK_SECRET")
    get_settings.cache_clear()
    assert cli_main(["seteaza-webhook", "--url", "https://app.exemplu.ro/telegram/webhook"], client=c) == 2
    assert "16 caractere" in capsys.readouterr().err
    get_settings.cache_clear()


def test_cli_raporteaza_refuzul_telegram_cu_cod_de_iesire_1(capsys: pytest.CaptureFixture[str]) -> None:
    c = client_cu(
        lambda r: httpx.Response(401, json={"ok": False, "error_code": 401, "description": "Unauthorized"})
    )
    assert cli_main(["info"], client=c) == 1
    assert "Unauthorized" in capsys.readouterr().err
