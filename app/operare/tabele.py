"""Tabelele operării: abonamente push, livrare, opriri, Telegram (migrarea 0005)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, LargeBinary, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class BazaOperare(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)


class AbonamentPush(BazaOperare):
    __tablename__ = "abonamente_push"
    id: Mapped[uuid.UUID] = _uuid_pk()
    utilizator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("utilizatori.id"))
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(Text)
    auth: Mapped[str] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ultima_trimitere: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CerereLivrare(BazaOperare):
    __tablename__ = "cereri_livrare"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tip: Mapped[str] = mapped_column(Text)
    imagine: Mapped[str | None] = mapped_column(Text)
    versiune: Mapped[str | None] = mapped_column(Text)
    stare: Mapped[str] = mapped_column(Text, default="solicitata")
    solicitat_de: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("utilizatori.id"))
    detalii: Mapped[str] = mapped_column(Text, default="")
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    actualizat_la: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class Livrare(BazaOperare):
    __tablename__ = "livrari"
    id: Mapped[uuid.UUID] = _uuid_pk()
    mediu: Mapped[str] = mapped_column(Text)
    cheie: Mapped[str] = mapped_column(Text)
    cerere_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    imagine: Mapped[str | None] = mapped_column(Text)
    versiune: Mapped[str | None] = mapped_column(Text)
    stare: Mapped[str] = mapped_column(Text)
    detalii: Mapped[str] = mapped_column(Text, default="")
    verificari: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    momentul: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())


class StareOprire(BazaOperare):
    __tablename__ = "oprituri"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tip: Mapped[str] = mapped_column(Text)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clienti.id"))
    activ: Mapped[bool] = mapped_column(Boolean, default=False)
    motiv: Mapped[str] = mapped_column(Text, default="")
    canal: Mapped[str] = mapped_column(Text)
    schimbat_de: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("utilizatori.id"))
    schimbat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActualizareTelegram(BazaOperare):
    __tablename__ = "telegram_actualizari"
    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    primit_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConfirmareTelegram(BazaOperare):
    __tablename__ = "telegram_confirmari"
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cod_hash: Mapped[bytes] = mapped_column(LargeBinary)
    tip: Mapped[str] = mapped_column(Text)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clienti.id"))
    expira_la: Mapped[datetime] = mapped_column(DateTime(timezone=True))
