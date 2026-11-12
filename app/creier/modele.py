"""Tabelele Creierului (migrarea 0021). Cheile străine există în bază, nu se declară aici."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class BazaCreier(DeclarativeBase):
    pass


class IntrareCreier(BazaCreier):
    """Identitatea unei intrări: compartiment + cheie + nivel. Nu se modifică."""

    __tablename__ = "creier_intrari"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    nivel: Mapped[str] = mapped_column(Text, default="client")
    compartiment: Mapped[str] = mapped_column(Text)
    cheie: Mapped[str] = mapped_column(Text)
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    creat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class VersiuneCreier(BazaCreier):
    """O versiune a unei intrări. Conținutul, sursa și valabilitatea sunt înghețate de un declanșator în bază;
    se schimbă doar `stare` și urmele ei (aprobat_*, retras_*, inlocuita_de)."""

    __tablename__ = "creier_versiuni"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    intrare_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    nr: Mapped[int] = mapped_column(Integer)
    continut: Mapped[dict[str, Any]] = mapped_column(JSONB)
    text_cautare: Mapped[str] = mapped_column(Text, default="")
    stare: Mapped[str] = mapped_column(Text)
    sursa_tip: Mapped[str] = mapped_column(Text)
    sursa_ref: Mapped[str | None] = mapped_column(Text)
    sursa_citat: Mapped[str | None] = mapped_column(Text)
    sursa_detalii: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    valabil_de_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valabil_pana_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motiv: Mapped[str] = mapped_column(Text, default="")
    creat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    propus_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aprobat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    aprobat_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aprobat_prin: Mapped[str | None] = mapped_column(Text)
    retras_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    retras_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retras_cauza: Mapped[str | None] = mapped_column(Text)
    retras_motiv: Mapped[str] = mapped_column(Text, default="")
    inlocuita_de: Mapped[int | None] = mapped_column(Integer)
