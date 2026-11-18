"""Tabelul `urme` (FT.1, migrarea 0076). Doar adăugare: nicio cale de UPDATE sau DELETE în aplicație."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class BazaUrme(DeclarativeBase):
    pass


class Urma(BazaUrme):
    __tablename__ = "urme"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    corelare_id: Mapped[str] = mapped_column(Text)
    cauza_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    componenta: Mapped[str] = mapped_column(Text)
    actiune: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(Text)
    motiv: Mapped[str] = mapped_column(Text)
    rezultat: Mapped[str] = mapped_column(Text)
    cod: Mapped[str] = mapped_column(Text)
    cost: Mapped[Decimal] = mapped_column(Numeric(14, 6))
    unitate_cost: Mapped[str] = mapped_column(Text)
    durata_ms: Mapped[int | None] = mapped_column(Integer)
    obiect_tip: Mapped[str | None] = mapped_column(Text)
    obiect_id: Mapped[str | None] = mapped_column(Text)
    intrari: Mapped[dict[str, Any]] = mapped_column(JSONB)
    iesiri: Mapped[dict[str, Any]] = mapped_column(JSONB)


class RaportUrme(BazaUrme):
    """Analiza lunară (FT.4); una pe lună, regenerabilă (ultima generare câștigă)."""

    __tablename__ = "urme_rapoarte"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    luna: Mapped[dt.date] = mapped_column(Date)
    generat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    continut: Mapped[dict[str, Any]] = mapped_column(JSONB)
