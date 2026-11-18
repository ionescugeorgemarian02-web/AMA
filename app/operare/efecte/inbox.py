"""Ușa executorului spre inboxul social (F12.7). Conectorii se cheamă DOAR din `app/operare/efecte` (garda
`check_efecte`), deci și citirea mesajelor trece pe aici. Citirea nu schimbă nimic la platformă.
Răspunsurile și ascunderea (F12.8) sunt efecte de sistem de tipul `mesaj_social`."""

import datetime as dt
from typing import Any

from app.connectors import inbox as conector


def canale() -> tuple[str, ...]:
    return conector.CANALE


def citeste(canal: str, de_la: dt.datetime | None) -> list[dict[str, Any]]:
    """Mesajele și comentariile noi de pe un canal. `LookupError` dacă nu există cititor."""
    c = conector.cititor_pentru(canal)
    if c is None:
        raise LookupError(f"canalul „{canal}” nu are cititor de inbox")
    return [
        {
            "canal": m.canal,
            "id_extern": m.id_extern,
            "tip": m.tip,
            "fir": m.fir,
            "autor": m.autor,
            "text": m.text,
            "primit_la": m.primit_la,
        }
        for m in c.citeste(canal, de_la)
    ]
