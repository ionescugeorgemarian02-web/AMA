"""Modelele ORM ale modulului conturi. Schema o definesc migrările; testele prind abaterile."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, LargeBinary, Text, func
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class Baza(DeclarativeBase):
    pass


def _timp() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Client(Baza):
    __tablename__ = "clienti"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    nume: Mapped[str] = mapped_column(Text)
    stare: Mapped[str] = mapped_column(Text, default="activ")
    creat_la: Mapped[datetime] = _timp()
    actualizat_la: Mapped[datetime] = _timp()
    sters_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Utilizator(Baza):
    __tablename__ = "utilizatori"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(CITEXT)
    nume_afisat: Mapped[str] = mapped_column(Text)
    parola_hash: Mapped[str] = mapped_column(Text)
    stare: Mapped[str] = mapped_column(Text, default="activ")
    totp_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    totp_activ: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_ultim_pas: Mapped[int | None] = mapped_column(BigInteger)
    creat_la: Mapped[datetime] = _timp()
    actualizat_la: Mapped[datetime] = _timp()
    sters_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Apartenenta(Baza):
    __tablename__ = "apartenente"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    utilizator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("utilizatori.id"))
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clienti.id"))
    rol: Mapped[str] = mapped_column(Text)
    creat_la: Mapped[datetime] = _timp()
    sters_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Alocare(Baza):
    __tablename__ = "alocari"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    utilizator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("utilizatori.id"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clienti.id"))
    creat_la: Mapped[datetime] = _timp()


class Sesiune(Baza):
    __tablename__ = "sesiuni"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary)
    utilizator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("utilizatori.id"))
    tenant_activ_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clienti.id"))
    mfa_verificat: Mapped[bool] = mapped_column(Boolean)
    csrf_token: Mapped[str] = mapped_column(Text)
    creat_la: Mapped[datetime] = _timp()
    ultima_activitate: Mapped[datetime] = _timp()
    expira_absolut: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revocata_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)


class CodRecuperare(Baza):
    __tablename__ = "coduri_recuperare"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    utilizator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("utilizatori.id"))
    cod_hash: Mapped[bytes] = mapped_column(LargeBinary)
    creat_la: Mapped[datetime] = _timp()
    folosit_la: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
