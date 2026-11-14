"""Cititorii de metrici ai platformelor (F10.1, K1). Ca orice conector, se importă DOAR din executorul de
efecte (`app.operare.efecte.metrici`) și din teste (garda `check_efecte`).

Un cititor face un singur lucru: întoarce cifrele unei postări, așa cum le dă platforma acum
(`contract.Metrici`). Nu scrie nimic la platformă. Refolosește clientul HTTP, clasificarea erorilor și
depozitul de tokenuri ale conectorilor de publicare (F9), fără să îi modifice.

Cititorii reali se încarcă la cerere pentru canalele din `AMA_PUBLICARE_CONECTORI` (aceleași canale care au
conector de publicare activ); în teste se înregistrează explicit, pe platforme simulate.
"""

import importlib
from typing import Any

from app.connectors.contract import CititorMetrici

_registru: dict[str, CititorMetrici] = {}

FABRICI: dict[str, str] = {
    "facebook": "app.connectors.metrici.meta:CititorFacebook",
    "instagram": "app.connectors.metrici.meta:CititorInstagram",
    "youtube": "app.connectors.metrici.youtube:CititorYoutube",
    "linkedin": "app.connectors.metrici.linkedin:CititorLinkedin",
    "linkedin_pagina": "app.connectors.metrici.linkedin:CititorLinkedin.pagina_din_setari",
    "tiktok": "app.connectors.metrici.tiktok:CititorTiktok",
}


def inregistreaza(canal: str, cititor: CititorMetrici) -> None:
    _registru[canal] = cititor


def _incarca(canal: str) -> CititorMetrici | None:
    from app.config import get_settings

    activi = {c.strip() for c in get_settings().publicare_conectori.split(",") if c.strip()}
    if canal not in activi or canal not in FABRICI:
        return None
    modul, cale = FABRICI[canal].split(":")
    obiect: Any = importlib.import_module(modul)
    for parte in cale.split("."):
        obiect = getattr(obiect, parte)
    c: CititorMetrici = obiect() if "." in cale else obiect.din_setari()
    inregistreaza(canal, c)
    return c


def cititor_pentru(canal: str) -> CititorMetrici | None:
    """Cititorul canalului, sau `None`: canalul nu are citire prin API (asistat, blog); cifrele se introduc
    de om (din exportul platformei) sau vin din analiza de trafic proprie."""
    return _registru.get(canal) or _incarca(canal)


def uita_tot() -> None:
    """Golește registrul (teste)."""
    _registru.clear()
