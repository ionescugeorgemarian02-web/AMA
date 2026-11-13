"""Pachetele de context salvate (F4.7): tipurile și persistența. Doar adăugări; un pachet nu se modifică."""

import datetime as dt
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.creier.modele import PachetContextRand
from app.ids import new_id


@dataclass(frozen=True)
class Element:
    """Un element al pachetului: ce este, de unde vine (identificator + versiune) și textul trimis."""

    sectiune: str  # ghid | reguli | fapte | oferte | pasaje
    tip: str  # profil | constrangere | fapt | oferta | pasaj
    id: str
    versiune: int | None
    text: str
    tokeni: int
    detalii: dict[str, Any] = field(default_factory=dict)  # sursă, URL, poziție, scor …


@dataclass(frozen=True)
class PachetContext:
    id: uuid.UUID | None
    tenant_id: uuid.UUID
    livrabil_id: uuid.UUID | None
    tip_sarcina: str
    canal: str | None
    intrebare: str
    la: dt.datetime
    buget_tokeni: int
    tokeni_folositi: int
    depasit: bool
    elemente: tuple[Element, ...]
    lipsuri: tuple[str, ...]  # secțiuni goale spuse explicit (de ex. „ghid_brand”)
    taiate: tuple[dict[str, str], ...]
    amprenta: str
    creat_la: dt.datetime | None = None

    def sectiune(self, nume: str) -> list[Element]:
        return [e for e in self.elemente if e.sectiune == nume]


def continut_canonic(p: PachetContext) -> dict[str, Any]:
    return {
        "tip_sarcina": p.tip_sarcina,
        "canal": p.canal,
        "intrebare": p.intrebare,
        "la": p.la.isoformat(),
        "buget_tokeni": p.buget_tokeni,
        "elemente": [asdict(e) for e in p.elemente],
        "lipsuri": list(p.lipsuri),
        "taiate": list(p.taiate),
    }


def amprenta(continut: dict[str, Any]) -> str:
    """Aceleași intrări → aceeași amprentă (JSON canonic, chei sortate)."""
    return hashlib.sha256(json.dumps(continut, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def amprenta_corecta(p: PachetContext) -> bool:
    """Amprenta păstrată corespunde conținutului pachetului (integritatea instantaneului salvat)."""
    return p.amprenta == amprenta(continut_canonic(p))


def salveaza(db: Session, p: PachetContext, *, utilizator_id: uuid.UUID | None = None) -> PachetContext:
    pid = new_id()
    db.add(
        PachetContextRand(
            id=pid,
            tenant_id=p.tenant_id,
            livrabil_id=p.livrabil_id,
            tip_sarcina=p.tip_sarcina,
            canal=p.canal,
            intrebare=p.intrebare,
            la=p.la,
            buget_tokeni=p.buget_tokeni,
            tokeni_folositi=p.tokeni_folositi,
            depasit=p.depasit,
            amprenta=p.amprenta,
            continut=continut_canonic(p),
            lipsuri=list(p.lipsuri),
            taiate=list(p.taiate),
            creat_de=utilizator_id,
        )
    )
    db.flush()
    r = db.get(PachetContextRand, pid)
    if r is None:
        raise RuntimeError("pachetul tocmai scris nu poate fi citit")
    return _din_rand(r)


def _din_rand(r: PachetContextRand) -> PachetContext:
    c = r.continut
    return PachetContext(
        id=r.id,
        tenant_id=r.tenant_id,
        livrabil_id=r.livrabil_id,
        tip_sarcina=r.tip_sarcina,
        canal=r.canal,
        intrebare=r.intrebare,
        la=r.la,
        buget_tokeni=r.buget_tokeni,
        tokeni_folositi=r.tokeni_folositi,
        depasit=r.depasit,
        elemente=tuple(Element(**e) for e in c.get("elemente", [])),
        lipsuri=tuple(r.lipsuri),
        taiate=tuple(r.taiate),
        amprenta=r.amprenta,
        creat_la=r.creat_la,
    )


def citeste_pachet(db: Session, pachet_id: uuid.UUID) -> PachetContext | None:
    r = db.get(PachetContextRand, pachet_id)
    return None if r is None else _din_rand(r)


def ale_livrabilului(db: Session, livrabil_id: uuid.UUID) -> list[PachetContext]:
    q = (
        select(PachetContextRand)
        .where(PachetContextRand.livrabil_id == livrabil_id)
        .order_by(PachetContextRand.creat_la, PachetContextRand.id)
    )
    return [_din_rand(r) for r in db.execute(q).scalars()]
