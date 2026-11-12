"""Mecanismul comun al extragerilor pe pasaje (F4.9 citate, F4.10 afirmațiile concurenței): fiecare
pasaj al unei surse se
trece o singură dată, per versiune de prompt, prin modelul respectiv; rezultatul se notează în
`creier_extrageri`
(aceeași tabelă ca la fapte: `UNIQUE (pasaj_id, prompt)`), deci reluarea fluxului nu cheamă modelul din
nou pentru
pasajele terminate. Verificările (citat literal, fără date personale) sunt ale fiecărui extractor.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import creier
from app.ids import new_id

PASAJE_PE_LOT = 3
MAXIM_RESPINSE_PASTRATE = 20


@dataclass
class RezultatPasaj:
    pasaj_id: uuid.UUID
    propuse: int = 0
    duplicate: int = 0
    respinse: list[dict[str, str]] = field(default_factory=list)


def pasaje_de_extras(
    db: Session, tenant_id: uuid.UUID, sursa_id: uuid.UUID, prompt: str, limita: int
) -> list[uuid.UUID]:
    """Pasajele sursei care nu au fost încă extrase cu `prompt`."""
    q = (
        select(creier.Pasaj.id)
        .where(
            creier.Pasaj.tenant_id == tenant_id,
            creier.Pasaj.sursa_id == sursa_id,
            ~select(creier.Extragere.id)
            .where(creier.Extragere.pasaj_id == creier.Pasaj.id, creier.Extragere.prompt == prompt)
            .exists(),
        )
        .order_by(creier.Pasaj.document_id, creier.Pasaj.pozitie)
        .limit(limita)
    )
    return list(db.execute(q).scalars())


def deja_extras(db: Session, pasaj_id: uuid.UUID, prompt: str) -> bool:
    return (
        db.execute(
            select(creier.Extragere.id).where(
                creier.Extragere.pasaj_id == pasaj_id, creier.Extragere.prompt == prompt
            )
        ).first()
        is not None
    )


def noteaza(
    db: Session, tenant_id: uuid.UUID, pasaj: Any, prompt: str, r: RezultatPasaj, model: str | None
) -> None:
    db.add(
        creier.Extragere(
            id=new_id(), tenant_id=tenant_id, pasaj_id=pasaj.id, document_id=pasaj.document_id, prompt=prompt,
            propuse=r.propuse, duplicate=r.duplicate, respinse=r.respinse[:MAXIM_RESPINSE_PASTRATE],
            model=model,
        )
    )  # fmt: skip


def rezumat(db: Session, tenant_id: uuid.UUID, sursa_id: uuid.UUID, prompt: str) -> dict[str, int]:
    r = db.execute(
        text(
            "SELECT count(*), COALESCE(sum(e.propuse), 0), COALESCE(sum(e.duplicate), 0), "
            "COALESCE(sum(jsonb_array_length(e.respinse)), 0) FROM creier_extrageri e "
            "JOIN pasaje p ON p.id = e.pasaj_id WHERE e.tenant_id = :t AND p.sursa_id = :s AND e.prompt = :p"
        ),
        {"t": tenant_id, "s": sursa_id, "p": prompt},
    ).one()
    return {"pasaje": int(r[0]), "propuse": int(r[1]), "duplicate": int(r[2]), "respinse": int(r[3])}
