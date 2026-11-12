"""Al doilea factor: TOTP (RFC 6238) și coduri de recuperare."""

import hmac
import secrets
import time
from urllib.parse import quote

import pyotp

PERIOADA = 30
FEREASTRA = 1  # acceptă pasul curent și unul înainte/înapoi (decalaj de ceas)
EMITENT = "AMA"
ALFABET_COD = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # fără caractere ambigue  # pragma: allowlist secret
NUMAR_CODURI = 10


def secret_nou() -> str:
    return pyotp.random_base32()


def uri_provizionare(secret: str, email: str) -> str:
    return f"otpauth://totp/{quote(EMITENT)}:{quote(email)}?secret={secret}&issuer={quote(EMITENT)}"


def pas_curent(acum: float | None = None) -> int:
    return int((time.time() if acum is None else acum) // PERIOADA)


def normalizeaza_cod(cod: str) -> str:
    return "".join(cod.split())


def arata_ca_totp(cod: str) -> bool:
    c = normalizeaza_cod(cod)
    return len(c) == 6 and c.isascii() and c.isdigit()


def pas_valid(secret: str, cod: str, *, ultim_pas: int | None, acum: float | None = None) -> int | None:
    """Pasul pentru care `cod` e corect, doar dacă e mai nou decât ultimul acceptat (anti-reluare)."""
    c = normalizeaza_cod(cod)
    if not arata_ca_totp(c):
        return None
    otp = pyotp.TOTP(secret, interval=PERIOADA)
    curent = pas_curent(acum)
    gasit: int | None = None
    for pas in range(curent - FEREASTRA, curent + FEREASTRA + 1):
        if hmac.compare_digest(otp.generate_otp(pas), c):  # fără ieșire timpurie: timp constant pe fereastră
            gasit = pas
    if gasit is None or (ultim_pas is not None and gasit <= ultim_pas):
        return None
    return gasit


def cod_pentru(secret: str, acum: float) -> str:
    """Pentru teste și diagnostic."""
    return pyotp.TOTP(secret, interval=PERIOADA).generate_otp(pas_curent(acum))


def cod_recuperare_nou() -> str:
    brut = "".join(secrets.choice(ALFABET_COD) for _ in range(16))
    return "-".join(brut[i : i + 4] for i in range(0, 16, 4))


def normalizeaza_cod_recuperare(cod: str) -> str:
    return "".join(ch for ch in cod.upper() if ch.isalnum())


def coduri_recuperare_noi() -> list[str]:
    return [cod_recuperare_nou() for _ in range(NUMAR_CODURI)]
