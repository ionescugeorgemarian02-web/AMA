"""Datele Shopify izolate pe tenant."""

import datetime as dt
import uuid

from sqlalchemy import DateTime, LargeBinary, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class Baza(DeclarativeBase):
    pass


class Magazin(Baza):
    __tablename__ = "comert_magazine"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID]
    magazin: Mapped[str] = mapped_column(Text, unique=True)
    token_criptat: Mapped[bytes | None] = mapped_column(LargeBinary)
    stare_hash: Mapped[bytes | None] = mapped_column(LargeBinary)
    expira_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Produs(Baza):
    __tablename__ = "comert_produse"
    tenant_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    magazin: Mapped[str] = mapped_column(Text, primary_key=True)
    id_extern: Mapped[str] = mapped_column(Text, primary_key=True)
    titlu: Mapped[str] = mapped_column(Text)
    activ: Mapped[bool]
    versiune: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
