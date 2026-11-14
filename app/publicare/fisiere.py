"""Fișierul unei versiuni de conținut (F9.6, F9.7): primul activ din conținut, cu calea lui din biblioteca
media și eticheta AI din pașaport (G11, 15.6)."""

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app import media, validare


@dataclass(frozen=True)
class Fisier:
    cale: str
    video: bool
    eticheta_ai: dict[str, bool]  # pe canal, din pașaport (gol: fără pașaport)


def al_continutului(db: Session, c: validare.Continut) -> Fisier | None:
    activ_id = next((a.get("activ_id") for a in c.active if a.get("activ_id")), None)
    if not activ_id:
        return None
    a = media.biblioteca.citeste_activ(db, uuid.UUID(str(activ_id)))
    if a is None:
        return None
    pas = media.provenienta.al_activului(db, a.id)
    etichete = (pas.continut.get("etichete") or {}) if pas else {}
    return Fisier(
        a.cale,
        a.mime.startswith("video/"),
        {k: bool((v or {}).get("eticheta_ai")) for k, v in etichete.items()},
    )
