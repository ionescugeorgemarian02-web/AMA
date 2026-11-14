"""Tabelele publicării (F6.6, migrarea 0038). Cheile străine există în bază."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, LargeBinary, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
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


class ContCanal(BazaPublicare):
    """Contul unui client pe un canal cu publicare prin API (F9.1, migrarea 0053). Tokenul e criptat."""

    __tablename__ = "publicare_conturi"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    canal: Mapped[str] = mapped_column(Text, primary_key=True)
    cont_extern: Mapped[str] = mapped_column(Text, default="")
    nume: Mapped[str] = mapped_column(Text, default="")
    cont_agentie: Mapped[bool] = mapped_column(Boolean, default=False)
    mod_ales: Mapped[str] = mapped_column(Text, default="automat")
    token_criptat: Mapped[bytes | None] = mapped_column(LargeBinary)
    expira_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopuri: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    stare_oauth: Mapped[bytes | None] = mapped_column(LargeBinary)
    autorizat_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cere_reautorizare: Mapped[bool] = mapped_column(Boolean, default=False)
    setari: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    actualizat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AprobareApi(BazaPublicare):
    """Aprobarea aplicației agenției la o platformă, pe permisiune (App Review, audit). Date de agenție."""

    __tablename__ = "aprobari_api"
    platforma: Mapped[str] = mapped_column(Text, primary_key=True)
    permisiune: Mapped[str] = mapped_column(Text, primary_key=True)
    stare: Mapped[str] = mapped_column(Text)
    inregistrare: Mapped[str | None] = mapped_column(Text)
    trimisa_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decisa_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observatii: Mapped[str] = mapped_column(Text, default="")
    actualizat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
