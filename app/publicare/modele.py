"""Tabelele publicării (F6.6, migrarea 0038). Cheile străine există în bază."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class BazaPublicare(DeclarativeBase):
    pass


class PublicareAsistata(BazaPublicare):
    """Pachetul de publicare asistată al unei versiuni aprobate și linkul lipit de om."""

    __tablename__ = "publicari_asistate"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    livrabil_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    versiune: Mapped[int] = mapped_column(Integer)
    canal: Mapped[str] = mapped_column(Text)
    cheie: Mapped[str] = mapped_column(Text)
    pachet: Mapped[dict[str, Any]] = mapped_column(JSONB)
    stare: Mapped[str] = mapped_column(Text, default="pregatit")
    link: Mapped[str | None] = mapped_column(Text)
    publicat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    publicat_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
