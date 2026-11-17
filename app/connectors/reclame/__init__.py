"""Conectorii conturilor de reclame (F13). Ca orice conector, se importă DOAR din executorul de efecte
(`app.operare.efecte.reclame`) și din teste (garda `check_efecte`).

Cititorii reali se încarcă la cerere pentru platformele din `AMA_RECLAME_CONECTORI` (de ex. „meta,google”);
în teste se înregistrează explicit, pe platforme simulate.
"""

import importlib

from app.connectors.contract import CititorReclame

FABRICI: dict[str, str] = {
    "meta": "app.connectors.reclame.meta:ContMeta",
    "google": "app.connectors.reclame.google:ContGoogle",
}
_cititori: dict[str, CititorReclame] = {}


def _activi() -> set[str]:
    from app.config import get_settings

    return {c.strip() for c in get_settings().reclame_conectori.split(",") if c.strip()}


def inregistreaza(platforma: str, cititor: CititorReclame) -> None:
    _cititori[platforma] = cititor


def cititor_pentru(platforma: str) -> CititorReclame | None:
    c = _cititori.get(platforma)
    if c is not None or platforma not in _activi() or platforma not in FABRICI:
        return c
    modul, nume = FABRICI[platforma].split(":")
    nou: CititorReclame = getattr(importlib.import_module(modul), nume).din_setari()
    inregistreaza(platforma, nou)
    return nou


def uita_tot() -> None:
    """Golește registrul (teste)."""
    _cititori.clear()
