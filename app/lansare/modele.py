"""Tabelele lansării (F15.5 pilotul, F15.6 lista de go-live)."""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Date, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class BazaLansare(DeclarativeBase):
    pass


class PilotClient(BazaLansare):
    __tablename__ = "pilot_clienti"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    inceput: Mapped[dt.date] = mapped_column(Date)
    saptamani: Mapped[int] = mapped_column(Integer, default=4)
    pret_lunar_bani: Mapped[int] = mapped_column(Integer)
    stare: Mapped[str] = mapped_column(Text, default="activ")
    note: Mapped[str] = mapped_column(Text, default="")
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    creat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class PilotFeedback(BazaLansare):
    __tablename__ = "pilot_feedback"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    saptamana: Mapped[dt.date] = mapped_column(Date)
    satisfactie: Mapped[int] = mapped_column(Integer)
    minute_om: Mapped[int] = mapped_column(Integer, default=0)
    frictiuni: Mapped[str] = mapped_column(Text, default="")
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    creat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class PilotRaport(BazaLansare):
    __tablename__ = "pilot_rapoarte"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    saptamana: Mapped[dt.date] = mapped_column(Date)
    continut: Mapped[dict[str, Any]] = mapped_column(JSONB)
    generat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
