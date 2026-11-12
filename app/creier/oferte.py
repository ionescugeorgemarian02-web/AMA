"""Catalogul de oferte (F4.6, docs/10 §10.1): produse, servicii, pachete, abonamente, promoții, cu preț,
monedă, condiții și
valabilitate, LEGATE de faptele din registru. Stă peste depozitul versionat (compartimentul `catalog_oferte`).

Regula de integritate: o ofertă intră în context doar dacă TOATE faptele de care e legată sunt, la rândul lor,
aprobate și
valabile la data cerută (o ofertă al cărei fapt a expirat dispare din context odată cu el). Reducerile cer
preț de referință
(docs/21 §21.11). Aceleași reguli de sursă ca la fapte (citat literal în pasaj / document).
"""

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.creier import fapte as registru
from app.creier import pasaje as nucleu
from app.creier import versiuni as v
from app.creier.compartimente import Compartiment, inregistreaza_schema
from app.creier.modele import IntrareCreier, VersiuneCreier
from app.creier.versiuni import RegulaCreier, Sursa


class TipOferta(StrEnum):
    PRODUS = "produs"
    SERVICIU = "serviciu"
    PACHET = "pachet"
    ABONAMENT = "abonament"
    PROMOTIE = "promotie"


class Pret(BaseModel):
    model_config = ConfigDict(extra="forbid")
    numar: Decimal = Field(ge=0)
    moneda: str = Field(default="RON", pattern=r"^[A-Z]{3}$")
    unitate: str | None = Field(default=None, max_length=40)  # „250 g”, „lună”, „persoană”


class ContinutOferta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tip: TipOferta
    nume: str = Field(min_length=1, max_length=160)
    descriere: str = Field(default="", max_length=600)
    pret: Pret
    pret_referinta: Pret | None = None  # obligatoriu la promoții (21.11)
    conditii: str = Field(default="", max_length=600)
    garantie: str = Field(default="", max_length=300)
    fapte: list[str] = Field(
        default_factory=list, max_length=20
    )  # identificatori de intrări din registrul de fapte

    @model_validator(mode="after")
    def _promotia_are_pret_de_referinta(self) -> "ContinutOferta":
        if self.tip is TipOferta.PROMOTIE and self.pret_referinta is None:
            raise ValueError("o promoție cere prețul de referință")
        if self.pret_referinta is not None and self.pret_referinta.numar <= self.pret.numar:
            raise ValueError("prețul de referință trebuie să fie mai mare decât prețul redus")
        return self


inregistreaza_schema(Compartiment.CATALOG_OFERTE, ContinutOferta)


def cheie_oferta(tip: str, nume: str) -> str:
    return "o-" + hashlib.sha256(f"{tip}|{nucleu.normalizeaza(nume)}".encode()).hexdigest()[:24]


def _verifica_legaturi(db: Session, tenant_id: uuid.UUID, c: ContinutOferta) -> None:
    for brut in c.fapte:
        try:
            fid = uuid.UUID(brut)
        except ValueError:
            raise RegulaCreier("o ofertă se leagă de fapte prin identificatorul intrării") from None
        i = db.get(IntrareCreier, fid)
        if i is None or i.tenant_id != tenant_id or i.compartiment != Compartiment.REGISTRU_FAPTE.value:
            raise RegulaCreier("oferta trimite la un fapt care nu există în registrul clientului")


def propune_oferta(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    continut: ContinutOferta | dict[str, Any],
    sursa: Sursa,
    valabil_de_la: dt.datetime | None = None,
    valabil_pana_la: dt.datetime | None = None,
    utilizator_id: uuid.UUID | None = None,
    acum: dt.datetime | None = None,
) -> tuple[IntrareCreier, VersiuneCreier, bool]:
    """O ofertă nouă, `propusă`. Aceeași ofertă (tip + nume) nu se propune de două ori: dacă există, se
    întoarce ea
    (`creat=False`); schimbarea ei se face cu `modifica_oferta`."""
    c = continut if isinstance(continut, ContinutOferta) else ContinutOferta.model_validate(continut)
    registru.verifica_sursa(db, tenant_id, sursa, valoare_numar=format(c.pret.numar.normalize(), "f"))
    _verifica_legaturi(db, tenant_id, c)
    cheie = cheie_oferta(c.tip.value, c.nume)
    existenta = v.gaseste_intrare(
        db, tenant_id=tenant_id, compartiment=Compartiment.CATALOG_OFERTE, cheie=cheie
    )
    if existenta is not None:
        return existenta, v.istoric(db, existenta.id)[-1], False
    intrare, ver = v.creeaza_intrare(
        db,
        tenant_id=tenant_id,
        compartiment=Compartiment.CATALOG_OFERTE,
        cheie=cheie,
        continut=c.model_dump(mode="json"),
        sursa=sursa,
        valabil_de_la=valabil_de_la,
        valabil_pana_la=valabil_pana_la,
        utilizator_id=utilizator_id,
        acum=acum,
    )
    return intrare, ver, True


def modifica_oferta(
    db: Session,
    intrare_id: uuid.UUID,
    *,
    continut: ContinutOferta | dict[str, Any],
    sursa: Sursa,
    valabil_de_la: dt.datetime | None = None,
    valabil_pana_la: dt.datetime | None = None,
    motiv: str = "",
    utilizator_id: uuid.UUID | None = None,
    acum: dt.datetime | None = None,
) -> VersiuneCreier:
    i = v.intrare(db, intrare_id)
    if i.compartiment != Compartiment.CATALOG_OFERTE.value or i.tenant_id is None:
        raise RegulaCreier("intrarea nu este o ofertă")
    c = continut if isinstance(continut, ContinutOferta) else ContinutOferta.model_validate(continut)
    registru.verifica_sursa(db, i.tenant_id, sursa, valoare_numar=format(c.pret.numar.normalize(), "f"))
    _verifica_legaturi(db, i.tenant_id, c)
    return v.propune_schimbare(
        db,
        intrare_id,
        continut=c.model_dump(mode="json"),
        sursa=sursa,
        valabil_de_la=valabil_de_la,
        valabil_pana_la=valabil_pana_la,
        motiv=motiv,
        utilizator_id=utilizator_id,
        acum=acum,
    )


def aproba_oferta(
    db: Session,
    intrare_id: uuid.UUID,
    versiune: int,
    *,
    utilizator_id: uuid.UUID,
    acum: dt.datetime | None = None,
) -> VersiuneCreier:
    return v.aproba(db, intrare_id, versiune, utilizator_id=utilizator_id, acum=acum)


@dataclass(frozen=True)
class OfertaContext:
    intrare_id: uuid.UUID
    versiune: int
    tip: str
    nume: str
    descriere: str
    pret: dict[str, Any]
    pret_referinta: dict[str, Any] | None
    conditii: str
    garantie: str
    fapte: tuple[uuid.UUID, ...]
    sursa_tip: str
    sursa_ref: str | None
    valabil_de_la: dt.datetime | None
    valabil_pana_la: dt.datetime | None


def pentru_context(db: Session, tenant_id: uuid.UUID, la: dt.datetime) -> list[OfertaContext]:
    """SINGURA citire a ofertelor pentru context: doar versiuni aprobate și valabile la `la`, ale căror fapte
    legate sunt
    toate aprobate și valabile la `la`."""
    if la.tzinfo is None:
        raise RegulaCreier("data cerută trebuie să aibă fus orar (UTC)")
    fapte_ok = {f.intrare_id for f in registru.pentru_context(db, tenant_id, la)}
    q = (
        select(IntrareCreier, VersiuneCreier)
        .join(VersiuneCreier, VersiuneCreier.intrare_id == IntrareCreier.id)
        .where(
            IntrareCreier.tenant_id == tenant_id,
            IntrareCreier.compartiment == Compartiment.CATALOG_OFERTE.value,
            VersiuneCreier.aprobat_la.is_not(None),
            VersiuneCreier.aprobat_la <= la,
            VersiuneCreier.retras_la.is_(None) | (VersiuneCreier.retras_la > la),
            VersiuneCreier.valabil_de_la.is_(None) | (VersiuneCreier.valabil_de_la <= la),
            VersiuneCreier.valabil_pana_la.is_(None) | (VersiuneCreier.valabil_pana_la > la),
        )
        .order_by(IntrareCreier.cheie, VersiuneCreier.nr)
    )
    iesire: list[OfertaContext] = []
    for i, ver in db.execute(q).all():
        c = ver.continut
        legate = tuple(uuid.UUID(x) for x in c.get("fapte", []))
        if any(f not in fapte_ok for f in legate):
            continue
        iesire.append(
            OfertaContext(
                intrare_id=i.id,
                versiune=ver.nr,
                tip=c["tip"],
                nume=c["nume"],
                descriere=c.get("descriere", ""),
                pret=c["pret"],
                pret_referinta=c.get("pret_referinta"),
                conditii=c.get("conditii", ""),
                garantie=c.get("garantie", ""),
                fapte=legate,
                sursa_tip=ver.sursa_tip,
                sursa_ref=ver.sursa_ref,
                valabil_de_la=ver.valabil_de_la,
                valabil_pana_la=ver.valabil_pana_la,
            )
        )
    return iesire
