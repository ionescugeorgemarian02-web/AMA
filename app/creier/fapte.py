"""Registrul de fapte (F4.6, docs/09 §9.3, docs/10 §10.1): afirmații atomice verificabile ale clientului, cu
SURSĂ,
stare și valabilitate. Stă peste depozitul versionat al Creierului (F4.1): un fapt este o intrare din
compartimentul
`registru_fapte`, iar fiecare schimbare este o versiune nouă.

Stările unui fapt, în cuvintele din plan: `propus` (versiune propusă), `aprobat`, `respins` (propunere
respinsă de un om),
`expirat` (a trecut „valabil până la”), plus `retras` (scos de un om după aprobare) și `inlocuit` (o versiune
mai nouă a fost
aprobată). Doar `aprobat` și valabil la data cerută intră în context, prin SINGURA funcție de citire pentru
context:
`pentru_context` (garda este în `tests/unit/test_creier_garda_context.py`).

Sursa obligatorie (constrângere în bază, F4.1): `pasaj` (id + citat exact, verificat literal), `document`,
`url` (citat
verificat în documentul cu acel URL) sau `declaratie_client` (citatul e opțional). Valorile numerice sunt
`Decimal`
(prețurile se compară exact, fără model).
"""

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.cercetare import Document
from app.creier import citat as verificator
from app.creier import pasaje as nucleu
from app.creier import versiuni as v
from app.creier.compartimente import CauzaRetragere, Compartiment, Stare, SursaTip, inregistreaza_schema
from app.creier.modele import IntrareCreier, Pasaj, VersiuneCreier
from app.creier.versiuni import RegulaCreier, Sursa

SURSE_PERMISE = frozenset({SursaTip.PASAJ, SursaTip.DOCUMENT, SursaTip.URL, SursaTip.DECLARATIE_CLIENT})
SURSE_CU_CITAT = frozenset({SursaTip.PASAJ, SursaTip.DOCUMENT, SursaTip.URL})


class TipFapt(StrEnum):
    PRET = "pret"
    CARACTERISTICA = "caracteristica"
    CIFRA = "cifra"
    GARANTIE = "garantie"
    TERMEN = "termen"
    PROGRAM = "program"
    DATE_CONTACT = "date_contact"
    ADRESA = "adresa"
    MENTIUNE_LEGALA = "mentiune_legala"
    AFIRMATIE_PERFORMANTA = "afirmatie_performanta"
    ALTUL = "altul"


ETICHETE_TIP = {
    TipFapt.PRET: "Preț",
    TipFapt.CARACTERISTICA: "Caracteristică",
    TipFapt.CIFRA: "Cifră",
    TipFapt.GARANTIE: "Garanție",
    TipFapt.TERMEN: "Termen",
    TipFapt.PROGRAM: "Program",
    TipFapt.DATE_CONTACT: "Date de contact",
    TipFapt.ADRESA: "Adresă",
    TipFapt.MENTIUNE_LEGALA: "Mențiune legală",
    TipFapt.AFIRMATIE_PERFORMANTA: "Afirmație de performanță",
    TipFapt.ALTUL: "Altul",
}


class Valoare(BaseModel):
    """Valoarea structurată a unui fapt, unde se poate: număr exact, monedă, unitate, text."""

    model_config = ConfigDict(extra="forbid")
    numar: Decimal | None = None
    moneda: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    unitate: str | None = Field(default=None, max_length=40)
    text: str | None = Field(default=None, max_length=200)

    @field_validator("numar")
    @classmethod
    def _canonic(cls, n: Decimal | None) -> Decimal | None:
        return None if n is None else n.normalize()


class ContinutFapt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tip: TipFapt
    subiect: str = Field(min_length=1, max_length=160)  # despre ce este: „Etiopia Guji 250 g”, „Livrare”
    afirmatie: str = Field(min_length=5, max_length=500)  # o propoziție, atomică
    valoare: Valoare | None = None


inregistreaza_schema(Compartiment.REGISTRU_FAPTE, ContinutFapt)


class StareFapt(StrEnum):
    PROPUS = "propus"
    APROBAT = "aprobat"
    RESPINS = "respins"
    EXPIRAT = "expirat"
    RETRAS = "retras"
    INLOCUIT = "inlocuit"
    CIORNA = "ciorna"


ETICHETE_STARE = {
    StareFapt.PROPUS: "propus",
    StareFapt.APROBAT: "aprobat",
    StareFapt.RESPINS: "respins",
    StareFapt.EXPIRAT: "expirat",
    StareFapt.RETRAS: "retras",
    StareFapt.INLOCUIT: "înlocuit",
    StareFapt.CIORNA: "ciornă",
}


class CitatNegasit(RegulaCreier):
    """Citatul nu se regăsește literal în sursa indicată."""

    def __init__(self, cod: str, detaliu: str = "") -> None:
        super().__init__(f"{cod}: {detaliu}" if detaliu else cod)
        self.cod = cod


def stare_fapt(ver: VersiuneCreier) -> StareFapt:
    if ver.stare == Stare.RETRAS.value:
        return {
            CauzaRetragere.RESPINS.value: StareFapt.RESPINS,
            CauzaRetragere.EXPIRAT.value: StareFapt.EXPIRAT,
            CauzaRetragere.INLOCUITA.value: StareFapt.INLOCUIT,
        }.get(ver.retras_cauza or "", StareFapt.RETRAS)
    return StareFapt(ver.stare)


def cheie_fapt(afirmatie: str) -> str:
    """Cheia intrării: aceeași afirmație (fără majuscule și diacritice) este același fapt."""
    return "f-" + hashlib.sha256(nucleu.normalizeaza(afirmatie).encode()).hexdigest()[:24]


def _text_sursa(db: Session, tenant_id: uuid.UUID, sursa: Sursa) -> str | None:
    """Textul în care trebuie să apară citatul, sau `None` dacă sursa nu are text de verificat."""
    if sursa.tip is SursaTip.PASAJ:
        try:
            pid = uuid.UUID(sursa.ref or "")
        except ValueError:
            raise CitatNegasit("sursa_invalida", "pasajul nu are un identificator valid") from None
        p = db.get(Pasaj, pid)
        if p is None or p.tenant_id != tenant_id:
            raise CitatNegasit("sursa_inexistenta", "pasajul nu există")
        return p.text
    if sursa.tip in (SursaTip.DOCUMENT, SursaTip.URL):
        q = select(Document).where(Document.tenant_id == tenant_id)
        if sursa.tip is SursaTip.DOCUMENT:
            try:
                q = q.where(Document.id == uuid.UUID(sursa.ref or ""))
            except ValueError:
                raise CitatNegasit("sursa_invalida", "documentul nu are un identificator valid") from None
        else:
            q = q.where(Document.url == sursa.ref)
        d = db.execute(q.limit(1)).scalar_one_or_none()
        if d is None:
            raise CitatNegasit("sursa_inexistenta", "documentul nu există")
        return d.text
    return None


def verifica_sursa(
    db: Session, tenant_id: uuid.UUID, sursa: Sursa, *, valoare_numar: str | None = None
) -> None:
    """Sursa unui fapt: tip permis, citat prezent și găsit LITERAL în textul sursei (pasaj, document, URL)."""
    if sursa.tip not in SURSE_PERMISE:
        raise RegulaCreier("un fapt are sursă: pasaj, document, URL sau declarația clientului")
    if sursa.tip in SURSE_CU_CITAT and not (sursa.citat or "").strip():
        raise CitatNegasit("citat_absent", "un fapt dintr-un material cere citatul exact")
    text = _text_sursa(db, tenant_id, sursa)
    if text is not None and sursa.citat:
        motiv = verificator.verifica_propunere(sursa.citat, text, valoare_numar=valoare_numar)
        if motiv is not None:
            raise CitatNegasit(motiv)


def propune_fapt(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    continut: ContinutFapt | dict[str, Any],
    sursa: Sursa,
    valabil_de_la: dt.datetime | None = None,
    valabil_pana_la: dt.datetime | None = None,
    utilizator_id: uuid.UUID | None = None,
    acum: dt.datetime | None = None,
) -> tuple[IntrareCreier, VersiuneCreier, bool]:
    """Un fapt nou, `propus`. Sursa se verifică (citatul trebuie să apară literal în pasaj / document).
    Aceeași afirmație
    nu se propune de două ori: dacă intrarea există, se întoarce ea (`creat=False`), oricare i-ar fi
    starea."""
    c = continut if isinstance(continut, ContinutFapt) else ContinutFapt.model_validate(continut)
    numar = None if c.valoare is None or c.valoare.numar is None else format(c.valoare.numar, "f")
    verifica_sursa(db, tenant_id, sursa, valoare_numar=numar)
    cheie = cheie_fapt(c.afirmatie)
    existenta = v.gaseste_intrare(
        db, tenant_id=tenant_id, compartiment=Compartiment.REGISTRU_FAPTE, cheie=cheie
    )
    if existenta is not None:
        return existenta, v.istoric(db, existenta.id)[-1], False
    intrare, ver = v.creeaza_intrare(
        db,
        tenant_id=tenant_id,
        compartiment=Compartiment.REGISTRU_FAPTE,
        cheie=cheie,
        continut=c.model_dump(mode="json"),
        sursa=sursa,
        valabil_de_la=valabil_de_la,
        valabil_pana_la=valabil_pana_la,
        utilizator_id=utilizator_id,
        acum=acum,
    )
    return intrare, ver, True


def modifica_fapt(
    db: Session,
    intrare_id: uuid.UUID,
    *,
    continut: ContinutFapt | dict[str, Any],
    sursa: Sursa,
    valabil_de_la: dt.datetime | None = None,
    valabil_pana_la: dt.datetime | None = None,
    motiv: str = "",
    utilizator_id: uuid.UUID | None = None,
    acum: dt.datetime | None = None,
) -> VersiuneCreier:
    """O schimbare a unui fapt (de ex. prețul nou) = o versiune nouă `propusă`, cu sursa ei verificată."""
    i = v.intrare(db, intrare_id)
    if i.compartiment != Compartiment.REGISTRU_FAPTE.value or i.tenant_id is None:
        raise RegulaCreier("intrarea nu este un fapt")
    c = continut if isinstance(continut, ContinutFapt) else ContinutFapt.model_validate(continut)
    numar = None if c.valoare is None or c.valoare.numar is None else format(c.valoare.numar, "f")
    verifica_sursa(db, i.tenant_id, sursa, valoare_numar=numar)
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


def aproba_fapt(
    db: Session,
    intrare_id: uuid.UUID,
    versiune: int,
    *,
    utilizator_id: uuid.UUID,
    acum: dt.datetime | None = None,
) -> VersiuneCreier:
    """Aprobarea unui om. Doar de aici un fapt devine utilizabil în context."""
    return v.aproba(db, intrare_id, versiune, utilizator_id=utilizator_id, acum=acum)


def respinge_fapt(
    db: Session,
    intrare_id: uuid.UUID,
    versiune: int,
    *,
    utilizator_id: uuid.UUID,
    motiv: str,
    acum: dt.datetime | None = None,
) -> VersiuneCreier:
    if not motiv.strip():
        raise RegulaCreier("respingerea cere un motiv")
    if v.citeste(db, intrare_id, versiune).stare not in (Stare.PROPUS.value, Stare.CIORNA.value):
        raise v.TranzitieNepermisa("doar o versiune propusă se respinge; un fapt aprobat se retrage")
    return v.retrage(
        db,
        intrare_id,
        versiune,
        utilizator_id=utilizator_id,
        motiv=motiv,
        cauza=CauzaRetragere.RESPINS,
        acum=acum,
    )


def retrage_fapt(
    db: Session,
    intrare_id: uuid.UUID,
    versiune: int,
    *,
    utilizator_id: uuid.UUID,
    motiv: str,
    acum: dt.datetime | None = None,
) -> VersiuneCreier:
    return v.retrage(db, intrare_id, versiune, utilizator_id=utilizator_id, motiv=motiv, acum=acum)


@dataclass(frozen=True)
class FaptPropus:
    """Un fapt cu versiunea lui, pentru lista de aprobare."""

    intrare_id: uuid.UUID
    tenant_id: uuid.UUID
    versiune: int
    stare: StareFapt
    tip: str
    subiect: str
    afirmatie: str
    valoare: dict[str, Any] | None
    sursa_tip: str
    sursa_ref: str | None
    sursa_citat: str | None
    sursa_detalii: dict[str, Any]
    valabil_de_la: dt.datetime | None
    valabil_pana_la: dt.datetime | None
    creat_la: dt.datetime
    aprobat_la: dt.datetime | None
    motiv: str


def _fapt(i: IntrareCreier, ver: VersiuneCreier) -> FaptPropus:
    c = ver.continut
    return FaptPropus(
        intrare_id=i.id,
        tenant_id=ver.tenant_id or uuid.UUID(int=0),
        versiune=ver.nr,
        stare=stare_fapt(ver),
        tip=str(c.get("tip", "")),
        subiect=str(c.get("subiect", "")),
        afirmatie=str(c.get("afirmatie", "")),
        valoare=c.get("valoare"),
        sursa_tip=ver.sursa_tip,
        sursa_ref=ver.sursa_ref,
        sursa_citat=ver.sursa_citat,
        sursa_detalii=ver.sursa_detalii,
        valabil_de_la=ver.valabil_de_la,
        valabil_pana_la=ver.valabil_pana_la,
        creat_la=ver.creat_la,
        aprobat_la=ver.aprobat_la,
        motiv=ver.retras_motiv or ver.motiv,
    )


def propuneri(db: Session, *, tenant_id: uuid.UUID | None = None, limita: int = 200) -> list[FaptPropus]:
    """Faptele cu o versiune `propusă`, cele mai vechi întâi (pentru lista de aprobare). Fără `tenant_id`:
    toți clienții
    pe care sesiunea îi vede (RLS)."""
    q = (
        select(IntrareCreier, VersiuneCreier)
        .join(VersiuneCreier, VersiuneCreier.intrare_id == IntrareCreier.id)
        .where(
            IntrareCreier.compartiment == Compartiment.REGISTRU_FAPTE.value, VersiuneCreier.stare == "propus"
        )
        .order_by(VersiuneCreier.creat_la, VersiuneCreier.id)
        .limit(limita)
    )
    if tenant_id is not None:
        q = q.where(IntrareCreier.tenant_id == tenant_id)
    return [_fapt(i, ver) for i, ver in db.execute(q).all()]


def fapt(db: Session, intrare_id: uuid.UUID) -> FaptPropus:
    """Cea mai recentă versiune a unui fapt, în orice stare (istoricul complet: `versiuni.istoric`)."""
    i = v.intrare(db, intrare_id)
    return _fapt(i, v.istoric(db, intrare_id)[-1])


def pentru_context(
    db: Session, tenant_id: uuid.UUID, la: dt.datetime, *, tipuri: frozenset[TipFapt] | None = None
) -> list[FaptPropus]:
    """SINGURA citire a faptelor pentru context (F4.7): doar versiunile APROBATE de un om și valabile la `la`
    (aprobate până atunci, neretrase încă, cu `la` în intervalul de valabilitate). Ordine stabilă."""
    if la.tzinfo is None:
        raise RegulaCreier("data cerută trebuie să aibă fus orar (UTC)")
    q = (
        select(IntrareCreier, VersiuneCreier)
        .join(VersiuneCreier, VersiuneCreier.intrare_id == IntrareCreier.id)
        .where(
            IntrareCreier.tenant_id == tenant_id,
            IntrareCreier.compartiment == Compartiment.REGISTRU_FAPTE.value,
            VersiuneCreier.aprobat_la.is_not(None),
            VersiuneCreier.aprobat_la <= la,
            VersiuneCreier.retras_la.is_(None) | (VersiuneCreier.retras_la > la),
            VersiuneCreier.valabil_de_la.is_(None) | (VersiuneCreier.valabil_de_la <= la),
            VersiuneCreier.valabil_pana_la.is_(None) | (VersiuneCreier.valabil_pana_la > la),
        )
        .order_by(IntrareCreier.cheie, VersiuneCreier.nr)
    )
    iesire = [_fapt(i, ver) for i, ver in db.execute(q).all()]
    if tipuri is not None:
        iesire = [f for f in iesire if f.tip in {t.value for t in tipuri}]
    return iesire


@dataclass(frozen=True)
class Expirat:
    tenant_id: uuid.UUID
    intrare_id: uuid.UUID
    compartiment: str
    eticheta: str  # subiectul faptului / numele ofertei
    valabil_pana_la: dt.datetime


def expirate_de_clarificat(db: Session, tenant_id: uuid.UUID) -> list[FaptPropus]:
    """Faptele a căror ultimă versiune a expirat, fără versiune mai nouă: întrebările rămase către client."""
    noua = aliased(VersiuneCreier)
    q = (
        select(IntrareCreier, VersiuneCreier)
        .join(VersiuneCreier, VersiuneCreier.intrare_id == IntrareCreier.id)
        .where(
            IntrareCreier.tenant_id == tenant_id,
            IntrareCreier.compartiment == Compartiment.REGISTRU_FAPTE.value,
            VersiuneCreier.retras_cauza == CauzaRetragere.EXPIRAT.value,
            ~select(noua.id)
            .where(noua.intrare_id == VersiuneCreier.intrare_id, noua.nr > VersiuneCreier.nr)
            .exists(),
        )
        .order_by(VersiuneCreier.retras_la, IntrareCreier.id)
    )
    return [_fapt(i, ver) for i, ver in db.execute(q).all()]


def expira(db: Session, la: dt.datetime) -> list[Expirat]:
    """Retrage (cauza `expirat`) versiunile aprobate ale faptelor și ofertelor al căror „valabil până la” a
    trecut. Se
    cheamă dintr-o sesiune de agenție (vede toți clienții). Idempotentă: o versiune retrasă nu mai apare."""
    iesire: list[Expirat] = []
    for ver in v.versiuni_de_expirat(db, la):
        i = v.intrare(db, ver.intrare_id)
        if i.compartiment not in (Compartiment.REGISTRU_FAPTE.value, Compartiment.CATALOG_OFERTE.value):
            continue
        if i.tenant_id is None or ver.valabil_pana_la is None:
            continue
        v.retrage(
            db,
            i.id,
            ver.nr,
            utilizator_id=None,
            motiv="a trecut „valabil până la”",
            cauza=CauzaRetragere.EXPIRAT,
            acum=la,
        )
        iesire.append(
            Expirat(
                i.tenant_id,
                i.id,
                i.compartiment,
                str(ver.continut.get("subiect") or ver.continut.get("nume") or ""),
                ver.valabil_pana_la,
            )
        )
    return iesire


__all__ = [
    "ETICHETE_STARE",
    "ETICHETE_TIP",
    "CitatNegasit",
    "ContinutFapt",
    "Decimal",
    "Expirat",
    "FaptPropus",
    "StareFapt",
    "TipFapt",
    "Valoare",
    "aproba_fapt",
    "cheie_fapt",
    "expira",
    "expirate_de_clarificat",
    "fapt",
    "modifica_fapt",
    "pentru_context",
    "propune_fapt",
    "propuneri",
    "respinge_fapt",
    "retrage_fapt",
    "stare_fapt",
    "verifica_sursa",
]
