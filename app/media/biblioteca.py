"""Biblioteca de active a clientului (F7.5, docs/19 §19.2 „Materiale”, ADR-15: media pe disc local).

Un fișier încărcat din portal se verifică după CONȚINUT (semnătura de la început), nu după nume sau după tipul
declarat de browser; se păstrează pe disc ca `AMA_MEDIA_DIR/<client>/active/<sha256>.<ext>` și intră în
`active` cu sursa lui (cine, de unde, numele original). Același fișier încărcat de două ori e un singur activ.
Limite [I]: imagini 25 MB, documente 25 MB, video 300 MB, audio WAV 200 MB (F8)."""

import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.media.modele import Activ
from app.operare import audit, evenimente

MB = 1024 * 1024


@dataclass(frozen=True)
class TipFisier:
    mime: str
    extensie: str
    categorie: str  # foto / video / document
    limita: int


TIPURI = {
    "jpeg": TipFisier("image/jpeg", "jpg", "foto", 25 * MB),
    "png": TipFisier("image/png", "png", "foto", 25 * MB),
    "webp": TipFisier("image/webp", "webp", "foto", 25 * MB),
    "mp4": TipFisier("video/mp4", "mp4", "video", 300 * MB),
    "mov": TipFisier("video/quicktime", "mov", "video", 300 * MB),
    "pdf": TipFisier("application/pdf", "pdf", "document", 25 * MB),
    "wav": TipFisier("audio/wav", "wav", "audio", 200 * MB),
}
NUME_SIGUR = re.compile(r"^[0-9a-f]{64}\.[a-z0-9]{2,5}$")


class FisierRefuzat(ValueError):
    """Tipul sau mărimea fișierului nu sunt acceptate (mesaj pentru om)."""


def detecteaza(corp: bytes) -> TipFisier | None:
    """Nucleu pur: tipul după semnătura conținutului."""
    if corp.startswith(b"\xff\xd8\xff"):
        return TIPURI["jpeg"]
    if corp.startswith(b"\x89PNG\r\n\x1a\n"):
        return TIPURI["png"]
    if corp[:4] == b"RIFF" and corp[8:12] == b"WEBP":
        return TIPURI["webp"]
    if corp[:4] == b"RIFF" and corp[8:12] == b"WAVE":
        return TIPURI["wav"]
    if corp.startswith(b"%PDF-"):
        return TIPURI["pdf"]
    if corp[4:8] == b"ftyp":
        return TIPURI["mov"] if corp[8:10] == b"qt" else TIPURI["mp4"]
    return None


def verifica(corp: bytes) -> TipFisier:
    if not corp:
        raise FisierRefuzat("fișierul este gol")
    tip = detecteaza(corp)
    if tip is None:
        raise FisierRefuzat(
            "tip de fișier neacceptat: încarcă fotografii (JPG, PNG, WebP), video (MP4, MOV) sau PDF"
        )
    if len(corp) > tip.limita:
        raise FisierRefuzat(f"fișierul depășește {tip.limita // MB} MB")
    return tip


def _scrie(tenant_id: uuid.UUID, nume: str, corp: bytes) -> str:
    if not NUME_SIGUR.match(nume):
        raise ValueError("nume de fișier nesigur")
    rel = f"{tenant_id}/active/{nume}"
    destinatie = Path(get_settings().media_dir) / rel
    if not destinatie.exists():
        destinatie.parent.mkdir(parents=True, exist_ok=True)
        temporar = destinatie.with_name(f".{nume}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
        try:
            temporar.write_bytes(corp)
            temporar.replace(destinatie)
        finally:
            temporar.unlink(missing_ok=True)
    return rel


def incarca(
    db: Session,
    tenant_id: uuid.UUID,
    corp: bytes,
    *,
    nume_original: str,
    sursa: str,
    utilizator_id: uuid.UUID | None,
    descriere: str = "",
    licenta: dict[str, Any] | None = None,
    generare: dict[str, Any] | None = None,
) -> Activ:
    """Verifică, salvează și înregistrează un activ. Idempotent pe conținut (același hash, același activ).
    `licenta`: statutul drepturilor (F8.1, F8.4), `generare`: promptul / modelul / sămânța (F8.4, 14.3)."""
    tip = verifica(corp)
    h = hashlib.sha256(corp).hexdigest()
    existent = db.execute(
        select(Activ).where(Activ.tenant_id == tenant_id, Activ.sha256 == h)
    ).scalar_one_or_none()
    if existent is not None:
        return existent
    rel = _scrie(tenant_id, f"{h}.{tip.extensie}", corp)
    a = Activ(
        tenant_id=tenant_id,
        categorie=tip.categorie,
        mime=tip.mime,
        marime=len(corp),
        sha256=h,
        cale=rel,
        nume_original=Path(nume_original or "fisier").name[:200],
        sursa=sursa,
        descriere=descriere.strip()[:500],
        incarcat_de=utilizator_id,
        licenta=licenta,
        generare=generare,
    )
    db.add(a)
    db.flush()
    audit.record(
        db,
        "activ.incarcat",
        obiect_tip="activ",
        obiect_id=a.id,
        tenant_id=tenant_id,
        utilizator_id=utilizator_id,
        detalii={
            "categorie": a.categorie,
            "sursa": sursa,
            "marime": a.marime,
            "licenta": (licenta or {}).get("statut") or (licenta or {}).get("tip"),
        },
    )
    evenimente.emite(
        db,
        "activ.incarcat",
        sursa="media",
        obiect_tip="activ",
        obiect_id=a.id,
        tenant_id=tenant_id,
        utilizator_id=utilizator_id,
        date={"categorie": a.categorie},
    )
    return a


def ale_clientului(db: Session, tenant_id: uuid.UUID, *, limita: int = 200) -> list[Activ]:
    return list(
        db.execute(
            select(Activ).where(Activ.tenant_id == tenant_id).order_by(Activ.creat_la.desc()).limit(limita)
        ).scalars()
    )


def citeste_fisier(a: Activ) -> bytes:
    baza = Path(get_settings().media_dir).resolve()
    cale = (baza / a.cale).resolve()
    if baza not in cale.parents:
        raise ValueError("cale în afara directorului de media")
    return cale.read_bytes()
