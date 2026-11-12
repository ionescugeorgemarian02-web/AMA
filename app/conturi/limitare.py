"""Limitarea încercărilor de autentificare, în Postgres (fără Redis): pe cont și pe IP, cu fereastră.

Se înregistrează doar eșecurile și succesul final (sesiune completă). Succesul final repune la zero contorul
contului, dar nu pe cel al IP-ului (altfel un atacator cu cont propriu și-ar reseta limita).
Cheia contului este un HMAC al adresei de email: același tratament pentru conturi existente și inexistente.
"""

from sqlalchemy import CursorResult, Result, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.ids import new_id

_ESECURI_CONT = text(
    """SELECT count(*) FROM incercari_autentificare
       WHERE cheie_cont = :cheie AND NOT reusit
         AND creat_la > GREATEST(
               now() - make_interval(mins => :fereastra),
               COALESCE((SELECT max(creat_la) FROM incercari_autentificare
                         WHERE cheie_cont = :cheie AND reusit), '-infinity'::timestamptz))"""
)
_ESECURI_IP = text(
    """SELECT count(*) FROM incercari_autentificare
       WHERE ip = :ip AND NOT reusit AND creat_la > now() - make_interval(mins => :fereastra)"""
)
_INSERARE = text(
    "INSERT INTO incercari_autentificare (id, cheie_cont, ip, tip, reusit)"
    " VALUES (:id, :cheie, :ip, :tip, :reusit)"
)


def rand_afectate(r: Result[tuple[object, ...]] | CursorResult[tuple[object, ...]]) -> int:
    return int(r.rowcount) if isinstance(r, CursorResult) else 0


def esecuri_cont(db: Session, cheie: bytes) -> int:
    fereastra = get_settings().login_window_minutes
    return int(db.execute(_ESECURI_CONT, {"cheie": cheie, "fereastra": fereastra}).scalar_one())


def esecuri_ip(db: Session, ip: str) -> int:
    fereastra = get_settings().login_window_minutes
    return int(db.execute(_ESECURI_IP, {"ip": ip, "fereastra": fereastra}).scalar_one())


def cont_blocat(db: Session, cheie: bytes) -> bool:
    return esecuri_cont(db, cheie) >= get_settings().login_max_failures_account


def ip_blocat(db: Session, ip: str) -> bool:
    return esecuri_ip(db, ip) >= get_settings().login_max_failures_ip


def blocat(db: Session, cheie: bytes, ip: str) -> bool:
    return cont_blocat(db, cheie) or ip_blocat(db, ip)


def inregistreaza(db: Session, cheie: bytes, ip: str, tip: str, *, reusit: bool) -> None:
    db.execute(_INSERARE, {"id": new_id(), "cheie": cheie, "ip": ip, "tip": tip, "reusit": reusit})


def curata_vechi(db: Session, ore: int = 48) -> int:
    """Retenție: încercările mai vechi de `ore` nu mai contează pentru limitare."""
    r = db.execute(
        text("DELETE FROM incercari_autentificare WHERE creat_la < now() - make_interval(hours => :ore)"),
        {"ore": ore},
    )
    return rand_afectate(r)
