"""Tabelele onboardingului (migrările 0026 și 0027). Cheile străine există în bază, nu se declară aici."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class BazaOnboarding(DeclarativeBase):
    pass


class Sesiune(BazaOnboarding):
    __tablename__ = "onboarding_sesiuni"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    stare: Mapped[str] = mapped_column(Text, default="interviu")
    brief: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    brief_probleme: Mapped[list[str]] = mapped_column(JSONB, default=list)
    brief_intrare_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    flux_id: Mapped[str | None] = mapped_column(Text)
    amanat_pana: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IntrebareSesiune(BazaOnboarding):
    __tablename__ = "onboarding_intrebari"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    sesiune_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    ordine: Mapped[int] = mapped_column(Integer)
    tip: Mapped[str] = mapped_column(Text)
    cod: Mapped[str] = mapped_column(Text)
    camp: Mapped[str] = mapped_column(Text)
    text_intrebare: Mapped[str] = mapped_column(Text)
    parinte_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    generata_de: Mapped[str] = mapped_column(Text, default="date")
    raspuns: Mapped[str | None] = mapped_column(Text)
    raspuns_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raspuns_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VarianteTon(BazaOnboarding):
    """O variantă de ton propusă pentru ghidul de brand (F4.5). Conținutul nu se schimbă; se marchează
    cea aleasă."""

    __tablename__ = "onboarding_variante_ton"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    grup_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    nr: Mapped[int] = mapped_column(Integer)
    continut: Mapped[dict[str, Any]] = mapped_column(JSONB)
    prompt: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    brief_versiune: Mapped[int | None] = mapped_column(Integer)
    ales: Mapped[bool] = mapped_column(Boolean, default=False)
    ales_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ales_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
