"""Client subțire peste Telegram Bot API (https://core.telegram.org/bots/api): `httpx`, transport injectabil.

Jetonul botului este în calea URL-ului, deci: logger-ul `httpx` este coborât la WARNING (altfel ar scrie
URL-ul complet) și erorile nu poartă niciodată URL-ul sau corpul cererii.
"""

import logging
from typing import Any

import httpx

API = "https://api.telegram.org"
LUNGIME_MAXIMA_MESAJ = 4096

# httpx scrie la INFO „HTTP Request: POST https://api.telegram.org/bot<JETON>/…”.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class TelegramEroare(Exception):
    """Mesajul nu conține jetonul, URL-ul sau textul trimis."""


class TelegramClient:
    def __init__(
        self,
        token: str,
        *,
        transport: httpx.BaseTransport | None = None,
        base_url: str = API,
        timeout: float = 10.0,
    ) -> None:
        if not token:
            raise ValueError("jeton lipsă")
        self._prefix = f"/bot{token}"
        self._http = httpx.Client(base_url=base_url, transport=transport, timeout=timeout)

    def _apel(self, metoda: str, payload: dict[str, Any] | None = None) -> Any:
        try:
            r = self._http.post(f"{self._prefix}/{metoda}", json=payload or {})
        except httpx.HTTPError as exc:
            raise TelegramEroare(f"{metoda}: rețea ({type(exc).__name__})") from None
        try:
            corp = r.json()
        except ValueError:
            raise TelegramEroare(f"{metoda}: răspuns nevalid (HTTP {r.status_code})") from None
        if not isinstance(corp, dict) or not corp.get("ok"):
            cod = corp.get("error_code", r.status_code) if isinstance(corp, dict) else r.status_code
            descriere = str(corp.get("description", ""))[:100] if isinstance(corp, dict) else ""
            raise TelegramEroare(f"{metoda}: {cod} {descriere}".strip())
        return corp.get("result")

    def send_message(self, chat_id: int, text: str) -> int:
        """Trimite text simplu (fără parse_mode: nimic nu este interpretat). Întoarce `message_id`."""
        rez = self._apel(
            "sendMessage",
            {"chat_id": chat_id, "text": text[:LUNGIME_MAXIMA_MESAJ], "disable_web_page_preview": True},
        )
        return int(rez["message_id"])

    def set_webhook(self, url: str, secret_token: str) -> bool:
        return bool(
            self._apel(
                "setWebhook",
                {
                    "url": url,
                    "secret_token": secret_token,
                    "allowed_updates": ["message"],
                    "drop_pending_updates": False,
                },
            )
        )

    def delete_webhook(self) -> bool:
        return bool(self._apel("deleteWebhook", {}))

    def get_webhook_info(self) -> dict[str, Any]:
        rez = self._apel("getWebhookInfo", {})
        return rez if isinstance(rez, dict) else {}

    def close(self) -> None:
        self._http.close()
