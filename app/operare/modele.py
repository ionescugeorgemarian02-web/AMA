"""Tabelele jurnalelor (doar adăugări, impus în bază)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class BazaJurnale(DeclarativeBase):
    pass


class JurnalAudit(BazaJurnale):
    __tablename__ = "jurnal_audit"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clienti.id"))
    utilizator_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("utilizatori.id"))
    actor_tip: Mapped[str] = mapped_column(Text)
    actiune: Mapped[str] = mapped_column(Text)
    obiect_tip: Mapped[str | None] = mapped_column(Text)
    obiect_id: Mapped[str | None] = mapped_column(Text)
    rezultat: Mapped[str] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(Text)
    corelare_id: Mapped[str | None] = mapped_column(Text)
    detalii: Mapped[dict[str, Any]] = mapped_column(JSONB)


class JurnalEveniment(BazaJurnale):
    __tablename__ = "jurnal_evenimente"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clienti.id"))
    utilizator_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("utilizatori.id"))
    tip: Mapped[str] = mapped_column(Text)
    sursa: Mapped[str] = mapped_column(Text)
    obiect_tip: Mapped[str | None] = mapped_column(Text)
    obiect_id: Mapped[str | None] = mapped_column(Text)
    corelare_id: Mapped[str | None] = mapped_column(Text)
    date: Mapped[dict[str, Any]] = mapped_column(JSONB)
