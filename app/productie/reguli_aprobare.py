"""Regulile cererilor de aprobare (7.3, 18.3, 19.4), nucleu pur: fără bază de date și fără HTTP.

- Stări: în așteptare → aprobat | respins | expirat | anulat. Nimic nu mai iese din cele patru finale.
- Cine poate decide: o cerere „operator” o decid rolurile de agenție cu dreptul de a aproba (proprietar,
  operator); una „client” o decid doar rolurile de client cu acest drept (titular, aprobator). Analistul
  și vizitatorul nu decid.
- Termenul: 48 de ore de la creare (configurabil), dar nu după termenul livrabilului (slotul de publicare);
  reamintirea vine cu 24 de ore înainte de termen (sau la jumătatea intervalului, dacă e mai scurt).
- Fără aprobare automată: o cerere neprimită la timp devine `expirat`, niciodată `aprobat`.
"""

import datetime as dt
from enum import StrEnum

from app.conturi.roluri import Permisiune, Rol, este_agentie, poate, rol_valid


class StareAprobare(StrEnum):
    IN_ASTEPTARE = "in_asteptare"
    APROBAT = "aprobat"
    RESPINS = "respins"
    EXPIRAT = "expirat"
    ANULAT = "anulat"  # înlocuită de o versiune nouă a livrabilului, sau livrabilul a fost anulat


class Decident(StrEnum):
    OPERATOR = "operator"
    CLIENT = "client"


class Hotarare(StrEnum):
    APROBAT = "aprobat"
    RESPINS = "respins"


TRANZITII: dict[StareAprobare, frozenset[StareAprobare]] = {
    StareAprobare.IN_ASTEPTARE: frozenset(
        {StareAprobare.APROBAT, StareAprobare.RESPINS, StareAprobare.EXPIRAT, StareAprobare.ANULAT}
    ),
    StareAprobare.APROBAT: frozenset(),
    StareAprobare.RESPINS: frozenset(),
    StareAprobare.EXPIRAT: frozenset(),
    StareAprobare.ANULAT: frozenset(),
}

ETICHETE_STARE: dict[str, str] = {
    "in_asteptare": "în așteptare",
    "aprobat": "aprobat",
    "respins": "respins",
    "expirat": "expirat",
    "anulat": "anulat",
}
ETICHETE_DECIDENT: dict[str, str] = {"operator": "operator", "client": "client"}

# Motivele standard de respingere (18.3). Motivul intră direct în învățare (F11): de aceea e o listă închisă.
MOTIVE_RESPINGERE: dict[str, str] = {
    "fapt_gresit": "Fapt greșit",
    "ton_nepotrivit": "Ton nepotrivit",
    "prea_lung": "Prea lung",
    "hook_slab": "Hook slab",
    "subiect_nepotrivit": "Subiect nepotrivit",
    "vizual_slab": "Vizual slab",
    "conformitate": "Problemă de conformitate",
    "altceva": "Altceva",
}
MOTIV_MINIM = 3
MOTIV_MAXIM = 300


def poate_decide(rol: Rol | str, decident: Decident) -> bool:
    """Rolul `rol` poate decide o cerere adresată lui `decident`? Refuz implicit pentru roluri necunoscute."""
    r = rol_valid(str(rol))
    if r is None or not poate(r, Permisiune.LIVRABIL_APROBA):
        return False
    return este_agentie(r) == (decident is Decident.OPERATOR)


def este_finala(stare: StareAprobare) -> bool:
    return not TRANZITII[stare]


class TermenTrecut(ValueError):
    """Termenul cererii ar fi deja trecut la creare (slotul livrabilului a trecut)."""


def calculeaza_termene(
    acum: dt.datetime,
    termen_livrabil: dt.datetime | None,
    *,
    termen_ore: int,
    reamintire_ore: int,
) -> tuple[dt.datetime, dt.datetime]:
    """(termenul cererii, momentul reamintirii). Aruncă `TermenTrecut` dacă slotul a trecut deja."""
    termen = acum + dt.timedelta(hours=termen_ore)
    if termen_livrabil is not None and termen_livrabil < termen:
        termen = termen_livrabil
    if termen <= acum:
        raise TermenTrecut("termenul livrabilului a trecut înainte de cererea de aprobare")
    interval = termen - acum
    inainte = min(dt.timedelta(hours=reamintire_ore), interval / 2)
    return termen, termen - inainte


def motiv_valid(motiv: str) -> bool:
    return MOTIV_MINIM <= len(motiv.strip()) <= MOTIV_MAXIM
