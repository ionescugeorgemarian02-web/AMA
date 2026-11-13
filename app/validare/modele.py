"""Tabelele validării (migrarea 0028). Cheile străine există în bază, nu se declară aici."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class BazaValidare(DeclarativeBase):
    pass


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)


class ContinutLivrabil(BazaValidare):
    """O versiune de conținut a unui livrabil (acoperire provizorie până la F6). Doar adăugare."""

    __tablename__ = "livrabile_continut"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    livrabil_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    versiune: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    campuri: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    active: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    autor: Mapped[str] = mapped_column(Text)
    model_autor: Mapped[str | None] = mapped_column(Text)
    amprenta: Mapped[str] = mapped_column(Text)
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    creat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Rulare(BazaValidare):
    """O trecere a cascadei peste o versiune de livrabil. Doar adăugare."""

    __tablename__ = "validari_rulari"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    livrabil_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    versiune: Mapped[int] = mapped_column(Integer)
    runda: Mapped[int] = mapped_column(Integer)
    decizie: Mapped[str] = mapped_column(Text)
    cere_om: Mapped[bool] = mapped_column(Boolean, default=False)
    puncte: Mapped[int] = mapped_column(Integer)
    prag: Mapped[int] = mapped_column(Integer)
    oprit_la_treapta: Mapped[str | None] = mapped_column(Text)
    instructiune: Mapped[str] = mapped_column(Text, default="")
    amprenta: Mapped[str] = mapped_column(Text)
    cost: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VerdictSalvat(BazaValidare):
    """Verdictul unui validator într-o rulare. Doar adăugare; identitatea și versiunea validatorului rămân."""

    __tablename__ = "validari_verdicte"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    rulare_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    livrabil_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    versiune: Mapped[int] = mapped_column(Integer)
    runda: Mapped[int] = mapped_column(Integer)
    validator: Mapped[str] = mapped_column(Text)
    validator_versiune: Mapped[str] = mapped_column(Text)
    treapta: Mapped[str] = mapped_column(Text)
    rezultat: Mapped[str] = mapped_column(Text)
    severitate: Mapped[str | None] = mapped_column(Text)
    scor: Mapped[float] = mapped_column(Float)
    dovezi: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    instructiune: Mapped[str] = mapped_column(Text, default="")
    cost: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    detalii: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    amprenta: Mapped[str] = mapped_column(Text)
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Intrebare(BazaValidare):
    """O întrebare către client: livrabilul s-a oprit fiindcă lipsește un fapt necesar (G2)."""

    __tablename__ = "validari_intrebari"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    livrabil_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    versiune: Mapped[int] = mapped_column(Integer)
    validator: Mapped[str] = mapped_column(Text)
    intrebare: Mapped[str] = mapped_column(Text)
    tip_fapt: Mapped[str | None] = mapped_column(Text)
    subiect: Mapped[str | None] = mapped_column(Text)
    stare: Mapped[str] = mapped_column(Text, default="deschisa")
    raspuns: Mapped[str | None] = mapped_column(Text)
    raspuns_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    raspuns_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
