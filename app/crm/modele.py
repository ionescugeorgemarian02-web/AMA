"""Tabelele CRM-ului minimal (migrarea 0094). Date ale agenției: doar contextul de agenție le vede."""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class BazaCrm(DeclarativeBase):
    pass


def _id() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)


class Firma(BazaCrm):
    __tablename__ = "crm_firme"
    id: Mapped[uuid.UUID] = _id()
    nume: Mapped[str] = mapped_column(Text)
    nume_norm: Mapped[str] = mapped_column(Text)
    domeniu: Mapped[str | None] = mapped_column(Text)
    unita_in: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Contact(BazaCrm):
    __tablename__ = "crm_contacte"
    id: Mapped[uuid.UUID] = _id()
    firma_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    email: Mapped[str] = mapped_column(Text)
    nume: Mapped[str] = mapped_column(Text, default="")
    telefon: Mapped[str] = mapped_column(Text, default="")
    sursa: Mapped[str] = mapped_column(Text)
    temei: Mapped[str] = mapped_column(Text)
    tara: Mapped[str] = mapped_column(Text, default="RO")
    unit_in: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Consimtamant(BazaCrm):
    """Un rând din istoricul consimțământului. Nu se schimbă și nu se șterge."""

    __tablename__ = "crm_consimtamant"
    id: Mapped[uuid.UUID] = _id()
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    scop: Mapped[str] = mapped_column(Text)
    acordat: Mapped[bool] = mapped_column(Boolean)
    sursa: Mapped[str] = mapped_column(Text)
    temei: Mapped[str] = mapped_column(Text)
    dovada: Mapped[str] = mapped_column(Text, default="")
    la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LeadCrm(BazaCrm):
    __tablename__ = "crm_leaduri"
    id: Mapped[uuid.UUID] = _id()
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    firma_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    sursa: Mapped[str] = mapped_column(Text)
    temei: Mapped[str] = mapped_column(Text)
    etapa: Mapped[str] = mapped_column(Text, default="nou")
    motiv_pierdere: Mapped[str] = mapped_column(Text, default="")
    lead_site_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Activitate(BazaCrm):
    __tablename__ = "crm_activitati"
    id: Mapped[uuid.UUID] = _id()
    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    tip: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    utilizator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Sarcina(BazaCrm):
    __tablename__ = "crm_sarcini"
    id: Mapped[uuid.UUID] = _id()
    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    cheie: Mapped[str] = mapped_column(Text)
    titlu: Mapped[str] = mapped_column(Text)
    scadenta: Mapped[dt.date] = mapped_column(Date)
    stare: Mapped[str] = mapped_column(Text, default="deschisa")
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    inchisa_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Suprimare(BazaCrm):
    """O adresă din lista globală de suprimare (migrarea 0095). Nu se șterge prin aplicație."""

    __tablename__ = "crm_suprimari"
    email: Mapped[str] = mapped_column(Text, primary_key=True)
    motiv: Mapped[str] = mapped_column(Text)
    sursa: Mapped[str] = mapped_column(Text, default="")
    la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RegulaTara(BazaCrm):
    __tablename__ = "crm_matrice_tari"
    tara: Mapped[str] = mapped_column(Text, primary_key=True)
    tip_destinatar: Mapped[str] = mapped_column(Text, primary_key=True)
    regula: Mapped[str] = mapped_column(Text)
    mentiuni: Mapped[str] = mapped_column(Text, default="")
    verificat_de: Mapped[str] = mapped_column(Text)
    verificat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Trimitere(BazaCrm):
    __tablename__ = "crm_trimiteri"
    id: Mapped[uuid.UUID] = _id()
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    email: Mapped[str] = mapped_column(Text)
    campanie: Mapped[str] = mapped_column(Text)
    cheie: Mapped[str] = mapped_column(Text)
    la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InscriereSecventa(BazaCrm):
    """Un contact într-o secvență de emailuri (migrarea 0096)."""

    __tablename__ = "crm_secvente"
    id: Mapped[uuid.UUID] = _id()
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    lead_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    secventa: Mapped[str] = mapped_column(Text)
    pas: Mapped[int] = mapped_column(Integer, default=0)
    pornita_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    urmatorul_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    stare: Mapped[str] = mapped_column(Text, default="activa")
    motiv_oprire: Mapped[str] = mapped_column(Text, default="")


class Calificare(BazaCrm):
    """Răspunsurile de calificare, scorul și grupa unui lead (migrarea 0097). Doar cu adăugare."""

    __tablename__ = "crm_calificari"
    id: Mapped[uuid.UUID] = _id()
    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    raspunsuri: Mapped[dict[str, str]] = mapped_column(JSONB)
    scor: Mapped[int] = mapped_column(Integer)
    grupa: Mapped[str] = mapped_column(Text)
    la_om: Mapped[bool] = mapped_column(Boolean, default=False)
    motive: Mapped[list[str]] = mapped_column(JSONB, default=list)
    sursa: Mapped[str] = mapped_column(Text)
    la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Programare(BazaCrm):
    """Un apel rezervat (migrarea 0098)."""

    __tablename__ = "crm_programari"
    id: Mapped[uuid.UUID] = _id()
    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    tip: Mapped[str] = mapped_column(Text)
    inceput: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    sfarsit: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    stare: Mapped[str] = mapped_column(Text, default="confirmata")
    jeton_hash: Mapped[str] = mapped_column(Text)
    reamintit_24h: Mapped[bool] = mapped_column(Boolean, default=False)
    reamintit_1h: Mapped[bool] = mapped_column(Boolean, default=False)
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    anulat_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Oferta(BazaCrm):
    """O ofertă scrisă din audit și din pachete, în așteptarea aprobării (migrarea 0099)."""

    __tablename__ = "crm_oferte"
    id: Mapped[uuid.UUID] = _id()
    lead_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    pachet: Mapped[str] = mapped_column(Text)
    pret_lunar: Mapped[int] = mapped_column(Integer)
    setup: Mapped[int] = mapped_column(Integer)
    continut: Mapped[dict[str, Any]] = mapped_column(JSONB)
    verificari: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    stare: Mapped[str] = mapped_column(Text, default="de_aprobat")
    motiv: Mapped[str] = mapped_column(Text, default="")
    decis_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decis_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class CanalInbox(BazaCrm):
    """Un canal social aprobat pentru citire (migrarea 0100)."""

    __tablename__ = "crm_inbox_canale"
    canal: Mapped[str] = mapped_column(Text, primary_key=True)
    aprobat_de: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    aprobat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activ: Mapped[bool] = mapped_column(Boolean, default=True)
    nivel: Mapped[str] = mapped_column(Text, default="L1")  # migrarea 0101
    citit_pana_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class MesajInbox(BazaCrm):
    """Un mesaj sau un comentariu citit din inboxul social, clasificat (migrarea 0100)."""

    __tablename__ = "crm_inbox_mesaje"
    id: Mapped[uuid.UUID] = _id()
    canal: Mapped[str] = mapped_column(Text)
    id_extern: Mapped[str] = mapped_column(Text)
    tip: Mapped[str] = mapped_column(Text)
    fir: Mapped[str] = mapped_column(Text)
    autor: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    primit_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    clasa: Mapped[str] = mapped_column(Text)
    motiv_clasa: Mapped[str] = mapped_column(Text, default="")
    stare: Mapped[str] = mapped_column(Text, default="nou")
    de_verificat: Mapped[bool] = mapped_column(Boolean, default=False)  # migrarea 0101
    citit_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RaspunsInbox(BazaCrm):
    """Un răspuns propus sau trimis în inboxul social (migrarea 0101)."""

    __tablename__ = "crm_inbox_raspunsuri"
    id: Mapped[uuid.UUID] = _id()
    mesaj_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    text: Mapped[str] = mapped_column(Text)
    autor: Mapped[str] = mapped_column(Text)
    utilizator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    stare: Mapped[str] = mapped_column(Text)
    motiv: Mapped[str] = mapped_column(Text, default="")
    eticheta_agent_uman: Mapped[bool] = mapped_column(Boolean, default=False)
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    trimis_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
