"""Originalele colectate, pe disc (docs/20 §20.4, ADR-15):
`AMA_MEDIA_DIR/<client>/surse/<sursă>/<sha256>.<ext>`.

Numele vine doar din identificatori și din hash (niciodată din text venit din exterior), deci nu există cale
de ieșire din director. Scrierea e atomică (fișier temporar + redenumire) și idempotentă: același conținut,
același nume. Fișierele unui client stau sub directorul clientului (ștergerea clientului le șterge odată cu
el).
"""

import hashlib
import os
import re
import uuid
from pathlib import Path

from app.config import get_settings

EXTENSII = {
    "text/html": "html",
    "application/xhtml+xml": "html",
    "text/plain": "txt",
    "text/markdown": "md",
}
NUME_SIGUR = re.compile(r"^[0-9a-f]{64}\.[a-z0-9]{1,5}$")


def radacina() -> Path:
    return Path(get_settings().media_dir)


def sha256(corp: bytes) -> str:
    return hashlib.sha256(corp).hexdigest()


def cale_relativa(tenant_id: uuid.UUID, sursa_id: uuid.UUID, hash_continut: str, extensie: str) -> str:
    nume = f"{hash_continut}.{extensie}"
    if not NUME_SIGUR.match(nume):
        raise ValueError("nume de fișier nesigur")
    return f"{tenant_id}/surse/{sursa_id}/{nume}"


def scrie(tenant_id: uuid.UUID, sursa_id: uuid.UUID, corp: bytes, content_type: str) -> tuple[str, str]:
    """Salvează originalul. Întoarce (hash, calea relativă la `AMA_MEDIA_DIR`)."""
    h = sha256(corp)
    rel = cale_relativa(
        tenant_id, sursa_id, h, EXTENSII.get(content_type.split(";")[0].strip().lower(), "bin")
    )
    destinatie = radacina() / rel
    if destinatie.exists():
        return h, rel
    destinatie.parent.mkdir(parents=True, exist_ok=True)
    temporar = destinatie.with_name(f".{destinatie.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        temporar.write_bytes(corp)
        temporar.replace(destinatie)
    finally:
        temporar.unlink(missing_ok=True)
    return h, rel


def citeste(cale_rel: str) -> bytes:
    baza = radacina().resolve()
    cale = (baza / cale_rel).resolve()
    if baza not in cale.parents:
        raise ValueError("cale în afara directorului de media")
    return cale.read_bytes()
