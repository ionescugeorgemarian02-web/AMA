"""Tabelele facturării (migrarea 0043)."""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class BazaFinante(DeclarativeBase):
    pass


class Abonament(BazaFinante):
    __tablename__ = "abonamente"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    plan: Mapped[str] = mapped_column(Text)
    suma: Mapped[int] = mapped_column(Integer)
    email_facturare: Mapped[str] = mapped_column(Text)
    stare: Mapped[str] = mapped_column(Text, default="in_asteptare_plata")
    id_extern: Mapped[str | None] = mapped_column(Text)
    jeton_hash: Mapped[str] = mapped_column(Text)
    perioada_pana_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    restant_de_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    suspendat_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Factura(BazaFinante):
    __tablename__ = "facturi"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    abonament_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    id_extern: Mapped[str] = mapped_column(Text)
    suma: Mapped[int] = mapped_column(Integer)
    moneda: Mapped[str] = mapped_column(Text, default="RON")
    stare: Mapped[str] = mapped_column(Text)
    perioada_de_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    perioada_pana_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvenimentPlata(BazaFinante):
    """Webhook-urile primite (idempotență pe id-ul evenimentului; corpul, fără date de card)."""

    __tablename__ = "plati_evenimente"
    id_extern: Mapped[str] = mapped_column(Text, primary_key=True)
    tip: Mapped[str] = mapped_column(Text)
    corp: Mapped[dict[str, Any]] = mapped_column(JSONB)
    rezultat: Mapped[str] = mapped_column(Text, default="")
    primit_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
