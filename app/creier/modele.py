"""Tabelele Creierului (migrările 0021, 0023, 0024 și 0025).

Cheile străine există în bază, nu se declară aici."""

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


class Pasaj(BazaCreier):
    """O bucată dintr-un document colectat, cu textul normalizat pentru căutare. Coloanele `embedding`
    (pgvector) și
    `fts` (tsvector generat) nu se mapează: se ating doar prin SQL (`indexare`, `cautare`)."""

    __tablename__ = "pasaje"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    sursa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    pozitie: Mapped[int] = mapped_column(Integer)
    car_inceput: Mapped[int] = mapped_column(Integer)
    car_sfarsit: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    text_normalizat: Mapped[str] = mapped_column(Text)
    hash_document: Mapped[str] = mapped_column(Text)
    compartiment: Mapped[str | None] = mapped_column(Text)
    model_vectori: Mapped[str | None] = mapped_column(Text)
    vectorizat_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Extragere(BazaCreier):
    """Un pasaj extras cu o versiune de prompt: câte fapte a dat și ce a respins verificatorul de citate."""

    __tablename__ = "creier_extrageri"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    pasaj_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    prompt: Mapped[str] = mapped_column(Text)
    propuse: Mapped[int] = mapped_column(Integer, default=0)
    duplicate: Mapped[int] = mapped_column(Integer, default=0)
    respinse: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    model: Mapped[str | None] = mapped_column(Text)
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PachetContextRand(BazaCreier):
    """Un pachet de context salvat (F4.7). Doar adăugări; conținutul este instantaneul trimis sarcinii."""

    __tablename__ = "pachete_context"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    livrabil_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    tip_sarcina: Mapped[str] = mapped_column(Text)
    canal: Mapped[str | None] = mapped_column(Text)
    intrebare: Mapped[str] = mapped_column(Text)
    la: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    buget_tokeni: Mapped[int] = mapped_column(Integer)
    tokeni_folositi: Mapped[int] = mapped_column(Integer)
    depasit: Mapped[bool] = mapped_column(default=False)
    amprenta: Mapped[str] = mapped_column(Text)
    continut: Mapped[dict[str, Any]] = mapped_column(JSONB)
    lipsuri: Mapped[list[str]] = mapped_column(JSONB, default=list)
    taiate: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list)
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    creat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
