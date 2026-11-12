"""Tabelele gateway-ului (migrările 0012 și următoarele). Cheile străine există în bază, nu se declară "
"aici."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.ids import new_id


class BazaGateway(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)


class Furnizor(BazaGateway):
    """Un furnizor de modele. Cheia de API nu e aici: `cheie_env` este NUMELE variabilei de mediu."""

    __tablename__ = "gateway_furnizori"
    id: Mapped[uuid.UUID] = _uuid_pk()
    cod: Mapped[str] = mapped_column(Text)
    nume: Mapped[str] = mapped_column(Text)
    tip_api: Mapped[str] = mapped_column(Text)
    url_baza: Mapped[str] = mapped_column(Text)
    cheie_env: Mapped[str] = mapped_column(Text)
    stare: Mapped[str] = mapped_column(Text, default="inactiv")
    stare_motiv: Mapped[str] = mapped_column(Text, default="")
    platit: Mapped[bool] = mapped_column(Boolean, default=False)
    uz_comercial: Mapped[bool | None] = mapped_column(Boolean)
    antrenare_pe_date: Mapped[bool | None] = mapped_column(Boolean)
    restrictii_regionale: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    marcaj: Mapped[str] = mapped_column(Text)
    verificat_la: Mapped[dt.date | None] = mapped_column(Date)
    sursa: Mapped[str] = mapped_column(Text, default="")
    cereri_minut: Mapped[int | None] = mapped_column(Integer)
    cereri_zi: Mapped[int | None] = mapped_column(Integer)
    tokeni_minut: Mapped[int | None] = mapped_column(Integer)
    tokeni_zi: Mapped[int | None] = mapped_column(Integer)
    reset_zi_ora: Mapped[int] = mapped_column(SmallInteger, default=0)
    erori_consecutive: Mapped[int] = mapped_column(Integer, default=0)
    intrerupt_pana_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    ultima_eroare_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    ultimul_succes_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    parametri: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelLlm(BazaGateway):
    __tablename__ = "gateway_modele"
    id: Mapped[uuid.UUID] = _uuid_pk()
    furnizor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    identificator: Mapped[str] = mapped_column(Text)
    nume_afisat: Mapped[str] = mapped_column(Text)
    nivel: Mapped[str] = mapped_column(Text)
    context_tokeni: Mapped[int] = mapped_column(Integer)
    capabilitati: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    activ: Mapped[bool] = mapped_column(Boolean, default=True)
    cereri_minut: Mapped[int | None] = mapped_column(Integer)
    cereri_zi: Mapped[int | None] = mapped_column(Integer)
    tokeni_minut: Mapped[int | None] = mapped_column(Integer)
    tokeni_zi: Mapped[int | None] = mapped_column(Integer)
    pret_umbra_intrare: Mapped[Decimal] = mapped_column(default=Decimal(0))
    pret_umbra_iesire: Mapped[Decimal] = mapped_column(default=Decimal(0))
    scor: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    marcaj: Mapped[str] = mapped_column(Text)
    verificat_la: Mapped[dt.date | None] = mapped_column(Date)
    sursa: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def cheie(self) -> str:
        return str(self.id)


class ProfilSarcina(BazaGateway):
    """Un profil de sarcină (8.2): lanțul de modele și ce se întâmplă când se epuizează."""

    __tablename__ = "gateway_profiluri"
    nume: Mapped[str] = mapped_column(Text, primary_key=True)
    eticheta: Mapped[str] = mapped_column(Text)
    descriere: Mapped[str] = mapped_column(Text, default="")
    nivel_min: Mapped[str] = mapped_column(Text)
    capabilitati: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    lant: Mapped[list[str]] = mapped_column(ARRAY(Text))
    la_epuizare: Mapped[str] = mapped_column(Text)
    lant_degradare: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    verificare_in_plus: Mapped[bool] = mapped_column(Boolean, default=False)
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PromptGateway(BazaGateway):
    """Un prompt versionat (8.8). Conținutul unei versiuni care nu mai e ciornă nu se modifică
    (declanșator în bază)."""

    __tablename__ = "gateway_prompturi"
    id: Mapped[uuid.UUID] = _uuid_pk()
    nume: Mapped[str] = mapped_column(Text)
    versiune: Mapped[int] = mapped_column(Integer)
    stare: Mapped[str] = mapped_column(Text, default="ciorna")
    profil: Mapped[str] = mapped_column(Text)
    sistem: Mapped[str] = mapped_column(Text, default="")
    sablon: Mapped[str] = mapped_column(Text)
    schema_nume: Mapped[str] = mapped_column(Text)
    schema_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    descriere: Mapped[str] = mapped_column(Text, default="")
    amprenta: Mapped[str] = mapped_column(Text)
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    creat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    activat_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    retras_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Apel(BazaGateway):
    """Un apel prin gateway (metadate, păstrate). Cu `tenant_id` și RLS; doar adăugări."""

    __tablename__ = "gateway_apeluri"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    livrabil_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    componenta: Mapped[str] = mapped_column(Text)
    prioritate: Mapped[str] = mapped_column(Text)
    profil: Mapped[str] = mapped_column(Text, default="")
    prompt_nume: Mapped[str] = mapped_column(Text, default="")
    prompt_versiune: Mapped[int | None] = mapped_column(Integer)
    furnizor: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(Text, default="")
    nivel: Mapped[str] = mapped_column(Text, default="")
    motiv_alegere: Mapped[str] = mapped_column(Text, default="")
    rezultat: Mapped[str] = mapped_column(Text)
    cod_eroare: Mapped[str] = mapped_column(Text, default="")
    tokeni_intrare: Mapped[int] = mapped_column(Integer, default=0)
    tokeni_iesire: Mapped[int] = mapped_column(Integer, default=0)
    durata_ms: Mapped[int] = mapped_column(Integer, default=0)
    reparatii: Mapped[int] = mapped_column(SmallInteger, default=0)
    pret_umbra: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal(0))
    degradat: Mapped[bool] = mapped_column(Boolean, default=False)
    provizoriu: Mapped[bool] = mapped_column(Boolean, default=False)
    verificare_suplimentara: Mapped[bool] = mapped_column(Boolean, default=False)
    incercari: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    corelare_id: Mapped[str] = mapped_column(Text, default="")
    semnale: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApelContinut(BazaGateway):
    """Conținutul unui apel (mesajele trimise, răspunsul validat): 30 de zile, apoi se șterge; rămân
    metadatele."""

    __tablename__ = "gateway_apeluri_continut"
    apel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    mesaje: Mapped[list[dict[str, str]]] = mapped_column(JSONB)
    raspuns: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    expira_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
