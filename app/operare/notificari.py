"""Notificări: niveluri (18.6), rutare pe canale și trimiterea Web Push.

Cum trimiți o notificare din alt modul:

    from app.operare import notificari
    notificari.notifica(notificari.Nivel.IMPORTANT, "Titlu scurt", "Text fără secrete sau date personale.")

Rutarea (pură, testată): critic → push + Telegram; important → push; informativ → rezumat zilnic (substituent:
rezumatul nu există încă, deci nu se trimite nimic acum). Preferințele pe tip (oprit / alt canal) vin
într-un pas ulterior; acum nivelul decide singur canalul.
"""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import sesiune_agentie
from app.logging import get_logger
from app.operare import alerte
from app.operare.tabele import AbonamentPush

log = get_logger("app.notificari")


class Nivel(StrEnum):
    CRITIC = "critic"
    IMPORTANT = "important"
    INFORMATIV = "informativ"


class Canal(StrEnum):
    PUSH = "push"
    TELEGRAM = "telegram"
    REZUMAT_ZILNIC = "rezumat_zilnic"


_RUTARE: dict[Nivel, frozenset[Canal]] = {
    Nivel.CRITIC: frozenset({Canal.PUSH, Canal.TELEGRAM}),
    Nivel.IMPORTANT: frozenset({Canal.PUSH}),
    Nivel.INFORMATIV: frozenset({Canal.REZUMAT_ZILNIC}),
}


def canale_pentru(nivel: Nivel) -> frozenset[Canal]:
    return _RUTARE[nivel]


class Notificare(BaseModel):
    nivel: Nivel
    titlu: str = Field(max_length=100)
    text: str = Field(max_length=300)
    url: str = "/alerte"  # doar cale relativă, în aceeași origine

    def payload(self) -> str:
        url = self.url if self.url.startswith("/") and not self.url.startswith("//") else "/"
        return json.dumps(
            {"titlu": self.titlu, "text": self.text, "url": url, "nivel": self.nivel.value},
            ensure_ascii=False,
        )


@dataclass(frozen=True)
class Destinatar:
    endpoint: str
    p256dh: str
    auth: str


class AbonamentMort(Exception):
    """Furnizorul push a răspuns 404/410: abonamentul nu mai există și se șterge."""


# Un trimițător primește destinatarul și sarcina utilă (JSON, text). Aruncă `AbonamentMort` pentru 404/410.
Trimitator = Callable[[Destinatar, str], None]


def trimitator_webpush() -> Trimitator | None:
    """Trimițătorul real (pywebpush). `None` dacă cheile VAPID nu sunt setate: push este dezactivat."""
    s = get_settings()
    if not s.push_activ:
        return None
    privata = s.vapid_private_key.get_secret_value()
    subiect = s.vapid_subject

    def trimite(dest: Destinatar, payload: str) -> None:  # pragma: no cover - rețea reală
        # NEVERIFICAT: apelul către un serviciu push real nu rulează în CI (fără rețea); testele au unul fals.
        from pywebpush import WebPushException, webpush

        try:
            webpush(
                subscription_info={
                    "endpoint": dest.endpoint,
                    "keys": {"p256dh": dest.p256dh, "auth": dest.auth},
                },
                data=payload,
                vapid_private_key=privata,
                vapid_claims={"sub": subiect},
                ttl=3600,
                timeout=10,
            )
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):
                raise AbonamentMort from None
            raise RuntimeError(f"push eșuat (status {status})") from None  # fără detalii: pot conține adrese

    return trimite


_trimitator: Trimitator | None = None
_fals_setat = False


def seteaza_trimitator(t: Trimitator | None) -> None:
    """Pentru teste: înlocuiește trimițătorul real. `None` + `reseteaza_trimitator()` revine la cel real."""
    global _trimitator, _fals_setat
    _trimitator, _fals_setat = t, True


def reseteaza_trimitator() -> None:
    global _trimitator, _fals_setat
    _trimitator, _fals_setat = None, False


def trimitator() -> Trimitator | None:
    return _trimitator if _fals_setat else trimitator_webpush()


def push_disponibil() -> bool:
    return trimitator() is not None


# --- abonamente ---------------------------------------------------------------------------------------------


class ConflictAbonament(Exception):
    """Endpoint-ul aparține deja altui cont."""


def aboneaza(
    db: Session, utilizator_id: uuid.UUID, *, endpoint: str, p256dh: str, auth: str, user_agent: str | None
) -> None:
    existent = db.execute(
        select(AbonamentPush).where(
            AbonamentPush.endpoint == endpoint, AbonamentPush.utilizator_id == utilizator_id
        )
    ).scalar_one_or_none()
    if existent:
        existent.p256dh, existent.auth = p256dh, auth
        db.flush()
        return
    try:
        with db.begin_nested():
            db.add(
                AbonamentPush(
                    utilizator_id=utilizator_id,
                    endpoint=endpoint,
                    p256dh=p256dh,
                    auth=auth,
                    user_agent=(user_agent or "")[:300] or None,
                )
            )
            db.flush()
    except IntegrityError:
        raise ConflictAbonament from None


def dezaboneaza(db: Session, utilizator_id: uuid.UUID, endpoint: str) -> bool:
    sters = db.execute(
        delete(AbonamentPush)
        .where(AbonamentPush.endpoint == endpoint, AbonamentPush.utilizator_id == utilizator_id)
        .returning(AbonamentPush.id)
    ).first()
    return sters is not None


def numar_abonamente(db: Session, utilizator_id: uuid.UUID) -> int:
    return db.execute(
        select(func.count()).select_from(AbonamentPush).where(AbonamentPush.utilizator_id == utilizator_id)
    ).scalar_one()


@dataclass(frozen=True)
class RezultatTrimitere:
    trimise: int = 0
    sterse: int = 0
    esuate: int = 0


def _trimite_la(
    db: Session, abonamente: list[AbonamentPush], n: Notificare, send: Trimitator, *, marcheaza: bool = True
) -> RezultatTrimitere:
    """`marcheaza`: scrie `ultima_trimitere`, doar în contextul utilizatorului însuși. Agenția citește și
    șterge abonamente moarte, dar nu le modifică (politica RLS pe UPDATE este strict pe utilizator)."""
    payload = n.payload()
    trimise = sterse = esuate = 0
    for a in abonamente:
        try:
            send(Destinatar(a.endpoint, a.p256dh, a.auth), payload)
            if marcheaza:
                a.ultima_trimitere = func.now()
            trimise += 1
        except AbonamentMort:
            db.delete(a)
            sterse += 1
        except Exception as exc:
            log.warning("push eșuat", extra={"tip_eroare": type(exc).__name__})
            esuate += 1
    db.flush()
    return RezultatTrimitere(trimise, sterse, esuate)


def trimite_utilizatorului(
    db: Session, utilizator_id: uuid.UUID, n: Notificare, *, send: Trimitator | None = None
) -> RezultatTrimitere:
    """Trimite la toate dispozitivele unui utilizator. Fără trimițător (push dezactivat) nu face nimic."""
    send = send or trimitator()
    if send is None:
        return RezultatTrimitere()
    abonamente = list(
        db.execute(select(AbonamentPush).where(AbonamentPush.utilizator_id == utilizator_id)).scalars()
    )
    return _trimite_la(db, abonamente, n, send)


def notifica(nivel: Nivel, titlu: str, text: str, *, url: str = "/alerte") -> dict[Canal, bool]:
    """Rutează după nivel. Nu aruncă: o problemă la un canal nu strică apelantul. Întoarce ce a reușit."""
    n = Notificare(nivel=nivel, titlu=titlu[:100], text=text[:300], url=url)
    rezultat: dict[Canal, bool] = {}
    canale = canale_pentru(nivel)
    if Canal.PUSH in canale:
        try:
            send = trimitator()
            if send is None:
                rezultat[Canal.PUSH] = False
            else:
                with sesiune_agentie() as db:
                    abonamente = list(db.execute(select(AbonamentPush)).scalars())
                    r = _trimite_la(db, abonamente, n, send, marcheaza=False)
                rezultat[Canal.PUSH] = r.trimise > 0
        except Exception as exc:
            log.warning("notificare push nereușită", extra={"tip_eroare": type(exc).__name__})
            rezultat[Canal.PUSH] = False
    if Canal.TELEGRAM in canale:
        rezultat[Canal.TELEGRAM] = alerte.trimite(nivel.value, n.titlu, n.text)
    return rezultat
