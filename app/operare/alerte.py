"""Alerte spre Telegram (22.4). Fațadă subțire: conectorul se importă la apel, ca să nu existe import circular
(botul din `app.connectors.telegram` citește starea din `app.operare`).

`trimite` nu aruncă niciodată: dacă Telegram e oprit, neconfigurat sau căzut, întoarce False și jurnalizează.
Textele nu au voie să conțină secrete sau date personale; apelantul răspunde de ele.
"""

from app.logging import get_logger

log = get_logger("app.alerte")

ETICHETE = {"critic": "CRITIC", "important": "IMPORTANT", "informativ": "INFO"}


def format_mesaj(nivel: str, titlu: str, text: str) -> str:
    return f"[{ETICHETE.get(nivel, nivel.upper())}] {titlu}\n{text}".strip()


def trimite(nivel: str, titlu: str, text: str) -> bool:
    try:
        from app.connectors.telegram import trimite_proprietarului

        return trimite_proprietarului(format_mesaj(nivel, titlu, text))
    except Exception as exc:
        log.warning("alertă Telegram nereușită", extra={"tip_eroare": type(exc).__name__})
        return False
