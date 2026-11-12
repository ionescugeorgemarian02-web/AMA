"""Tabelele operării: abonamente push, livrare, opriri, Telegram (migrarea 0005), motor (migrarea 0006).

Cheile străine există în bază (migrarea); aici nu se declară, fiindcă `utilizatori` și `clienti` țin de alt
modul și alt `MetaData`."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, LargeBinary, Text, func
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
    utilizator_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
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
    solicitat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
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
    __tablename__ = "opriri"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tip: Mapped[str] = mapped_column(Text)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    activ: Mapped[bool] = mapped_column(Boolean, default=False)
    motiv: Mapped[str] = mapped_column(Text, default="")
    canal: Mapped[str] = mapped_column(Text)
    schimbat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
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
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    expira_la: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SemnalWorker(BazaOperare):
    """Un rând pe worker (migrarea 0006): bătaia de inimă a procesului `worker`."""

    __tablename__ = "worker_semnale"
    worker_id: Mapped[str] = mapped_column(Text, primary_key=True)
    pid: Mapped[int] = mapped_column(Integer)
    versiune: Mapped[str] = mapped_column(Text, default="")
    pornit_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ultimul_semnal: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    oprit_curat: Mapped[bool] = mapped_column(Boolean, default=False)
    oprit_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    semnalat_mort: Mapped[bool] = mapped_column(Boolean, default=False)


class EvenimentWorker(BazaOperare):
    __tablename__ = "worker_evenimente"
    id: Mapped[uuid.UUID] = _uuid_pk()
    worker_id: Mapped[str] = mapped_column(Text)
    tip: Mapped[str] = mapped_column(Text)
    la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    detalii: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class IntrareEroare(BazaOperare):
    """Coada de erori (22.5): contextul complet al unui job eșuat. Nu se șterge; se închide cu motiv."""

    __tablename__ = "coada_erori"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    workflow_id: Mapped[str] = mapped_column(Text, unique=True)
    flux: Mapped[str] = mapped_column(Text)
    pas: Mapped[str | None] = mapped_column(Text)
    stare_job: Mapped[str] = mapped_column(Text)
    coada: Mapped[str | None] = mapped_column(Text)
    executor_id: Mapped[str | None] = mapped_column(Text)
    eroare_tip: Mapped[str] = mapped_column(Text)
    eroare_mesaj: Mapped[str] = mapped_column(Text, default="")
    cauza: Mapped[str] = mapped_column(Text)
    severitate: Mapped[str] = mapped_column(Text)
    stare: Mapped[str] = mapped_column(Text, default="noua")
    reluari: Mapped[int] = mapped_column(Integer, default=0)
    reluat_ca: Mapped[str | None] = mapped_column(Text)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    creat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizat_la: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inchis_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inchis_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    motiv_inchidere: Mapped[str | None] = mapped_column(Text)
