"""Tabelele media (migrările 0042, 0047+): biblioteca de active a clientului, cu licența și generarea."""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import BigInteger, DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class BazaMedia(DeclarativeBase):
    pass


class Activ(BazaMedia):
    __tablename__ = "active"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    categorie: Mapped[str] = mapped_column(Text)
    mime: Mapped[str] = mapped_column(Text)
    marime: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(Text)
    cale: Mapped[str] = mapped_column(Text)
    nume_original: Mapped[str] = mapped_column(Text)
    sursa: Mapped[str] = mapped_column(Text)
    descriere: Mapped[str] = mapped_column(Text, default="")
    incarcat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    licenta: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    generare: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Tendinta(BazaMedia):
    """Inboxul de tendințe (docs/19 §19.2): linkuri și idei lipite de client."""

    __tablename__ = "tendinte"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    text: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    stare: Mapped[str] = mapped_column(Text, default="noua")
    creat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Pronuntie(BazaMedia):
    """Dicționarul de pronunție al clientului (F8.2): termen -> cum se citește."""

    __tablename__ = "pronuntii"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    termen: Mapped[str] = mapped_column(Text)
    pronuntie: Mapped[str] = mapped_column(Text)
    creat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FolosireActiv(BazaMedia):
    """Unde a fost folosit un activ (F8.4); baza refuză rândul dacă activul nu are licență."""

    __tablename__ = "folosiri_active"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    activ_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    scop: Mapped[str] = mapped_column(Text)
    obiect_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Randare(BazaMedia):
    """O randare video (F8.6): lista de montaj, starea, videoul rezultat, măsurătorile și controlul."""

    __tablename__ = "randari"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    livrabil_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lista: Mapped[dict[str, Any]] = mapped_column(JSONB)
    calitate: Mapped[str] = mapped_column(Text, default="final")
    stare: Mapped[str] = mapped_column(Text, default="in_lucru")
    activ_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    masuratori: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    control: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    terminat_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class SablonGrafic(BazaMedia):
    """Un șablon grafic al brandului (F8.10), ca date."""

    __tablename__ = "sabloane_grafice"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    tip: Mapped[str] = mapped_column(Text)
    versiune: Mapped[int] = mapped_column(default=1)
    definitie: Mapped[dict[str, Any]] = mapped_column(JSONB)
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
