"""Primitive criptografice ale conturilor: secrete în repaus (AES-GCM), HMAC pentru coduri, jetoane.

Cheia vine din `settings.master_key` (21.2) și nu se folosește direct: se derivă câte o cheie pe scop (HKDF).
"""

import hashlib
import hmac
import os
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings

VERSIUNE = b"\x01"
LUNGIME_MINIMA_CHEIE = 32


class CheieLipsa(RuntimeError):
    pass


def _derivata(scop: str) -> bytes:
    master = get_settings().master_key.get_secret_value()
    if len(master) < LUNGIME_MINIMA_CHEIE:
        raise CheieLipsa("AMA_MASTER_KEY lipsește sau este prea scurtă (minimum 32 de caractere)")
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=f"ama/{scop}/v1".encode()).derive(
        master.encode()
    )


def cripteaza(text_clar: bytes, *, aad: bytes) -> bytes:
    """AES-256-GCM, nonce de 96 de biți. `aad` leagă textul criptat de rândul său (ex. id utilizator)."""
    nonce = os.urandom(12)
    return VERSIUNE + nonce + AESGCM(_derivata("secrete-in-repaus")).encrypt(nonce, text_clar, VERSIUNE + aad)


def decripteaza(blob: bytes, *, aad: bytes) -> bytes:
    if not blob.startswith(VERSIUNE) or len(blob) < 1 + 12 + 16:
        raise ValueError("format necunoscut")
    nonce, ct = blob[1:13], blob[13:]
    return AESGCM(_derivata("secrete-in-repaus")).decrypt(nonce, ct, VERSIUNE + aad)


def hmac_valoare(scop: str, valoare: str) -> bytes:
    """HMAC-SHA256 cu cheie derivată: pentru coduri de recuperare și chei de limitare (fără PII în clar)."""
    return hmac.new(_derivata(f"hmac-{scop}"), valoare.encode(), hashlib.sha256).digest()


def jeton_nou() -> str:
    """256 de biți aleatori, în format URL-safe."""
    return secrets.token_urlsafe(32)


def hash_jeton(jeton: str) -> bytes:
    """În bază se ține doar SHA-256 al jetonului de sesiune."""
    return hashlib.sha256(jeton.encode()).digest()


def egale(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
