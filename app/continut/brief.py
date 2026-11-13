"""Autorul de brief (F6.2, D5, docs/13 §13.2 pasul 1: „scop, public, mesaj unic, fapte permise, format, canal,
termen”).

Pentru fiecare slot de calendar (livrabil `planificat`) se construiește pachetul de context (F4.7) cu
secțiunile `strategie`
și `public`, citit la data publicării (faptele valabile atunci). Modelul (profilul `clasificare`) primește
faptele și ofertele
din pachet sub aliasuri scurte (F1, F2, …) și alege pe cele permise; sistemul le rezolvă înapoi la intrarea și
versiunea
lor din Creier. Lume închisă: un alias care nu e în pachet respinge brieful; dacă pachetul are fapte, brieful
trebuie să
permită cel puțin unul; dacă nu are, brieful spune explicit lipsa (`lipsuri`). Canalul, tipul, termenul,
pilonul și
subiectul le pune sistemul, din slot, nu modelul. Livrabilul trece `planificat → briefat` (componenta D5).
"""

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import creier, gateway, onboarding, productie
from app.continut import calendar, prompturi
from app.continut.modele import Brief
from app.creier import context
from app.ids import new_id
from app.operare.motor import Prioritate
from app.productie import Stare

REFERINTA_PROMPT = "continut.brief@1"
COMPONENTA = "D5"
BUGET_TOKENI = 3000
SECTIUNI = ("strategie", "public")


class ContinutBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scop: str = Field(min_length=10, max_length=300)
    public: str = Field(min_length=5, max_length=300)
    mesaj_unic: str = Field(min_length=10, max_length=300)
    fapte_permise: list[str] = Field(max_length=12)
    format: str = Field(min_length=5, max_length=300)
    apel_la_actiune: str = Field(min_length=3, max_length=150)
    interdictii: list[str] = Field(default_factory=list, max_length=10)


class PropunereBrief(gateway.Iesire):
    brief: ContinutBrief


class BriefInvalid(creier.RegulaCreier):
    def __init__(self, probleme: list[str]) -> None:
        super().__init__("; ".join(probleme))
        self.probleme = probleme


def fapte_disponibile(pachet: creier.PachetContext) -> dict[str, dict[str, Any]]:
    """Aliasurile (F1, F2, …) ale faptelor și ofertelor din pachet, în ordinea lui (deterministă)."""
    elemente = [*pachet.sectiune("fapte"), *pachet.sectiune("oferte")]
    return {
        f"F{i}": {"id": e.id, "versiune": e.versiune, "tip": e.tip, "text": e.text}
        for i, e in enumerate(elemente, start=1)
    }


def probleme_brief(b: ContinutBrief, disponibile: dict[str, dict[str, Any]]) -> list[str]:
    """Nucleu pur: lumea închisă a faptelor permise."""
    probleme = [f"faptul {a} nu este în pachetul de context" for a in b.fapte_permise if a not in disponibile]
    if disponibile and not b.fapte_permise:
        probleme.append("brieful trebuie să permită cel puțin un fapt din pachet")
    if len(set(b.fapte_permise)) != len(b.fapte_permise):
        probleme.append("un fapt apare de două ori")
    return probleme


def _produse(db: Session, tenant_id: uuid.UUID) -> str:
    """Ce vinde clientul (din brieful de onboarding aprobat): relevanța faptelor e lexicală, iar
    produsele țin de orice material al brandului, oricare ar fi subiectul slotului."""
    try:
        continut, _ = onboarding.completare.brief_aprobat(db, tenant_id)
    except creier.RegulaCreier:
        return ""
    return str((continut.get("ce_vinde") or {}).get("valoare", ""))[:600]


def al_livrabilului(db: Session, livrabil_id: uuid.UUID) -> Brief | None:
    return db.execute(select(Brief).where(Brief.livrabil_id == livrabil_id)).scalar_one_or_none()


def scrie(db: Session, livrabil_id: uuid.UUID, *, utilizator_id: uuid.UUID | None = None) -> Brief:
    """Brieful unui livrabil `planificat` dintr-un calendar; îl mută în `briefat`. Idempotent: un brief
    existent se
    întoarce neschimbat. Ridică `gateway.Amanat`, `BriefInvalid` sau `RegulaCreier` (ghid de brand lipsă)."""
    existent = al_livrabilului(db, livrabil_id)
    if existent is not None:
        return existent
    lv = productie.blocheaza(db, livrabil_id)
    if Stare(lv.stare) is not Stare.PLANIFICAT:
        raise creier.RegulaCreier(f"brieful se scrie pentru un livrabil planificat, nu „{lv.stare}”")
    slot = calendar.intrarea_livrabilului(db, lv.id)
    if slot is None:
        raise creier.RegulaCreier("livrabilul nu vine dintr-un calendar")
    la = max(lv.termen_la or dt.datetime.now(dt.UTC), dt.datetime.now(dt.UTC))
    pachet = context.construieste(
        db,
        tenant_id=lv.tenant_id,
        tip_sarcina=f"{lv.tip}_{lv.canal}",
        intrebare=f"{slot.subiect}. {slot.unghi}. {slot.pilon}. {_produse(db, lv.tenant_id)}"[:1900],
        canal=lv.canal,
        livrabil_id=lv.id,
        la=la,
        buget_tokeni=BUGET_TOKENI,
        utilizator_id=utilizator_id,
        sectiuni_extra=SECTIUNI,
    )
    if "ghid_brand" in pachet.lipsuri:
        raise creier.RegulaCreier("brieful cere ghidul de brand aprobat")
    disponibile = fapte_disponibile(pachet)
    prompturi.asigura()
    r = gateway.apeleaza(
        db,
        prompt=REFERINTA_PROMPT,
        schema=PropunereBrief,
        tenant_id=lv.tenant_id,
        componenta="continut.brief",
        livrabil_id=lv.id,
        prioritate=Prioritate.P2,
        max_tokeni=1500,
        variabile={
            "tip": lv.tip,
            "canal": lv.canal,
            "termen": slot.slot_la.astimezone(calendar.FUS).strftime("%d.%m.%Y %H:%M"),
            "pilon": slot.pilon,
            "subiect": slot.subiect,
            "unghi": slot.unghi or "-",
            "fapte": "\n".join(f"[{a}] {f['text']}" for a, f in disponibile.items())
            or "(niciun fapt relevant)",
            "context": context.ca_text(pachet),
        },
    )
    if not isinstance(r.iesire, PropunereBrief):
        raise TypeError("ieșirea nu respectă schema promptului")
    b = r.iesire.brief
    probleme = probleme_brief(b, disponibile)
    if probleme:
        raise BriefInvalid(probleme)
    continut = {
        **b.model_dump(mode="json"),
        "fapte_permise": [{"alias": a, **disponibile[a]} for a in b.fapte_permise],
        "tip": lv.tip,
        "canal": lv.canal,
        "termen": slot.slot_la.isoformat(),
        "pilon": slot.pilon,
        "subiect": slot.subiect,
        "unghi": slot.unghi,
        "lipsuri": [x for x in pachet.lipsuri if x == "fapte_relevante"],
    }
    rand = Brief(
        id=new_id(),
        tenant_id=lv.tenant_id,
        livrabil_id=lv.id,
        pachet_id=pachet.id,
        continut=continut,
        model=r.model,
    )
    db.add(rand)
    db.flush()
    productie.muta(
        db,
        lv.id,
        Stare.PLANIFICAT,
        Stare.BRIEFAT,
        componenta=COMPONENTA,
        motiv="brief scris",
        utilizator_id=utilizator_id,
        detalii={"brief": str(rand.id), "fapte_permise": len(b.fapte_permise)},
    )
    return rand


def text_pentru_autor(continut: dict[str, Any]) -> str:
    """Brieful, gata de pus în promptul autorului (faptele permise cu textul lor)."""
    permise = continut.get("fapte_permise", [])
    fapte = "\n".join(f"- {f['text']}" for f in permise) or "- (niciun fapt permis)"
    interdictii = "; ".join(continut.get("interdictii", [])) or "-"
    return (
        f"Scop: {continut['scop']}\nPublic: {continut['public']}\nMesaj unic: {continut['mesaj_unic']}\n"
        f"Format: {continut['format']}\nApel la acțiune (unul singur): {continut['apel_la_actiune']}\n"
        f"Interdicții: {interdictii}\n"
        f"Fapte permise (singurele cifre, prețuri și promisiuni permise):\n{fapte}"
    )
