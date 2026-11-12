"""Tabelele cercetării (migrarea 0022). Cheile străine există în bază, nu se declară aici."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class BazaCercetare(DeclarativeBase):
    pass


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)


class SursaColectare(BazaCercetare):
    """O sursă de materiale a unui client: un site (se citește automat) sau materiale încărcate manual."""

    __tablename__ = "surse"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    tip: Mapped[str] = mapped_column(Text)  # site | manual
    statut: Mapped[str] = mapped_column(Text)  # cod din `statut.STATUTE`
    nume: Mapped[str] = mapped_column(Text)
    url_radacina: Mapped[str | None] = mapped_column(Text)
    activa: Mapped[bool] = mapped_column(default=True)
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    creat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Colectare(BazaCercetare):
    """O rulare a colectorului pe o sursă, cu starea și contoarele ei (derivate din paginile ei)."""

    __tablename__ = "colectari"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    sursa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    stare: Mapped[str] = mapped_column(Text, default="in_asteptare")
    limite: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    user_agent: Mapped[str] = mapped_column(Text)
    motiv_oprire: Mapped[str] = mapped_column(Text, default="")
    pagini_gasite: Mapped[int] = mapped_column(Integer, default=0)
    pagini_citite: Mapped[int] = mapped_column(Integer, default=0)
    pagini_sarite: Mapped[int] = mapped_column(Integer, default=0)
    pagini_nemodificate: Mapped[int] = mapped_column(Integer, default=0)
    pagini_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    linkuri_ignorate: Mapped[int] = mapped_column(Integer, default=0)
    octeti_cititi: Mapped[int] = mapped_column(BigInteger, default=0)
    cereri_http: Mapped[int] = mapped_column(Integer, default=0)
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    creat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    inceput_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sfarsit_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaginaColectata(BazaCercetare):
    """O adresă găsită și soarta ei: citită, sărită (cu motiv), nemodificată, duplicat, eroare."""

    __tablename__ = "colectari_pagini"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    colectare_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    url: Mapped[str] = mapped_column(Text)
    adancime: Mapped[int] = mapped_column(Integer, default=0)
    gasit_din: Mapped[str | None] = mapped_column(Text)
    stare: Mapped[str] = mapped_column(Text, default="in_asteptare")
    motiv: Mapped[str] = mapped_column(Text, default="")
    detaliu: Mapped[str] = mapped_column(Text, default="")
    cod_http: Mapped[int | None] = mapped_column(Integer)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    procesat_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Document(BazaCercetare):
    """Un document colectat sau încărcat: textul extras stă în bază, originalul pe disc (`cale_original`)."""

    __tablename__ = "documente_colectate"
    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    sursa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    tip: Mapped[str] = mapped_column(Text)  # pagina | text_lipit | fisier
    url: Mapped[str | None] = mapped_column(Text)
    titlu: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text)
    hash_continut: Mapped[str] = mapped_column(Text)  # sha256 al originalului
    hash_text: Mapped[str] = mapped_column(Text)  # sha256 al textului extras (deduplicare, reindexare)
    content_type: Mapped[str] = mapped_column(Text, default="")
    octeti: Mapped[int] = mapped_column(Integer, default=0)
    cale_original: Mapped[str | None] = mapped_column(Text)
    antete: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    versiune: Mapped[int] = mapped_column(Integer, default=1)
    colectare_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    colectat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    verificat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expira_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
