"""Contul clientului (F7.3, docs/19 §19.3 pasul 1: „clientul primește linkul de activare după plată”).

`invita` creează invitația și cere emailul cu linkul (efect de sistem, idempotent); `activeaza` creează
utilizatorul de client cu parola aleasă de el (regulile de parolă din F1.5) și închide invitația. Jetonul:
256 de biți, doar SHA-256 în bază, valabil 7 zile, o singură folosire."""

import datetime as dt
import hashlib
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.conturi import Actor, DateInvalide, Rol, creeaza_utilizator
from app.db import sesiune_agentie
from app.operare import audit, evenimente
from app.operare.efecte import sistem
from app.portal.modele import Invitatie

VALABILITATE = dt.timedelta(days=7)
ROLURI_INVITABILE = (Rol.CLIENT_TITULAR, Rol.CLIENT_APROBATOR, Rol.CLIENT_VIZITATOR)


class InvitatieInvalida(ValueError):
    pass


def _hash(jeton: str) -> str:
    return hashlib.sha256(jeton.encode()).hexdigest()


def invita(
    db: Session,
    tenant_id: uuid.UUID,
    email: str,
    *,
    rol: Rol = Rol.CLIENT_TITULAR,
    creat_de: uuid.UUID | None = None,
    motiv: str = "manual",
) -> Invitatie:
    """Invitația și emailul cu linkul de activare. `motiv` intră în cheia emailului (de ex.
    `plata:<abonament>`):
    aceeași cauză nu trimite două invitații."""
    if rol not in ROLURI_INVITABILE:
        raise InvitatieInvalida("se invită doar roluri de client")
    email = email.strip().lower()
    jeton = secrets.token_urlsafe(32)
    inv = Invitatie(
        tenant_id=tenant_id,
        email=email,
        rol=rol.value,
        jeton_hash=_hash(jeton),
        expira_la=dt.datetime.now(dt.UTC) + VALABILITATE,
        creat_de=creat_de,
    )
    db.add(inv)
    db.flush()
    link = get_settings().portal_url.rstrip("/") + "/activare/" + jeton
    sistem.cere(
        db,
        "email",
        cheie=f"invitatie:{tenant_id}:{motiv}:{email}",
        tenant_id=tenant_id,
        payload={
            "catre": email,
            "subiect": "Activează-ți contul AMA",
            "text": f"Contul firmei tale este gata. Alege o parolă și intră în portal:\n{link}\n\n"
            "Linkul este valabil 7 zile.",
        },
    )
    audit.record(
        db,
        "invitatie.creata",
        obiect_tip="invitatie",
        obiect_id=inv.id,
        tenant_id=tenant_id,
        utilizator_id=creat_de,
        actor_tip="utilizator" if creat_de else "sistem",
        detalii={"rol": rol.value},
    )
    return inv


def dupa_jeton(db: Session, jeton: str) -> Invitatie | None:
    """Invitația valabilă (nefolosită, neexpirată) a jetonului. Contextul de agenție: încă nu există
    sesiune."""
    if not 20 <= len(jeton) <= 100:
        return None
    inv = db.execute(select(Invitatie).where(Invitatie.jeton_hash == _hash(jeton))).scalar_one_or_none()
    if inv is None or inv.folosita_la is not None or inv.expira_la < dt.datetime.now(dt.UTC):
        return None
    return inv


def activeaza(jeton: str, *, parola: str, nume_afisat: str) -> uuid.UUID:
    """Creează utilizatorul de client și închide invitația. Aruncă `InvitatieInvalida` / `DateInvalide`."""
    with sesiune_agentie() as db:
        inv = dupa_jeton(db, jeton)
        if inv is None:
            raise InvitatieInvalida("Linkul de activare nu este valid sau a expirat.")
        db.execute(select(Invitatie).where(Invitatie.id == inv.id).with_for_update())
        u = creeaza_utilizator(
            db,
            email=inv.email,
            parola=parola,
            nume_afisat=nume_afisat or inv.email,
            rol=Rol(inv.rol),
            tenant_id=inv.tenant_id,
            actor=Actor(None, None, "sistem"),
        )
        inv.folosita_la, inv.utilizator_id = dt.datetime.now(dt.UTC), u.id
        evenimente.emite(
            db,
            "client.cont_activat",
            sursa="portal",
            obiect_tip="utilizator",
            obiect_id=u.id,
            tenant_id=inv.tenant_id,
            utilizator_id=u.id,
        )
        return u.id


__all__ = ["DateInvalide", "InvitatieInvalida", "activeaza", "dupa_jeton", "invita"]
