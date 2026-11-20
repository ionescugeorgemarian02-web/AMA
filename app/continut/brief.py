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
import re
import unicodedata
import uuid
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import creier, gateway, onboarding, productie
from app.continut import calendar, prompturi
from app.continut.modele import Brief, IdeeConcept
from app.creier import context
from app.ids import new_id
from app.operare.motor import Prioritate
from app.productie import Stare

REFERINTA_PROMPT = "continut.brief@4"
COMPONENTA = "D5"
BUGET_TOKENI = 3000
SECTIUNI = ("strategie", "public")


# --- brieful vizual (F-editorial, decizia 4): indicațiile trebuie să fie observabile ---

# [I] cuvinte care nu spun CE se vede: adjective de efect, termeni de cadru și de montaj, umplutură
_VAGI = """
dinamic dinamica dinamice premium modern moderna moderne elegant eleganta elegante atractiv
atractiva captivant captivanta profesional profesionala frumos frumoasa frumoase spectaculos
spectaculoasa cinematic cinematografic energic energica vibrant vibranta inspirational
inspirationala minimalist minimalista luminos luminoasa calduros calduroasa autentic autentica
emotionant impresionant creativ creativa stilat stilata curat curata simplu simpla rapid rapida lent
lenta wow epic fresh cool trendy viral cadru cadrul cadre plan planul prim apropiat apropiata larg
larga imagine imaginea imagini scena scene vizual vizuala vizuale broll roll montaj tranzitie
tranzitii zoom efect efecte atmosfera ambianta vibe stil energie emotie emotii poveste mesaj concept
abstract abstracta generic generica grafica grafice animatie animatii text fundal culori culoare
lumina miscare video clip ceva cald calda calde rece reci
"""
VAGI = frozenset(_VAGI.split())
_UMPLUTURA = """
care sunt este fost pentru prin dintre catre langa peste spre dupa foarte mult multa toate fiecare
noastre nostru noastra niste doar chiar apoi cele cela cea cel una unul unei unui ale lui lor
"""
UMPLUTURA = frozenset(_UMPLUTURA.split())


def _cuvinte(text: str) -> list[str]:
    fara = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    return [w for w in re.split(r"[^a-z0-9]+", fara) if len(w) >= 3 and w not in UMPLUTURA]


def problema_indicatie(text: str) -> str | None:
    """Nucleu pur: `None` dacă indicația numește ceva concret ce se vede; altfel motivul respingerii.
    Fără analiză gramaticală: concret = cel puțin un cuvânt de conținut care nu e adjectiv de efect sau
    termen de cadru (aproximare [I] a „substantivului concret”)."""
    cuvinte = _cuvinte(text)
    if not cuvinte:
        return "indicația vizuală e goală"
    if all(c in VAGI for c in cuvinte):
        return (
            f"indicația vizuală „{text.strip()[:80]}” e vagă: numește ce se vede (un obiect, o persoană, "
            "un loc sau o acțiune), nu doar cum arată"
        )
    return None


def _observabila(text: str) -> str:
    problema = problema_indicatie(text)
    if problema:
        raise ValueError(problema)
    return text


Observabila = Annotated[str, AfterValidator(_observabila)]


class ContinutBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")
    obiectiv: Literal["vanzare", "editorial"]
    oferta: str | None = None
    scop: str = Field(min_length=10, max_length=300)
    public: str = Field(min_length=5, max_length=300)
    mesaj_unic: str = Field(min_length=10, max_length=300)
    fapte_permise: list[str] = Field(max_length=12)
    format: str = Field(min_length=5, max_length=300)
    apel_la_actiune: str = Field(min_length=3, max_length=150)
    interdictii: list[str] = Field(default_factory=list, max_length=10)
    # brieful vizual (F-editorial)
    idee_editoriala: str = Field(min_length=10, max_length=300)
    ce_vede_publicul: Annotated[Observabila, Field(min_length=10, max_length=300)]
    informatie_in_plus: str = Field(min_length=5, max_length=300)
    natura: Literal["educativ", "prezentare"]


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
        f"F{i}": {
            "id": e.id,
            "versiune": e.versiune,
            "tip": e.tip,
            "text": e.text,
            "destinatie": e.detalii.get("destinatie"),
        }
        for i, e in enumerate(elemente, start=1)
    }


def probleme_brief(b: ContinutBrief, disponibile: dict[str, dict[str, Any]]) -> list[str]:
    """Nucleu pur: lumea închisă a faptelor permise."""
    probleme = [f"faptul {a} nu este în pachetul de context" for a in b.fapte_permise if a not in disponibile]
    if disponibile and not b.fapte_permise:
        probleme.append("brieful trebuie să permită cel puțin un fapt din pachet")
    if len(set(b.fapte_permise)) != len(b.fapte_permise):
        probleme.append("un fapt apare de două ori")
    comercial = b.obiectiv == "vanzare" or re.search(
        r"\b(comandă|cumpără|rezervă|programează-te)\b", b.apel_la_actiune, re.IGNORECASE
    )
    if comercial or b.oferta:
        of = disponibile.get(b.oferta or "", {})
        if of.get("tip") != "oferta" or b.oferta not in b.fapte_permise:
            probleme.append("materialul comercial cere o ofertă aprobată în faptele permise")
        elif not of.get("destinatie"):
            probleme.append("oferta aprobată nu are destinație pentru apelul la acțiune")
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


def pachet_livrabil(
    db: Session, lv: productie.Livrabil, slot: Any, *, utilizator_id: uuid.UUID | None = None
) -> creier.PachetContext:
    """Pachetul de context al livrabilului (F4.7), citit la data publicării; comun briefului și ideii."""
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
        exemple=(lv.tip, lv.canal),
    )
    return pachet


def idee_aleasa(db: Session, livrabil_id: uuid.UUID) -> dict[str, Any] | None:
    """Conceptul ales în etapa de idee (F-idee), dacă există."""
    r = db.execute(
        select(IdeeConcept).where(IdeeConcept.livrabil_id == livrabil_id, IdeeConcept.ales.is_(True))
    ).scalar_one_or_none()
    return None if r is None else {**r.concept, "id": str(r.id)}


TITLU_IMAGINE_CUVINTE = 7  # [I] titlul imaginii de feed: scurt, nu hook-ul postării


def titlu_imagine(idee: dict[str, Any] | None, rezerva: str = "") -> str:
    """Titlul imaginii de feed: titlul conceptului ales (scurt, scris pentru o privire), nu hook-ul postării;
    fără concept, `rezerva` (de pildă produsul). Cel mult `TITLU_IMAGINE_CUVINTE` cuvinte întregi."""
    titlu = str((idee or {}).get("titlu") or rezerva).strip()
    return " ".join(titlu.split()[:TITLU_IMAGINE_CUVINTE]).rstrip(" ,;:–—-")


def text_idee(idee: dict[str, Any] | None, disponibile: dict[str, dict[str, Any]] | None = None) -> str:
    """Conceptul ales, ca text pentru autorii de brief, postare și script (gol fără concept)."""
    if not idee:
        return ""
    dovada = idee.get("dovada_text") or (disponibile or {}).get(idee.get("dovada", ""), {}).get("text", "")
    cadre = "\n".join(
        f"{i}. {c['subiect']}: {c['actiune']} ({c.get('context') or '-'}) "
        f"[{c.get('tip')}, {c.get('incadrare')}]"
        for i, c in enumerate(idee.get("cadre", []), start=1)
    )
    return (
        "Conceptul ales (scrie din el, nu din subiectul calendarului):\n"
        f"Momentul real: {idee.get('moment_real', '')}\nTensiunea: {idee.get('tensiune', '')}\n"
        f"Mesajul conceptului: {idee.get('mesaj_unic', '')}\nDovada: {dovada or '-'}\n"
        f"De ce acum: {idee.get('de_ce_acum', '')}\n"
        f"Cadrele, în ordine (o bătaie pe cadru):\n{cadre}\n"
    )


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
    pachet = pachet_livrabil(db, lv, slot, utilizator_id=utilizator_id)
    if "ghid_brand" in pachet.lipsuri:
        raise creier.RegulaCreier("brieful cere ghidul de brand aprobat")
    disponibile = fapte_disponibile(pachet)
    idee = idee_aleasa(db, lv.id)
    if idee is not None and not idee.get("dovada_text"):
        idee["dovada_text"] = disponibile.get(idee.get("dovada", ""), {}).get("text", "")
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
            "fapte": "\n".join(f"[{a}] {f['tip']}: {f['text']}" for a, f in disponibile.items())
            or "(niciun fapt relevant)",
            "context": context.ca_text(pachet),
            "idee": text_idee(idee) or "(niciun concept ales: scrie din subiect)",
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
        "oferta": disponibile[b.oferta] if b.oferta else None,
        "tip": lv.tip,
        "canal": lv.canal,
        "termen": slot.slot_la.isoformat(),
        "pilon": slot.pilon,
        "subiect": slot.subiect,
        "unghi": slot.unghi,
        "lipsuri": [x for x in pachet.lipsuri if x == "fapte_relevante"],
        **({"idee": idee} if idee is not None else {}),
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
    oferta = continut.get("oferta")
    comercial = f"Oferta aprobată: {oferta['text']}\nDestinație: {oferta['destinatie']}\n" if oferta else ""
    interdictii = "; ".join(continut.get("interdictii", [])) or "-"
    vizual = "".join(
        f"{eticheta}: {continut[cheie]}\n"
        for cheie, eticheta in (
            ("idee_editoriala", "Ideea editorială"),
            ("ce_vede_publicul", "Ce vede publicul"),
            ("informatie_in_plus", "Informația în plus"),
            ("natura", "Natura materialului"),
        )
        if continut.get(cheie)
    )
    return (
        f"Scop: {continut['scop']}\nPublic: {continut['public']}\nMesaj unic: {continut['mesaj_unic']}\n"
        f"Format: {continut['format']}\nApel la acțiune (unul singur): {continut['apel_la_actiune']}\n"
        f"{vizual}{text_idee(continut.get('idee'))}{comercial}Interdicții: {interdictii}\n"
        f"Fapte permise (singurele cifre, prețuri și promisiuni permise):\n{fapte}"
    )
