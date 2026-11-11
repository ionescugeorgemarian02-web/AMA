"""Operații asupra conturilor: clienți, utilizatori, roluri, alocări.

Fiecare scrie audit și eveniment în aceeași tranzacție. Permisiunile se verifică aici, nu doar în rute."""

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.conturi import parole, sesiuni
from app.conturi.modele import Alocare, Apartenenta, Client, Utilizator
from app.conturi.roluri import ROLURI_AGENTIE, ROLURI_CLIENT, Permisiune, Rol, este_agentie, poate
from app.operare import audit, evenimente

EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,}$")


class PermisiuneRefuzata(Exception):
    pass


class DateInvalide(ValueError):
    pass


@dataclass(frozen=True)
class Actor:
    """Cine face operația. `rol=None` înseamnă proces de sistem de încredere (CLI de instalare); nu se
    construiește din date primite de la utilizator."""

    utilizator_id: uuid.UUID | None
    rol: Rol | None = None
    actor_tip: str = "utilizator"

    @classmethod
    def cli(cls) -> "Actor":
        return cls(None, None, "cli")

    def poate(self, permisiune: Permisiune) -> bool:
        return self.actor_tip == "cli" or (self.rol is not None and poate(self.rol, permisiune))


def _cere(actor: Actor, permisiune: Permisiune) -> None:
    if not actor.poate(permisiune):
        raise PermisiuneRefuzata(permisiune.value)


def _audit(db: Session, actor: Actor, actiune: str, **kw: object) -> None:
    audit.record(db, actiune, utilizator_id=actor.utilizator_id, actor_tip=actor.actor_tip, **kw)  # type: ignore[arg-type]


def creeaza_client(db: Session, nume: str, *, actor: Actor) -> Client:
    _cere(actor, Permisiune.CLIENTI_GESTIONEAZA)
    nume = nume.strip()
    if not 1 <= len(nume) <= 200:
        raise DateInvalide("Numele clientului trebuie să aibă între 1 și 200 de caractere.")
    client = Client(nume=nume)
    db.add(client)
    db.flush()
    _audit(db, actor, "client.creat", obiect_tip="client", obiect_id=client.id, tenant_id=client.id)
    evenimente.emite(
        db,
        "client.creat",
        sursa="conturi",
        obiect_tip="client",
        obiect_id=client.id,
        tenant_id=client.id,
        utilizator_id=actor.utilizator_id,
    )
    return client


def lista_clienti(db: Session) -> list[Client]:
    """Clienții activi pe care contextul sesiunii îi poate vedea (RLS), după nume."""
    return list(db.execute(select(Client).where(Client.sters_la.is_(None)).order_by(Client.nume)).scalars())


def cauta_clienti(db: Session, text: str) -> list[Client]:
    """Clienți după identificator (UUID) sau după nume exact, fără diferență între litere mari și mici."""
    text = text.strip()
    if not text:
        return []
    try:
        id_ = uuid.UUID(text)
    except ValueError:
        id_ = None
    return [c for c in lista_clienti(db) if c.id == id_ or c.nume.casefold() == text.casefold()]


def _verifica_rol_si_client(rol: Rol, tenant_id: uuid.UUID | None) -> None:
    if rol in ROLURI_AGENTIE and tenant_id is not None:
        raise DateInvalide("Rolurile de agenție nu aparțin unui client.")
    if rol in ROLURI_CLIENT and tenant_id is None:
        raise DateInvalide("Rolurile de client cer un client.")


def creeaza_utilizator(
    db: Session,
    *,
    email: str,
    parola: str,
    nume_afisat: str,
    rol: Rol,
    tenant_id: uuid.UUID | None,
    actor: Actor,
) -> Utilizator:
    _cere(actor, Permisiune.UTILIZATORI_GESTIONEAZA)
    email = email.strip().lower()
    if not EMAIL.match(email):
        raise DateInvalide("Adresa de email nu este validă.")
    _verifica_rol_si_client(rol, tenant_id)
    try:
        parole.valideaza(parola, email)
    except parole.ParolaInvalida as exc:
        raise DateInvalide(str(exc)) from exc
    if db.execute(select(Utilizator.id).where(Utilizator.email == email)).first():
        raise DateInvalide("Există deja un utilizator cu această adresă.")
    utilizator = Utilizator(
        email=email, nume_afisat=nume_afisat.strip() or email, parola_hash=parole.hash_parola(parola)
    )
    db.add(utilizator)
    db.flush()
    db.add(Apartenenta(utilizator_id=utilizator.id, tenant_id=tenant_id, rol=rol.value))
    db.flush()
    detalii = {"rol": rol.value}
    _audit(
        db,
        actor,
        "utilizator.creat",
        obiect_tip="utilizator",
        obiect_id=utilizator.id,
        tenant_id=tenant_id,
        detalii=detalii,
    )
    evenimente.emite(
        db,
        "utilizator.creat",
        sursa="conturi",
        obiect_tip="utilizator",
        obiect_id=utilizator.id,
        tenant_id=tenant_id,
        utilizator_id=actor.utilizator_id,
        date=detalii,
    )
    return utilizator


def schimba_rol(
    db: Session, utilizator_id: uuid.UUID, rol_nou: Rol, tenant_id: uuid.UUID | None, *, actor: Actor
) -> None:
    _cere(actor, Permisiune.UTILIZATORI_GESTIONEAZA)
    if actor.utilizator_id == utilizator_id:
        raise DateInvalide("Nu îți poți schimba propriul rol.")
    _verifica_rol_si_client(rol_nou, tenant_id)
    ap = db.execute(
        select(Apartenenta).where(Apartenenta.utilizator_id == utilizator_id, Apartenenta.sters_la.is_(None))
    ).scalar_one_or_none()
    if ap is None:
        raise DateInvalide("Utilizatorul nu are o apartenență activă.")
    vechi = {"rol": ap.rol, "tenant_id": str(ap.tenant_id) if ap.tenant_id else None}
    ap.rol, ap.tenant_id = rol_nou.value, tenant_id
    db.flush()
    sesiuni.revoca_utilizator(db, utilizator_id)  # drepturile noi se aplică la următoarea autentificare
    detalii = {
        "de_la": vechi,
        "la": {"rol": rol_nou.value, "tenant_id": str(tenant_id) if tenant_id else None},
    }
    _audit(
        db,
        actor,
        "rol.schimbat",
        obiect_tip="utilizator",
        obiect_id=utilizator_id,
        tenant_id=tenant_id,
        detalii=detalii,
    )
    evenimente.emite(
        db,
        "rol.schimbat",
        sursa="conturi",
        obiect_tip="utilizator",
        obiect_id=utilizator_id,
        tenant_id=tenant_id,
        utilizator_id=actor.utilizator_id,
        date=detalii,
    )


def aloca_operator(db: Session, utilizator_id: uuid.UUID, tenant_id: uuid.UUID, *, actor: Actor) -> None:
    _cere(actor, Permisiune.UTILIZATORI_GESTIONEAZA)
    ap = db.execute(
        select(Apartenenta).where(Apartenenta.utilizator_id == utilizator_id, Apartenenta.sters_la.is_(None))
    ).scalar_one_or_none()
    if ap is None or not este_agentie(ap.rol) or ap.rol == Rol.PROPRIETAR.value:
        raise DateInvalide("Doar operatorii și analiștii se alocă pe clienți.")
    db.add(Alocare(utilizator_id=utilizator_id, tenant_id=tenant_id))
    db.flush()
    _audit(db, actor, "alocare.creata", obiect_tip="utilizator", obiect_id=utilizator_id, tenant_id=tenant_id)
    evenimente.emite(
        db,
        "alocare.creata",
        sursa="conturi",
        obiect_tip="utilizator",
        obiect_id=utilizator_id,
        tenant_id=tenant_id,
        utilizator_id=actor.utilizator_id,
    )
