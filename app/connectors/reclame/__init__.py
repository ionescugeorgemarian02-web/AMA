"""Conectorii conturilor de reclame (F13). Ca orice conector, se importă DOAR din executorul de efecte
(`app.operare.efecte.reclame`) și din teste (garda `check_efecte`).

Cititorii reali se încarcă la cerere pentru platformele din `AMA_RECLAME_CONECTORI` (de ex. „meta,google”);
în teste se înregistrează explicit, pe platforme simulate.
"""

import importlib
import uuid
from typing import Any, Protocol, runtime_checkable

from app.connectors.contract import CititorReclame, EfectSistem, RezultatPlatforma

FABRICI: dict[str, str] = {
    "meta": "app.connectors.reclame.meta:ContMeta",
    "google": "app.connectors.reclame.google:ContGoogle",
}
_cititori: dict[str, CititorReclame] = {}


def _activi() -> set[str]:
    from app.config import get_settings

    return {c.strip() for c in get_settings().reclame_conectori.split(",") if c.strip()}


@runtime_checkable
class ContReclameApi(CititorReclame, Protocol):
    """Adaptorul complet al unei platforme: citire (F13.1–F13.2) și scriere (F13.4)."""

    def scrie(self, tenant_id: uuid.UUID, payload: dict[str, Any]) -> RezultatPlatforma: ...


class Executant:
    """Conectorul de sistem pentru efectele `reclama` (D-008): alege adaptorul după `payload["platforma"]`."""

    def trimite(self, efect: EfectSistem) -> RezultatPlatforma:
        from app.operare.motor import EroareDefinitiva

        if efect.tenant_id is None:
            raise EroareDefinitiva("efectul de reclame cere clientul")
        c = cititor_pentru(str(efect.payload.get("platforma")))
        if not isinstance(c, ContReclameApi):
            raise EroareDefinitiva(f"platforma „{efect.payload.get('platforma')}” nu are conector de scriere")
        return c.scrie(efect.tenant_id, efect.payload)


EXECUTANT = Executant()


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
