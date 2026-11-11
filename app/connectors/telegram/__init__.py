"""Conectorul Telegram (F1.10): client Bot API, webhook, comenzi. Vezi docs/specs/F1.10.md.

Alertele de ieșire trec prin `app.operare.alerte.trimite`; aici e doar transportul.
"""

from app.config import get_settings
from app.connectors.telegram.client import TelegramClient, TelegramEroare
from app.logging import get_logger

log = get_logger("app.telegram")

_client: TelegramClient | None = None
_fals: TelegramClient | None = None


def seteaza_client(client: TelegramClient | None) -> None:
    """Pentru teste: înlocuiește clientul (cu transport fals). `None` revine la cel real."""
    global _fals
    _fals = client


def get_client() -> TelegramClient | None:
    """Clientul pentru configurarea curentă; `None` dacă botul nu e configurat (dezactivat)."""
    global _client
    if _fals is not None:
        return _fals
    s = get_settings()
    if not s.telegram_activ:
        return None
    if _client is None:
        _client = TelegramClient(s.telegram_bot_token.get_secret_value())
    return _client


def trimite_proprietarului(text: str) -> bool:
    """Trimite un mesaj în conversația proprietarului. Nu aruncă: eșecul se jurnalizează și întoarce False."""
    s = get_settings()
    client = get_client()
    if client is None or not s.telegram_chat_id.lstrip("-").isdigit():
        return False
    try:
        client.send_message(int(s.telegram_chat_id), text)
        return True
    except TelegramEroare as exc:
        log.warning("Telegram nu a putut fi atins", extra={"eroare": str(exc)[:200]})
        return False


__all__ = ["TelegramClient", "TelegramEroare", "get_client", "seteaza_client", "trimite_proprietarului"]
