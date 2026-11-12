"""Sesiuni pe server (21.3). În cookie e un jeton aleator de 256 de biți; în bază doar SHA-256 al lui."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.conturi import criptare
from app.conturi.modele import Apartenenta, Sesiune, Utilizator
from app.conturi.roluri import Rol, are_scop_agentie, este_agentie, rol_valid
from app.db import ContextDb

ACTUALIZARE_ACTIVITATE = timedelta(seconds=60)  # nu scriem la fiecare cerere


@dataclass(frozen=True)
class SesiuneCurenta:
    sesiune_id: uuid.UUID
    utilizator_id: uuid.UUID
    email: str
    nume_afisat: str
    rol: Rol
    tenant_apartenenta: uuid.UUID | None  # clientul utilizatorului de client; NULL pentru agenție
    tenant_activ_id: uuid.UUID | None  # clientul ales de un utilizator de agenție
    mfa_verificat: bool
    totp_activ: bool
    csrf_token: str

    @property
    def tenant_id(self) -> uuid.UUID | None:
        """Clientul în care lucrează acum. Un utilizator de client nu poate lucra în alt client."""
        return self.tenant_activ_id if este_agentie(self.rol) else self.tenant_apartenenta

    def context_db(self) -> ContextDb:
        return ContextDb(
            tenant_id=self.tenant_id, user_id=self.utilizator_id, agency=are_scop_agentie(self.rol)
        )


def acum() -> datetime:
    return datetime.now(UTC)


def creeaza(
    db: Session,
    utilizator_id: uuid.UUID,
    *,
    mfa_verificat: bool,
    ip: str | None,
    user_agent: str | None,
    tenant_activ_id: uuid.UUID | None = None,
) -> str:
    """Creează o sesiune nouă și întoarce jetonul (singura dată când există în clar)."""
    s = get_settings()
    t = acum()
    durata = (
        timedelta(hours=s.session_absolute_hours)
        if mfa_verificat
        else timedelta(minutes=s.session_pending_minutes)
    )
    jeton = criptare.jeton_nou()
    db.add(
        Sesiune(
            token_hash=criptare.hash_jeton(jeton),
            utilizator_id=utilizator_id,
            tenant_activ_id=tenant_activ_id,
            mfa_verificat=mfa_verificat,
            csrf_token=criptare.jeton_nou(),
            creat_la=t,
            ultima_activitate=t,
            expira_absolut=t + durata,
            ip=ip,
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    db.flush()
    return jeton


def incarca(db: Session, jeton: str) -> SesiuneCurenta | None:
    """Sesiunea pentru jeton, dacă este validă (nerevocată, neexpirată, utilizator activ, cu apartenență)."""
    if not jeton or len(jeton) > 200:
        return None
    rand = db.execute(
        select(Sesiune, Utilizator, Apartenenta)
        .join(Utilizator, Utilizator.id == Sesiune.utilizator_id)
        .join(Apartenenta, (Apartenenta.utilizator_id == Utilizator.id) & Apartenenta.sters_la.is_(None))
        .where(Sesiune.token_hash == criptare.hash_jeton(jeton))
    ).first()
    if rand is None:
        return None
    sesiune, utilizator, apartenenta = rand
    rol = rol_valid(apartenenta.rol)
    t = acum()
    s = get_settings()
    if (
        rol is None
        or sesiune.revocata_la is not None
        or t >= sesiune.expira_absolut
        or utilizator.stare != "activ"
        or utilizator.sters_la is not None
    ):
        return None
    if sesiune.mfa_verificat and t - sesiune.ultima_activitate >= timedelta(minutes=s.session_idle_minutes):
        return None  # inactivă prea mult
    if t - sesiune.ultima_activitate >= ACTUALIZARE_ACTIVITATE:
        db.execute(update(Sesiune).where(Sesiune.id == sesiune.id).values(ultima_activitate=t))
    return SesiuneCurenta(
        sesiune_id=sesiune.id,
        utilizator_id=utilizator.id,
        email=str(utilizator.email),
        nume_afisat=utilizator.nume_afisat,
        rol=rol,
        tenant_apartenenta=apartenenta.tenant_id,
        tenant_activ_id=sesiune.tenant_activ_id,
        mfa_verificat=sesiune.mfa_verificat,
        totp_activ=utilizator.totp_activ,
        csrf_token=sesiune.csrf_token,
    )


def revoca(db: Session, sesiune_id: uuid.UUID) -> None:
    db.execute(
        update(Sesiune)
        .where(Sesiune.id == sesiune_id, Sesiune.revocata_la.is_(None))
        .values(revocata_la=acum())
    )


def revoca_utilizator(db: Session, utilizator_id: uuid.UUID) -> None:
    """Toate sesiunile unui utilizator (schimbare de rol, parolă, blocare)."""
    db.execute(
        update(Sesiune)
        .where(Sesiune.utilizator_id == utilizator_id, Sesiune.revocata_la.is_(None))
        .values(revocata_la=acum())
    )


def roteste(
    db: Session, veche: SesiuneCurenta, *, mfa_verificat: bool, ip: str | None, user_agent: str | None
) -> str:
    """Rotire: sesiunea veche este revocată și apare una nouă, cu jeton nou (fără fixarea sesiunii)."""
    revoca(db, veche.sesiune_id)
    return creeaza(
        db,
        veche.utilizator_id,
        mfa_verificat=mfa_verificat,
        ip=ip,
        user_agent=user_agent,
        tenant_activ_id=veche.tenant_activ_id,
    )


def seteaza_tenant_activ(db: Session, sesiune_id: uuid.UUID, tenant_id: uuid.UUID | None) -> None:
    db.execute(update(Sesiune).where(Sesiune.id == sesiune_id).values(tenant_activ_id=tenant_id))
