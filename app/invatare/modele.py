"""Tabelele învățării (F11, migrarea 0090). Cheile străine există în bază."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class BazaInvatare(DeclarativeBase):
    pass


class LotReflectie(BazaInvatare):
    __tablename__ = "loturi_reflectie"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    de_la: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    pana_la: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    postari: Mapped[int] = mapped_column(Integer)
    propuneri: Mapped[int] = mapped_column(Integer, default=0)
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Lectie(BazaInvatare):
    """Un rând de playbook (11.3)."""

    __tablename__ = "lectii"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    lot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cheie: Mapped[str] = mapped_column(Text)
    domeniu_tip: Mapped[str] = mapped_column(Text)
    domeniu: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text)
    dovezi: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    sursa: Mapped[str] = mapped_column(Text)
    sensibila: Mapped[bool] = mapped_column(Boolean, default=False)
    stare: Mapped[str] = mapped_column(Text, default="propusa")
    a_ajutat: Mapped[int] = mapped_column(Integer, default=0)
    a_daunat: Mapped[int] = mapped_column(Integer, default=0)
    motiv: Mapped[str] = mapped_column(Text, default="")
    decis_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decis_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LectieFolosita(BazaInvatare):
    """O lecție intrată în contextul autorului pentru un livrabil (F11.2, migrarea 0091)."""

    __tablename__ = "lectii_folosite"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    livrabil_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    lectie_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    socotit: Mapped[bool] = mapped_column(Boolean, default=False)
    folosita_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
