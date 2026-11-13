"""Regulile pe client, în bază (F5.4, docs/09 §9.7): pe lângă pachetele comune de reguli, un client poate
avea reguli proprii
(un cuvânt interzis de brand, o mențiune obligatorie). Se supun EXACT aceleiași scheme ca regulile din
fișiere, cu exemple
blocate / care trec, verificate la scriere: o regulă ale cărei exemple nu se comportă ca în declarație nu se
salvează.

Regulile se schimbă doar prin revizuire umană: `utilizator_id` este obligatoriu (coloana `creat_de` nu poate
fi goală), fiecare
schimbare este o versiune nouă (doar adăugare), fiecare scriere lasă urmă în audit. Niciun cod automat nu
apelează aceste funcții
(optimizatorul nu are drept de scriere asupra regulilor).
"""

import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ids import new_id
from app.operare import audit
from app.validare import reguli
from app.validare.modele import RegulaClient
from app.validare.reguli import Regula


class RegulaClientInvalida(ValueError):
    def __init__(self, probleme: list[str]) -> None:
        super().__init__("; ".join(probleme))
        self.probleme = probleme


def valideaza(definitie: dict[str, Any]) -> Regula:
    """Schema regulilor din fișiere + exemplele care trebuie să se comporte ca în declarație."""
    try:
        r = Regula.model_validate(definitie)
    except ValidationError as exc:
        raise RegulaClientInvalida(
            [f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()[:5]]
        ) from None
    probleme = reguli.verifica_exemple(r)
    if probleme:
        raise RegulaClientInvalida(probleme)
    return r


def _ultima(db: Session, tenant_id: uuid.UUID, regula_id: str) -> RegulaClient | None:
    return db.execute(
        select(RegulaClient)
        .where(RegulaClient.tenant_id == tenant_id, RegulaClient.regula_id == regula_id)
        .order_by(RegulaClient.versiune.desc())
        .limit(1)
    ).scalar_one_or_none()


def adauga(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    definitie: dict[str, Any],
    utilizator_id: uuid.UUID,
    motiv: str = "",
) -> RegulaClient:
    """O regulă nouă sau o versiune nouă a uneia existente (același `id`). Doar un om
    (`utilizator_id`)."""
    r = valideaza(definitie)
    if r.id in ids_comune():
        raise RegulaClientInvalida(
            [f"{r.id}: identificatorul intră în conflict cu o regulă din pachetele comune"]
        )
    ultima = _ultima(db, tenant_id, r.id)
    rand = RegulaClient(
        id=new_id(), tenant_id=tenant_id, regula_id=r.id, versiune=(ultima.versiune + 1) if ultima else 1,
        definitie=r.model_dump(mode="json"), retrasa=False, motiv=motiv[:500], creat_de=utilizator_id,
    )  # fmt: skip
    db.add(rand)
    db.flush()
    audit.record(
        db,
        "validare.regula_client_adaugata",
        obiect_tip="regula_client",
        obiect_id=rand.id,
        utilizator_id=utilizator_id,
        tenant_id=tenant_id,
        detalii={"regula": r.id, "versiune": rand.versiune, "severitate": r.severitate},
    )
    return rand


def ids_comune() -> set[str]:
    """Identificatorii regulilor din pachetele comune: un client nu le poate redefini."""
    return {r.id for _, r in reguli.toate_regulile()}


def retrage(
    db: Session, *, tenant_id: uuid.UUID, regula_id: str, utilizator_id: uuid.UUID, motiv: str
) -> RegulaClient:
    """Retrage regula (versiune nouă, `retrasa`); istoricul rămâne."""
    ultima = _ultima(db, tenant_id, regula_id)
    if ultima is None or ultima.retrasa:
        raise LookupError(regula_id)
    if len(motiv.strip()) < 3:
        raise ValueError("retragerea cere un motiv")
    rand = RegulaClient(
        id=new_id(), tenant_id=tenant_id, regula_id=regula_id, versiune=ultima.versiune + 1,
        definitie=ultima.definitie, retrasa=True, motiv=motiv.strip()[:500], creat_de=utilizator_id,
    )  # fmt: skip
    db.add(rand)
    db.flush()
    audit.record(
        db,
        "validare.regula_client_retrasa",
        obiect_tip="regula_client",
        obiect_id=rand.id,
        utilizator_id=utilizator_id,
        tenant_id=tenant_id,
        detalii={"regula": regula_id, "versiune": rand.versiune, "motiv": motiv.strip()[:200]},
    )
    return rand


def active(db: Session, tenant_id: uuid.UUID) -> list[tuple[Regula, int]]:
    """Regulile în vigoare ale clientului: ultima versiune a fiecăreia, dacă nu e retrasă. Ordine
    stabilă."""
    ultimele: dict[str, RegulaClient] = {}
    for r in db.execute(
        select(RegulaClient)
        .where(RegulaClient.tenant_id == tenant_id)
        .order_by(RegulaClient.regula_id, RegulaClient.versiune)
    ).scalars():
        ultimele[r.regula_id] = r
    return [(Regula.model_validate(r.definitie), r.versiune) for r in ultimele.values() if not r.retrasa]


def istoric(db: Session, tenant_id: uuid.UUID, regula_id: str) -> list[RegulaClient]:
    return list(
        db.execute(
            select(RegulaClient)
            .where(RegulaClient.tenant_id == tenant_id, RegulaClient.regula_id == regula_id)
            .order_by(RegulaClient.versiune)
        ).scalars()
    )
