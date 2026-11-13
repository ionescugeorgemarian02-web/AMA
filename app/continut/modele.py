"""Tabelele producției de conținut text (F6, migrările 0034 și următoarele). Cheile străine există în bază."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class BazaContinut(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)


class Calendar(BazaContinut):
    """Calendarul strategului de conținut (D3) pe o fereastră de zile, legat de strategia aprobată (F6.1)."""

    __tablename__ = "calendare"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    inceput: Mapped[date] = mapped_column(Date)
    zile: Mapped[int] = mapped_column(Integer)
    strategie_intrare_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    strategie_versiune: Mapped[int] = mapped_column(Integer)
    propunere: Mapped[dict[str, Any]] = mapped_column(JSONB)
    pachet_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    model: Mapped[str | None] = mapped_column(Text)
    stare: Mapped[str] = mapped_column(Text, default="propus")
    motiv: Mapped[str | None] = mapped_column(Text)
    decis_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decis_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IntrareCalendar(BazaContinut):
    """Un slot din calendar. La aprobarea calendarului primește livrabilul lui (o singură dată)."""

    __tablename__ = "calendar_intrari"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    calendar_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    nr: Mapped[int] = mapped_column(Integer)
    slot_la: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    canal: Mapped[str] = mapped_column(Text)
    tip: Mapped[str] = mapped_column(Text)
    pilon: Mapped[str] = mapped_column(Text)
    subiect: Mapped[str] = mapped_column(Text)
    unghi: Mapped[str] = mapped_column(Text, default="")
    livrabil_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Brief(BazaContinut):
    """Brieful unui livrabil (D5, F6.2): scop, public, mesaj unic, fapte permise, format.
    Unul pe livrabil, neschimbat."""

    __tablename__ = "briefuri"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    livrabil_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    pachet_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    continut: Mapped[dict[str, Any]] = mapped_column(JSONB)
    model: Mapped[str | None] = mapped_column(Text)
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
