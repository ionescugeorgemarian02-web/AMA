"""Previzualizarea și consimțământul pentru postarea directă pe TikTok (F9.6, regulile de integrare TikTok).

Înainte de o postare directă: se citesc opțiunile creatorului (`creator_info`), omul vede previzualizarea
(pseudonimul contului, clipul, legenda, eticheta AI), ALEGE vizibilitatea dintre opțiunile contului (fără
valoare implicită) și interacțiunile, apoi își dă consimțământul explicit. Consimțământul e pe versiune: o
versiune nouă cere altul. Fără el, programarea așteaptă, iar conectorul refuză.
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import DateTime, Integer, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from app import productie
from app.ids import new_id
from app.operare import audit
from app.publicare.modele import BazaPublicare

INTERACTIUNI = ("fara_comentarii", "fara_duet", "fara_stitch")


class Consimtamant(BazaPublicare):
    __tablename__ = "publicare_consimtaminte"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    livrabil_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    versiune: Mapped[int] = mapped_column(Integer)
    canal: Mapped[str] = mapped_column(Text)
    optiuni: Mapped[dict[str, Any]] = mapped_column(JSONB)
    previzualizare: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    dat_de: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    dat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConsimtamantRefuzat(ValueError):
    pass


def valideaza(optiuni: dict[str, Any], creator: dict[str, Any], *, de_acord: bool) -> dict[str, Any]:
    """Nucleu pur: opțiunile alese de om, verificate față de ce permite contul acum."""
    if not de_acord:
        raise ConsimtamantRefuzat("bifează consimțământul explicit pentru această postare")
    viz = str(optiuni.get("vizibilitate") or "")
    if not viz:
        raise ConsimtamantRefuzat("alege vizibilitatea: nu există o valoare implicită")
    if viz not in (creator.get("privacy_level_options") or []):
        raise ConsimtamantRefuzat("vizibilitatea aleasă nu este permisă acestui cont")
    out: dict[str, Any] = {"vizibilitate": viz}
    for k in INTERACTIUNI:
        out[k] = bool(optiuni.get(k))
    out["fara_comentarii"] = out["fara_comentarii"] or bool(creator.get("comment_disabled"))
    out["fara_duet"] = out["fara_duet"] or bool(creator.get("duet_disabled"))
    out["fara_stitch"] = out["fara_stitch"] or bool(creator.get("stitch_disabled"))
    return out


def inregistreaza(
    db: Session,
    livrabil_id: uuid.UUID,
    *,
    optiuni: dict[str, Any],
    creator: dict[str, Any],
    de_acord: bool,
    utilizator_id: uuid.UUID,
    canal: str = "tiktok",
) -> Consimtamant:
    lv = productie.blocheaza(db, livrabil_id)
    if lv.canal != canal:
        raise ConsimtamantRefuzat("livrabilul nu este pe acest canal")
    existent = al_versiunii(db, lv.id, lv.versiune, canal)
    if existent is not None:
        return existent
    alese = valideaza(optiuni, creator, de_acord=de_acord)
    prev = {
        k: creator.get(k)
        for k in (
            "creator_username",
            "creator_nickname",
            "privacy_level_options",
            "max_video_post_duration_sec",
        )
    }
    c = Consimtamant(
        tenant_id=lv.tenant_id,
        livrabil_id=lv.id,
        versiune=lv.versiune,
        canal=canal,
        optiuni=alese,
        previzualizare=prev,
        dat_de=utilizator_id,
    )
    db.add(c)
    db.flush()
    audit.record(
        db,
        "publicare.consimtamant",
        obiect_tip="livrabil",
        obiect_id=lv.id,
        tenant_id=lv.tenant_id,
        utilizator_id=utilizator_id,
        detalii={"canal": canal, "versiune": lv.versiune, **alese},
    )
    return c


def al_versiunii(db: Session, livrabil_id: uuid.UUID, versiune: int, canal: str) -> Consimtamant | None:
    return db.execute(
        select(Consimtamant).where(
            Consimtamant.livrabil_id == livrabil_id,
            Consimtamant.versiune == versiune,
            Consimtamant.canal == canal,
        )
    ).scalar_one_or_none()


def pentru_pachet(c: Consimtamant) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "dat_de": str(c.dat_de),
        "dat_la": c.dat_la.isoformat() if c.dat_la else None,
        **c.optiuni,
    }
