"""Tabelele analizei (F10). Cheile străine există în bază."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class BazaAnaliza(DeclarativeBase):
    pass


class MetriciPostare(BazaAnaliza):
    """Citirea unui interval pentru o postare publicată (F10.1, migrarea 0057)."""

    __tablename__ = "metrici_postari"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    livrabil_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    canal: Mapped[str] = mapped_column(Text)
    id_extern: Mapped[str] = mapped_column(Text, default="")
    interval: Mapped[str] = mapped_column(Text)
    stare: Mapped[str] = mapped_column(Text)
    sursa: Mapped[str] = mapped_column(Text, default="api")
    valori: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    motiv: Mapped[str] = mapped_column(Text, default="")
    publicat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    citit_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    intarziere_s: Mapped[int] = mapped_column(Integer, default=0)
    introdus_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class CurbaRetentie(BazaAnaliza):
    """Ultima curbă de retenție citită pentru un clip (F10.2, migrarea 0058)."""

    __tablename__ = "curbe_retentie"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    livrabil_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    canal: Mapped[str] = mapped_column(Text)
    id_extern: Mapped[str] = mapped_column(Text)
    interval: Mapped[str] = mapped_column(Text)
    puncte: Mapped[list[list[float]]] = mapped_column(JSONB)
    citit_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
