"""Tabelele producției (migrările 0007 și următoarele). Cheile străine există în bază, nu se declară aici."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class BazaProductie(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)


class Livrabil(BazaProductie):
    """O postare, un articol, un video, o reclamă. Fără conținut (vine în F4–F6): doar identitate, stare,
    versiune și contoare. `stare` se schimbă DOAR prin `tranzitii.muta` (declanșator în bază + gardă)."""

    __tablename__ = "livrabile"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    tip: Mapped[str] = mapped_column(Text)
    canal: Mapped[str] = mapped_column(Text)
    clasa_actiune: Mapped[str] = mapped_column(Text, default="publicare_continut")
    termen_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nu_inainte_de: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # amânat de A4 (F3.11)
    stare: Mapped[str] = mapped_column(Text, default="planificat")
    stare_anterioara: Mapped[str | None] = mapped_column(Text)
    versiune: Mapped[int] = mapped_column(Integer, default=1)
    runde_reparatie: Mapped[int] = mapped_column(Integer, default=0)
    predari: Mapped[int] = mapped_column(Integer, default=0)
    apeluri_llm: Mapped[int] = mapped_column(Integer, default=0)
    timp_sec: Mapped[float] = mapped_column(Float, default=0.0)
    buget_apeluri_llm: Mapped[int] = mapped_column(Integer)
    buget_timp_sec: Mapped[int] = mapped_column(Integer)
    escaladari: Mapped[int] = mapped_column(Integer, default=0)
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Tranzitie(BazaProductie):
    """Istoric doar-adăugare: tranzițiile aplicate ȘI cele refuzate (`rezultat`)."""

    __tablename__ = "livrabile_tranzitii"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    livrabil_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    rezultat: Mapped[str] = mapped_column(Text)
    din: Mapped[str | None] = mapped_column(Text)
    in_stare: Mapped[str] = mapped_column(Text)
    componenta: Mapped[str] = mapped_column(Text)
    actor_tip: Mapped[str] = mapped_column(Text)
    utilizator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    motiv: Mapped[str] = mapped_column(Text, default="")
    detalii: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    versiune: Mapped[int] = mapped_column(Integer)
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())


class Aprobare(BazaProductie):
    """O cerere de aprobare pentru o VERSIUNE a unui livrabil (F2.8). O decizie înregistrată nu se schimbă."""

    __tablename__ = "aprobari"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    livrabil_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    versiune: Mapped[int] = mapped_column(Integer)
    clasa_actiune: Mapped[str] = mapped_column(Text)
    decident: Mapped[str] = mapped_column(Text)
    stare: Mapped[str] = mapped_column(Text, default="in_asteptare")
    termen_la: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reamintire_la: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reamintit_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motiv_cod: Mapped[str | None] = mapped_column(Text)
    motiv: Mapped[str | None] = mapped_column(Text)
    decis_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decis_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NivelAutonomie(BazaProductie):
    """Nivelul de autonomie (0–4) al unui client pentru o clasă de acțiune. Fără rând = implicit L1."""

    __tablename__ = "autonomie_niveluri"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    clasa: Mapped[str] = mapped_column(Text, primary_key=True)
    nivel: Mapped[int] = mapped_column(Integer)
    motiv: Mapped[str] = mapped_column(Text, default="")
    schimbat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    schimbat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SchimbareAutonomie(BazaProductie):
    """Istoric doar-adăugare al schimbărilor de nivel (setări ale proprietarului și retrogradări automate)."""

    __tablename__ = "autonomie_istoric"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    clasa: Mapped[str] = mapped_column(Text)
    de_la: Mapped[int] = mapped_column(Integer)
    la: Mapped[int] = mapped_column(Integer)
    tip: Mapped[str] = mapped_column(Text)
    utilizator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    motiv: Mapped[str] = mapped_column(Text, default="")
    referinta: Mapped[str] = mapped_column(Text, default="")
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
