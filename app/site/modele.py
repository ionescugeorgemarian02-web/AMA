"""Tabelele site-ului public (migrările 0039+). Date ale agenției: doar contextul de agenție le vede."""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class BazaSite(DeclarativeBase):
    pass


class Vizita(BazaSite):
    __tablename__ = "site_vizite"
    zi: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    cale: Mapped[str] = mapped_column(Text, primary_key=True)
    numar: Mapped[int] = mapped_column(Integer, default=0)


class Articol(BazaSite):
    __tablename__ = "site_articole"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(Text)
    titlu: Mapped[str] = mapped_column(Text)
    descriere: Mapped[str] = mapped_column(Text)
    cuvant_cheie: Mapped[str] = mapped_column(Text, default="")
    corp: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    surse: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    dezvaluire_ai: Mapped[bool] = mapped_column(Boolean, default=True)
    publicat_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Lead(BazaSite):
    __tablename__ = "leaduri"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(Text)
    firma: Mapped[str] = mapped_column(Text)
    site_url: Mapped[str] = mapped_column(Text)
    sursa: Mapped[str] = mapped_column(Text, default="audit")
    stare: Mapped[str] = mapped_column(Text, default="neconfirmat")
    jeton_hash: Mapped[str] = mapped_column(Text)
    consimtamant_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    confirmat_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Audit(BazaSite):
    __tablename__ = "audituri"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    stare: Mapped[str] = mapped_column(Text, default="in_curs")
    motor: Mapped[str] = mapped_column(Text)
    raport: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    eroare: Mapped[str | None] = mapped_column(Text)
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    gata_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
