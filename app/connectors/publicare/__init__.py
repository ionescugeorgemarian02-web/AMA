"""Conectorii de publicare prin API (F9). Se importă DOAR din executorul de efecte și din teste (garda
`check_efecte`).

    from app.connectors.publicare import ConectorPublicare, Token, Limite, StarePostare
"""

from app.connectors.contract import ETICHETE_STARE, Limite, StarePostare, Token
from app.connectors.publicare.baza import (
    ClientHttp,
    ConectorPublicare,
    DepozitBaza,
    DepozitInMemorie,
    DepozitTokenuri,
    clasifica,
    text_postare,
    token_sau_autentificare,
)

__all__ = [
    "ETICHETE_STARE",
    "ClientHttp",
    "ConectorPublicare",
    "DepozitBaza",
    "DepozitInMemorie",
    "DepozitTokenuri",
    "Limite",
    "StarePostare",
    "Token",
    "clasifica",
    "text_postare",
    "token_sau_autentificare",
]
