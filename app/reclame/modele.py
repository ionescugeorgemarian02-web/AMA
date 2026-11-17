"""Tabelele reclamelor (F13). Cheile străine și constrângerile sunt în migrări (`0070`…)."""

import datetime as dt
import uuid

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
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


__all__ = ["BazaReclame", "ContReclame", "RezultatReclame"]
