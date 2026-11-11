"""Parole: argon2id, lungime minimă 12 (21.3)."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

LUNGIME_MINIMA = 12
LUNGIME_MAXIMA = 128  # limită de resurse: argon2 consumă memorie

_hasher = PasswordHasher()  # argon2id cu parametrii impliciți recomandați (RFC 9106)
# Hash fals, calculat o dată: verificarea lui egalează timpul cerut pentru un utilizator existent.
_HASH_FALS = _hasher.hash("parola-falsa-pentru-egalizarea-timpului")


class ParolaInvalida(ValueError):
    pass


def valideaza(parola: str, email: str = "") -> None:
    if len(parola) < LUNGIME_MINIMA:
        raise ParolaInvalida(f"Parola trebuie să aibă cel puțin {LUNGIME_MINIMA} caractere.")
    if len(parola) > LUNGIME_MAXIMA:
        raise ParolaInvalida(f"Parola poate avea cel mult {LUNGIME_MAXIMA} de caractere.")
    if email and parola.strip().lower() == email.strip().lower():
        raise ParolaInvalida("Parola nu poate fi adresa de email.")


def hash_parola(parola: str) -> str:
    return _hasher.hash(parola)


def verifica(hash_stocat: str | None, parola: str) -> bool:
    """Verifică parola. Fără hash (utilizator necunoscut) rulează aceeași muncă și întoarce fals."""
    try:
        if hash_stocat is None:
            _hasher.verify(_HASH_FALS, parola[:LUNGIME_MAXIMA])
            return False
        return _hasher.verify(hash_stocat, parola[:LUNGIME_MAXIMA])
    except (VerificationError, InvalidHashError):
        return False


def necesita_rehash(hash_stocat: str) -> bool:
    return _hasher.check_needs_rehash(hash_stocat)
