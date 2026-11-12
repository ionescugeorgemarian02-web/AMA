"""Strategia pe 90 de zile, prima formă (F4.11, A2, docs/07 §7.7).

„Totul pornește cu criterii.” Fiecare strategie are din start: ipoteza, planul pe 30 și pe 90 de zile,
indicatorul principal,
pragul minim, fereastra de măsurare și criteriul de oprire. TOATE sunt obligatorii (schemă strictă,
`extra="forbid"`, fără
valori implicite) și se verifică încă o dată la poarta compartimentului (`strategie`): o strategie cu
un element lipsă,
cu pragul peste țintă sau cu un plan fără pași nu poate fi trimisă spre aprobare și nici aprobată.

Strategia se propune prin gateway pe profilul `strategie`, care se AMÂNĂ, nu se degradează (docs/08
§8.2, ADR-06): la `Amanat`
fluxul durabil își reprogramează munca. Intrarea pentru model este pachetul de context (F4.7) cerut cu
secțiunile
`brief`, `public` și `insight`: brieful, ghidul de brand, faptele și ofertele, profilul de public și
brieful de insight,
toate APROBATE de un om. Strategia se salvează ca versiune `propus` (cu amprenta pachetului în sursă)
și o aprobă un om;
cea veche rămâne citibilă. Revizuirile și pivotul sunt F13.6 (nu se construiesc aici).
"""

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app import creier, gateway
from app.creier import context
from app.creier.compartimente import Compartiment, SursaTip
from app.onboarding import completare, prompturi
from app.operare import audit
from app.operare.motor import Prioritate

REFERINTA_PROMPT = "onboarding.strategie@1"
CHEIE_STRATEGIE = "strategie-90"
BUGET_TOKENI = 6000
CANALE = (
    "facebook",
    "instagram",
    "tiktok",
    "linkedin",
    "email",
    "site",
    "whatsapp",
    "reclama",
    "cafenea",
    "alt_canal",
)


class Pas(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actiune: str = Field(min_length=10, max_length=300)
    canal: Literal[
        "facebook",
        "instagram",
        "tiktok",
        "linkedin",
        "email",
        "site",
        "whatsapp",
        "reclama",
        "cafenea",
        "alt_canal",
    ]
    rezultat_asteptat: str = Field(min_length=5, max_length=200)


class Indicator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nume: str = Field(min_length=3, max_length=100)
    unitate: str = Field(min_length=1, max_length=30)
    tinta: float = Field(gt=0)
    mod_masurare: str = Field(min_length=10, max_length=300)


class Prag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valoare: float = Field(gt=0)
    unitate: str = Field(min_length=1, max_length=30)
    motiv: str = Field(min_length=10, max_length=300)


class Strategie(BaseModel):
    """Strategia pe 90 de zile. Nimic nu are valoare implicită: ce lipsește nu trece."""

    model_config = ConfigDict(extra="forbid")
    ipoteza: str = Field(min_length=30, max_length=800)
    plan_30_zile: list[Pas] = Field(min_length=3, max_length=10)
    plan_90_zile: list[Pas] = Field(min_length=3, max_length=15)
    indicator_principal: Indicator
    prag_minim: Prag
    fereastra_masurare_zile: int = Field(ge=7, le=90)
    criteriu_oprire: str = Field(min_length=30, max_length=500)


class PropunereStrategie(gateway.Iesire):
    strategie: Strategie


def probleme_strategie(c: dict[str, Any]) -> list[str]:
    """Nucleu pur: problemele unei strategii (schema, ca poartă pe orice cale, și regulile dincolo de ea)."""
    try:
        s = Strategie.model_validate(c)
    except ValidationError as exc:
        return [f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()[:8]]
    probleme: list[str] = []
    if s.prag_minim.unitate.strip().lower() != s.indicator_principal.unitate.strip().lower():
        probleme.append("pragul minim și indicatorul principal trebuie să aibă aceeași unitate")
    if s.prag_minim.valoare >= s.indicator_principal.tinta:
        probleme.append("pragul minim trebuie să fie sub ținta indicatorului principal")
    if s.fereastra_masurare_zile > 90:
        probleme.append("fereastra de măsurare nu poate depăși cele 90 de zile")
    return probleme


def _poarta(_db: Any, _tenant: uuid.UUID | None, c: dict[str, Any]) -> list[str]:
    return probleme_strategie(c)


def randeaza(c: dict[str, Any]) -> str | None:
    try:
        s = Strategie.model_validate(c)
    except ValidationError:
        return None
    ind, prag = s.indicator_principal, s.prag_minim
    plan30 = "; ".join(f"{p.actiune} ({p.canal})" for p in s.plan_30_zile)
    plan90 = "; ".join(f"{p.actiune} ({p.canal})" for p in s.plan_90_zile)
    return (
        f"Ipoteză: {s.ipoteza}\nIndicator principal: {ind.nume}, țintă {ind.tinta} {ind.unitate}; "
        f"prag minim {prag.valoare} {prag.unitate}; "
        f"fereastră de măsurare {s.fereastra_masurare_zile} de zile\n"
        f"Plan 30 de zile: {plan30}\nPlan 90 de zile: {plan90}\nCriteriu de oprire: {s.criteriu_oprire}"
    )


creier.inregistreaza_schema(Compartiment.STRATEGIE, Strategie)
creier.inregistreaza_randare(Compartiment.STRATEGIE, randeaza)
creier.inregistreaza_poarta(Compartiment.STRATEGIE, _poarta)


class StrategieInvalida(creier.RegulaCreier):
    def __init__(self, probleme: list[str]) -> None:
        super().__init__("; ".join(probleme))
        self.probleme = probleme


def propune(db: Session, *, tenant_id: uuid.UUID, utilizator_id: uuid.UUID | None) -> tuple[uuid.UUID, int]:
    """Strategia propusă (versiune `propus`) din pachetul de context al clientului. Cere brief, ghid de brand,
    profil de public și brief de insight APROBATE. Ridică `gateway.Amanat` (nu degradează)."""
    continut_brief, _ = completare.brief_aprobat(db, tenant_id)

    def camp(nume: str) -> str:
        return str((continut_brief.get(nume) or {}).get("valoare", ""))

    # Relevanța faptelor este lexicală: întrebarea poartă obiectivul, produsele și prețurile din brief,
    # ca faptele și
    # ofertele despre ele să intre în pachet.
    intrebare = (
        f"Strategie de marketing pe 90 de zile. {camp('obiectiv_90_zile')} "
        f"Produse: {camp('ce_vinde')} Prețuri: {camp('preturi')}"
    )[:1900]
    pachet = context.construieste(
        db, tenant_id=tenant_id, tip_sarcina="strategie_90_zile", intrebare=intrebare,
        buget_tokeni=BUGET_TOKENI, utilizator_id=utilizator_id, la=dt.datetime.now(dt.UTC),
        sectiuni_extra=("brief", "public", "insight"),
    )  # fmt: skip
    lipsa = [x for x in pachet.lipsuri if x in ("ghid_brand", "brief", "public", "insight")]
    if lipsa:
        raise creier.RegulaCreier("strategia cere, aprobate: " + ", ".join(lipsa))
    prompturi.asigura()
    r = gateway.apeleaza(
        db,
        prompt=REFERINTA_PROMPT,
        variabile={"context": context.ca_text(pachet)},
        schema=PropunereStrategie,
        tenant_id=tenant_id,
        componenta="onboarding.strategie",
        prioritate=Prioritate.P1,
        max_tokeni=4000,
    )
    iesire = r.iesire
    if not isinstance(iesire, PropunereStrategie):
        raise TypeError("ieșirea nu respectă schema promptului")
    continut = iesire.strategie.model_dump(mode="json")
    probleme = probleme_strategie(continut)
    if probleme:
        raise StrategieInvalida(probleme)
    sursa = creier.Sursa(
        SursaTip.SISTEM,
        detalii={
            "pachet_amprenta": pachet.amprenta,
            "pachet_id": str(pachet.id) if pachet.id else None,
            "model": r.model,
        },
    )
    existenta = creier.gaseste_intrare(
        db, tenant_id=tenant_id, compartiment=Compartiment.STRATEGIE, cheie=CHEIE_STRATEGIE
    )
    if existenta is None:
        i, v = creier.creeaza_intrare(
            db,
            tenant_id=tenant_id,
            compartiment=Compartiment.STRATEGIE,
            cheie=CHEIE_STRATEGIE,
            continut=continut,
            sursa=sursa,
        )
        iid, nr = i.id, v.nr
    else:
        v = creier.propune_schimbare(db, existenta.id, continut=continut, sursa=sursa)
        iid, nr = existenta.id, v.nr
    audit.record(
        db, "onboarding.strategie_propusa", obiect_tip="creier_intrare", obiect_id=iid,
        utilizator_id=utilizator_id, tenant_id=tenant_id, detalii={"versiune": nr},
    )  # fmt: skip
    return iid, nr


def strategii(db: Session, tenant_id: uuid.UUID) -> list[tuple[Any, Any | None]]:
    """Intrările `strategie` ale clientului, fiecare cu versiunea aprobată acum (sau `None`)."""
    return creier.lista(db, tenant_id=tenant_id, compartiment=Compartiment.STRATEGIE)
