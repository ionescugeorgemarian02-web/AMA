"""Articolele blogului agenției (docs/19 §19.1 „Blog”): citire pentru site, publicare din F7.10."""

import datetime as dt
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.site.modele import Articol

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DIACRITICE = str.maketrans("ăâîșşțţĂÂÎȘŞȚŢ", "aaisstt" + "AAISSTT")


def slug_din(titlu: str) -> str:
    """Nucleu pur: „Cum alegi cafeaua?” → „cum-alegi-cafeaua”."""
    s = re.sub(r"[^a-z0-9]+", "-", titlu.translate(DIACRITICE).lower()).strip("-")
    return s[:90].rstrip("-") or "articol"


def publicate(db: Session, *, limita: int = 50) -> list[Articol]:
    return list(
        db.execute(
            select(Articol)
            .where(Articol.publicat_la.is_not(None))
            .order_by(Articol.publicat_la.desc())
            .limit(limita)
        ).scalars()
    )


def dupa_slug(db: Session, slug: str) -> Articol | None:
    if not SLUG.match(slug):
        return None
    return db.execute(
        select(Articol).where(Articol.slug == slug, Articol.publicat_la.is_not(None))
    ).scalar_one_or_none()


def publica(
    db: Session,
    *,
    titlu: str,
    descriere: str,
    corp: list[dict[str, Any]],
    surse: list[dict[str, Any]],
    cuvant_cheie: str = "",
    slug: str | None = None,
) -> Articol:
    """Publică (sau actualizează, pe același slug) un articol. Contextul de agenție."""
    slug = slug or slug_din(titlu)
    a = db.execute(select(Articol).where(Articol.slug == slug)).scalar_one_or_none()
    if a is None:
        a = Articol(slug=slug, titlu=titlu, descriere=descriere, corp=corp, surse=surse)
        db.add(a)
    a.titlu, a.descriere, a.corp, a.surse, a.cuvant_cheie = titlu, descriere, corp, surse, cuvant_cheie
    a.publicat_la = dt.datetime.now(dt.UTC)
    db.flush()
    return a
