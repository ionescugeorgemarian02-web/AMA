"""Tabelele portalului clientului (migrările 0041+)."""

import datetime as dt
import uuid

from sqlalchemy import DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class BazaPortal(DeclarativeBase):
    pass


class Invitatie(BazaPortal):
    __tablename__ = "invitatii"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    email: Mapped[str] = mapped_column(Text)
    rol: Mapped[str] = mapped_column(Text)
    jeton_hash: Mapped[str] = mapped_column(Text)
    expira_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    folosita_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    utilizator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
