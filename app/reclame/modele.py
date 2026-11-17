"""Tabelele reclamelor (F13). Cheile străine și constrângerile sunt în migrări (`0070`…)."""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class BazaReclame(DeclarativeBase):
    pass


class ContReclame(BazaReclame):
    """Contul de reclame al unui client la o platformă, cu plafoanele și regulile gardianului (0070)."""

    __tablename__ = "reclame_conturi"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    platforma: Mapped[str] = mapped_column(Text)
    cont_extern: Mapped[str] = mapped_column(Text)
    nume: Mapped[str] = mapped_column(Text)
    moneda: Mapped[str] = mapped_column(Text, default="RON")
    al_agentiei: Mapped[bool] = mapped_column(Boolean, default=False)
    activ: Mapped[bool] = mapped_column(Boolean, default=True)
    plafon_zilnic_bani: Mapped[int] = mapped_column(BigInteger)
    plafon_lunar_bani: Mapped[int] = mapped_column(BigInteger)
    plafon_campanie_bani: Mapped[int] = mapped_column(BigInteger)
    schimbare_max_pct: Mapped[int] = mapped_column(Integer, default=20)
    asteptare_ore: Mapped[int] = mapped_column(Integer, default=48)
    schimbari_pe_zi: Mapped[int] = mapped_column(Integer, default=5)
    citit_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    eroare_citire: Mapped[str | None] = mapped_column(Text)
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RezultatReclame(BazaReclame):
    """Cifrele unei zile pentru o campanie sau o reclamă, cum le arată platforma (migrarea 0070)."""

    __tablename__ = "reclame_rezultate"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    cont_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    nivel: Mapped[str] = mapped_column(Text, primary_key=True)
    obiect_extern: Mapped[str] = mapped_column(Text, primary_key=True)
    zi: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    nume: Mapped[str] = mapped_column(Text, default="")
    parinte_extern: Mapped[str] = mapped_column(Text, default="")
    cheltuiala_bani: Mapped[int] = mapped_column(BigInteger)
    afisari: Mapped[int] = mapped_column(BigInteger)
    clicuri: Mapped[int] = mapped_column(BigInteger)
    rezultate: Mapped[int] = mapped_column(Integer)
    citit_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlanMediaRand(BazaReclame):
    """Un plan media (F13.3, migrarea 0071). Conținutul e `plan.PlanMedia` ca JSON."""

    __tablename__ = "reclame_planuri"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    cont_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    continut: Mapped[dict[str, Any]] = mapped_column(JSONB)
    probleme: Mapped[list[str]] = mapped_column(JSONB, default=list)
    stare: Mapped[str] = mapped_column(Text, default="propus")
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decis_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decis_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Campanie(BazaReclame):
    """O campanie construită din planul aprobat (F13.4, migrarea 0072). Se creează în pauză."""

    __tablename__ = "reclame_campanii"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    cont_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    plan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    nume: Mapped[str] = mapped_column(Text)
    rol: Mapped[str] = mapped_column(Text)
    variabila: Mapped[str | None] = mapped_column(Text)
    id_extern: Mapped[str | None] = mapped_column(Text)
    stare: Mapped[str] = mapped_column(Text, default="in_constructie")
    buget_zilnic_bani: Mapped[int] = mapped_column(BigInteger)
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    schimbat_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Anunt(BazaReclame):
    """O reclamă (creativul) dintr-o campanie (migrarea 0072)."""

    __tablename__ = "reclame_anunturi"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    campanie_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    nume: Mapped[str] = mapped_column(Text)
    varianta: Mapped[str] = mapped_column(Text, default="")
    titlu: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    link: Mapped[str] = mapped_column(Text)
    generat_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    id_extern: Mapped[str | None] = mapped_column(Text)
    stare: Mapped[str] = mapped_column(Text, default="in_constructie")
    verificare: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Propunere(BazaReclame):
    """O schimbare tipizată, cu starea de dinainte și de după (F13.4, migrarea 0072)."""

    __tablename__ = "reclame_propuneri"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    cont_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    campanie_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    anunt_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    tip: Mapped[str] = mapped_column(Text)
    inainte: Mapped[dict[str, Any]] = mapped_column(JSONB)
    dupa: Mapped[dict[str, Any]] = mapped_column(JSONB)
    motiv: Mapped[str] = mapped_column(Text)
    sursa: Mapped[str] = mapped_column(Text)
    stare: Mapped[str] = mapped_column(Text, default="propusa")
    verdict: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    efect_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    anuleaza_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decis_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decis_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    aplicat_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class DecizieReclame(BazaReclame):
    """O înregistrare de decizie (F13.6–F13.7, migrarea 0073): ce s-a văzut, ce s-a decis, ce se așteaptă."""

    __tablename__ = "reclame_decizii"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    cont_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    campanie_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    sursa: Mapped[str] = mapped_column(Text)
    de_la: Mapped[dt.date] = mapped_column(Date)
    pana_la: Mapped[dt.date] = mapped_column(Date)
    observat: Mapped[dict[str, Any]] = mapped_column(JSONB)
    iesire: Mapped[str] = mapped_column(Text)
    motiv: Mapped[str] = mapped_column(Text)
    alternative: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    asteptat: Mapped[str] = mapped_column(Text, default="")
    verificare_la: Mapped[dt.date] = mapped_column(Date)
    propuneri: Mapped[list[str]] = mapped_column(JSONB, default=list)
    model: Mapped[str | None] = mapped_column(Text)
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DosarConsiliu(BazaReclame):
    """Un dosar de Consiliu și decizia lui (F13.7, migrarea 0074)."""

    __tablename__ = "reclame_dosare"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    cont_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    subiect: Mapped[str] = mapped_column(Text)
    motiv_apel: Mapped[str] = mapped_column(Text)
    continut: Mapped[str] = mapped_column(Text)
    optiuni: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    mod: Mapped[str] = mapped_column(Text, default="manual")
    stare: Mapped[str] = mapped_column(Text, default="deschis")
    luna: Mapped[dt.date] = mapped_column(Date)
    decizie: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    decizie_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decis_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decis_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
