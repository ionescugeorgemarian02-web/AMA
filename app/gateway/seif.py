"""Seiful de secrete al gateway-ului (G-pool, D-030): cheile furnizorilor criptate (Fernet) în Postgres.

Portat din seiful fabricii și adaptat: cheia de criptare NU stă în bază, ci se derivă (HKDF, scop propriu) din
`AMA_MASTER_KEY`; o copie a bazei fără fișierul de mediu nu scurge nicio cheie. Seiful primește doar numele
din `catalog.NUME_SECRETE` (baza refuză și ea alte nume). Mediul are întâietate: seiful e o rezervă pentru
cheile puse de proprietar fără repornire. Valorile nu ajung în jurnale, audit, erori sau HTML.

Linia de comandă (valoarea se citește ascuns de la terminal sau de pe intrarea standard, niciodată din
argumente):

    python -m app.gateway.seif pune GROQ_API_KEY
    python -m app.gateway.seif lista
    python -m app.gateway.seif sterge GROQ_API_KEY
"""

import argparse
import base64
import getpass
import sys
import time

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import sesiune_agentie
from app.gateway.catalog import NUME_SECRETE
from app.logging import get_logger
from app.operare import audit

log = get_logger(__name__)
LUNGIME_MINIMA_CHEIE = 32
VALOARE_MAXIMA = 4096
CACHE_SEC = 60.0


class SeifIndisponibil(RuntimeError):
    """Cheia principală lipsește sau e prea scurtă: seiful nu poate cripta / decripta."""


def _fernet() -> Fernet:
    master = get_settings().master_key.get_secret_value()
    if len(master) < LUNGIME_MINIMA_CHEIE:
        raise SeifIndisponibil("AMA_MASTER_KEY lipsește sau e prea scurtă (minimum 32 de caractere)")
    cheie = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"ama/seif-gateway/v1").derive(
        master.encode()
    )
    return Fernet(base64.urlsafe_b64encode(cheie))


def _verifica_nume(nume: str) -> None:
    if nume not in NUME_SECRETE:
        raise ValueError(f"nume de secret necunoscut: {nume!r} (vezi catalog.PROVIDER_SECRETS)")


def pune(db: Session, nume: str, valoare: str) -> None:
    _verifica_nume(nume)
    valoare = valoare.strip()
    if not 1 <= len(valoare) <= VALOARE_MAXIMA:
        raise ValueError("valoare goală sau prea lungă")
    blob = _fernet().encrypt(valoare.encode())
    db.execute(
        text(
            "INSERT INTO gateway_seif (nume, valoare) VALUES (:n, :v) "
            "ON CONFLICT (nume) DO UPDATE SET valoare = EXCLUDED.valoare, actualizat_la = now()"
        ),
        {"n": nume, "v": blob},
    )
    audit.record(
        db, "gateway.secret_pus", obiect_tip="secret", obiect_id=nume, utilizator_id=None, tenant_id=None,
        detalii={"nume": nume},
    )  # fmt: skip
    invalideaza()


def sterge(db: Session, nume: str) -> bool:
    _verifica_nume(nume)
    r = db.execute(text("DELETE FROM gateway_seif WHERE nume = :n"), {"n": nume})
    audit.record(
        db, "gateway.secret_sters", obiect_tip="secret", obiect_id=nume, utilizator_id=None, tenant_id=None,
        detalii={"nume": nume},
    )  # fmt: skip
    invalideaza()
    return bool(getattr(r, "rowcount", 0))


def nume(db: Session) -> list[str]:
    return list(db.execute(text("SELECT nume FROM gateway_seif ORDER BY nume")).scalars())


def _incarca(db: Session) -> dict[str, str]:
    f = _fernet()
    valori: dict[str, str] = {}
    for n, blob in db.execute(text("SELECT nume, valoare FROM gateway_seif")).all():
        try:
            valori[n] = f.decrypt(bytes(blob)).decode()
        except InvalidToken:
            log.warning("secret din seif nedecriptabil (altă cheie principală?)", extra={"nume": n})
    return valori


_cache: tuple[float, dict[str, str]] | None = None


def invalideaza() -> None:
    global _cache
    _cache = None


def citeste(nume_secret: str) -> str | None:
    """Valoarea din seif (cu o memorie de 60 s în proces), sau `None`. Fără cheie principală sau fără bază,
    seiful e tratat ca gol: mediul rămâne sursa."""
    global _cache
    if nume_secret not in NUME_SECRETE:
        return None
    acum = time.monotonic()
    if _cache is None or acum - _cache[0] > CACHE_SEC:
        try:
            with sesiune_agentie() as db:
                _cache = (acum, _incarca(db))
        except SeifIndisponibil:
            _cache = (acum, {})
        except Exception as exc:  # baza indisponibilă: nu blocăm apelurile care au cheia în mediu
            log.warning("seiful nu s-a putut citi", extra={"tip_eroare": type(exc).__name__})
            _cache = (acum, {})
    return _cache[1].get(nume_secret) or None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.gateway.seif", description="Seiful cheilor de furnizori.")
    sub = p.add_subparsers(dest="comanda", required=True)
    sub.add_parser("pune").add_argument("nume")
    sub.add_parser("sterge").add_argument("nume")
    sub.add_parser("lista")
    a = p.parse_args(argv)
    if a.comanda == "lista":
        with sesiune_agentie() as db:
            for n in nume(db):
                print(n)
        return 0
    if a.comanda == "pune":
        valoare = getpass.getpass(f"{a.nume}: ") if sys.stdin.isatty() else sys.stdin.readline()
        with sesiune_agentie() as db:
            pune(db, a.nume, valoare)
        print(f"{a.nume}: pus în seif")
        return 0
    with sesiune_agentie() as db:
        sters = sterge(db, a.nume)
    print(f"{a.nume}: {'șters' if sters else 'nu era în seif'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
