"""Tabelele executorului de efecte (migrarea 0011)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class BazaEfecte(DeclarativeBase):
    pass


class Efect(BazaEfecte):
    """Un efect extern cerut („outbox”). `stare` se schimbă doar prin `servicii.muta_efect` (tabelul
    din `stari`)."""

    __tablename__ = "efecte_de_trimis"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    livrabil_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    canal: Mapped[str] = mapped_column(Text)
    versiune: Mapped[int] = mapped_column(Integer)
    tip: Mapped[str] = mapped_column(Text)
    cheia: Mapped[str] = mapped_column(Text, unique=True)
    stare: Mapped[str] = mapped_column(Text, default="in_asteptare")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    incercari: Mapped[int] = mapped_column(Integer, default=0)
    rulari: Mapped[int] = mapped_column(Integer, default=0)
    programat_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    id_extern: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(Text)
    eroare_cod: Mapped[str | None] = mapped_column(Text)
    eroare_mesaj: Mapped[str | None] = mapped_column(Text)
    motiv: Mapped[str] = mapped_column(Text, default="")
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    trimis_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PauzaConector(BazaEfecte):
    """Canalul unui client, pus pe pauză după o eroare de autentificare. Până la reautorizare nu pleacă
    nimic."""

    __tablename__ = "conectori_pauze"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    canal: Mapped[str] = mapped_column(Text, primary_key=True)
    motiv: Mapped[str] = mapped_column(Text, default="")
    de_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
