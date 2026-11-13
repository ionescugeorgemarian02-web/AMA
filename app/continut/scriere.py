"""Hook-uri și postări (F6.3): generatorul de hook-uri (E1), alegerea, autorul de postări (E4), editorul (E8),
apoi
cascada de validare (F5) cu cel mult 2 reparații și aprobarea, dacă nivelul de autonomie o cere (docs/13
§13.2).

1. E1 (profilul `creatie`) propune 3–5 hook-uri pe tipare diferite (biblioteca din §13.4); fiecare primește un
scor
   DETERMINIST (`scor_hook`: problemele G8 de hook, lungimea, cifre în afara faptelor permise, legătura cu
   subiectul);
   se alege cel mai bun (la egalitate, primul). Variantele și alegerea se salvează (`variante_hook`).
2. E4 scrie postarea pe hook-ul ales, din brief (lume închisă: doar faptele permise) și din exemplele
aprobate.
3. E8 editează determinist (`editor.editeaza`); nu schimbă fapte.
4. Conținutul se scrie prin `validare.continut.scrie`, livrabilul trece `in_scriere → in_validare`; cascada îl
validează.
   Reparația o face tot autorul (`repara`, înregistrat ca sursă de autor în `validare.autor`) pe instrucțiunea
   unificată.
5. După `validat` (punctul de extensie `validare.ciclu.inregistreaza_dupa_validare`): aprobare dacă autonomia
o cere,
   `aprobat` la nivel automat, nimic la L0 (umbră). Doar pentru livrabilele cu brief (cele din calendar).
"""

import re
import uuid
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import creier, gateway, productie, validare
from app.continut import brief, editor, prompturi
from app.continut.modele import VariantaHook
from app.ids import new_id
from app.logging import get_logger
from app.operare.motor import Prioritate
from app.productie import Stare

log = get_logger("app.continut")
COMPONENTA_HOOK, COMPONENTA_POSTARE = "E1", "E4"
TIPARE = ("intrebare", "contraintuitiv", "rezultat", "greseala", "cifra", "poveste", "inainte_dupa")
Tipar = Literal["intrebare", "contraintuitiv", "rezultat", "greseala", "cifra", "poveste", "inainte_dupa"]
CUVINTE_HOOK_MAXIM = 20  # [I] docs/13 §13.4: un hook scurt; G8 semnalează peste 25
# [I] scriptul video: hook-ul se rostește în primele 3 secunde (13.3), la ~2,5 cuvinte pe secundă
CUVINTE_HOOK_PE_TIP = {"script_video_scurt": 7}


class HookPropus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=3, max_length=300)
    tipar: Tipar


class PropunereHookuri(gateway.Iesire):
    hookuri: list[HookPropus] = Field(min_length=3, max_length=5)


class PostareScrisa(gateway.Iesire):
    text: str = Field(min_length=20, max_length=3000)
    hashtaguri: list[str] = Field(default_factory=list, max_length=5)


class TextReparat(gateway.Iesire):
    text: str = Field(min_length=10, max_length=6000)


class ScriereRefuzata(creier.RegulaCreier):
    """Livrabilul nu se poate scrie (stare greșită, fără brief)."""


class AutorEsuat(RuntimeError):
    """Autorul nu a putut produce un material care respectă regulile tipului (de exemplu durata unui script):
    livrabilul
    merge în coada de erori cu diagnostic, nu în validare."""


# --- nucleul alegerii
# --------------------------------------------------------------------------------------------


def _cifre(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", text))


def scor_hook(
    text: str, continut_brief: dict[str, object], *, cuvinte_maxim: int = CUVINTE_HOOK_MAXIM
) -> tuple[int, list[str]]:
    """Scorul unui hook (mai mare = mai bun) și problemele lui. Nucleu pur, determinist."""
    probleme = [
        p.regula
        for p in validare.probleme_hook(validare.Continut(versiune=1, text=text, campuri={"hook": text}))
    ]
    scor = 100 - 25 * len(probleme)
    n = len(text.split())
    if n > cuvinte_maxim:
        probleme.append("hook_prea_lung")
        scor -= 15 if cuvinte_maxim >= CUVINTE_HOOK_MAXIM else 30
    fapte = continut_brief.get("fapte_permise")
    permise: set[str] = set()
    for f in fapte if isinstance(fapte, list) else []:
        permise |= _cifre(str(f.get("text", "")) if isinstance(f, dict) else "")
    if _cifre(text) - permise:
        probleme.append("cifra_fara_fapt")
        scor -= 50
    subiect = {w.lower() for w in re.findall(r"\w{4,}", str(continut_brief.get("subiect", "")))}
    if not subiect & {w.lower() for w in re.findall(r"\w{4,}", text)}:
        scor -= 10
    return scor, probleme


def alege(
    hookuri: list[HookPropus], continut_brief: dict[str, object], *, cuvinte_maxim: int = CUVINTE_HOOK_MAXIM
) -> int:
    """Indicele hook-ului ales: cel mai mare scor; la egalitate, primul."""
    scoruri = [scor_hook(h.text, continut_brief, cuvinte_maxim=cuvinte_maxim)[0] for h in hookuri]
    return max(range(len(hookuri)), key=lambda i: (scoruri[i], -i))


# --- serviciile
# -------------------------------------------------------------------------------------------------


def variante(db: Session, livrabil_id: uuid.UUID) -> list[VariantaHook]:
    return list(
        db.execute(
            select(VariantaHook).where(VariantaHook.livrabil_id == livrabil_id).order_by(VariantaHook.nr)
        ).scalars()
    )


def exemple_text(db: Session, lv: productie.Livrabil) -> str:
    """Exemplele aprobate și respinse pentru același tip și canal (F6.7); șir gol dacă nu există."""
    return ""


def hook_ales(db: Session, lv: productie.Livrabil, b: dict[str, object]) -> str:
    """Hook-ul ales pentru livrabil (variantele existente se refolosesc: pasul e idempotent)."""
    existente = variante(db, lv.id)
    if existente:
        return next(v.text for v in existente if v.ales)
    prompturi.asigura()
    r = gateway.apeleaza(
        db,
        prompt="continut.hookuri@1",
        schema=PropunereHookuri,
        tenant_id=lv.tenant_id,
        componenta="continut.hookuri",
        livrabil_id=lv.id,
        prioritate=Prioritate.P2,
        max_tokeni=800,
        temperatura=0.7,
        variabile={
            "tip": lv.tip,
            "canal": lv.canal,
            "brief": brief.text_pentru_autor(b),
            "exemple": exemple_text(db, lv),
        },
    )
    if not isinstance(r.iesire, PropunereHookuri):
        raise TypeError("ieșirea nu respectă schema promptului")
    hookuri = r.iesire.hookuri
    maxim = CUVINTE_HOOK_PE_TIP.get(lv.tip, CUVINTE_HOOK_MAXIM)
    ales = alege(hookuri, b, cuvinte_maxim=maxim)
    for i, h in enumerate(hookuri):
        scor, probleme = scor_hook(h.text, b, cuvinte_maxim=maxim)
        db.add(
            VariantaHook(
                id=new_id(),
                tenant_id=lv.tenant_id,
                livrabil_id=lv.id,
                nr=i + 1,
                text=h.text,
                tipar=h.tipar,
                scor=scor,
                probleme=probleme,
                ales=i == ales,
                model=r.model,
            )
        )
    db.flush()
    return hookuri[ales].text


def _scrie_postarea(db: Session, lv: productie.Livrabil, b: dict[str, object]) -> validare.ContinutNou:
    hook = editor.editeaza(hook_ales(db, lv, b))
    r = gateway.apeleaza(
        db,
        prompt="continut.postare@1",
        schema=PostareScrisa,
        tenant_id=lv.tenant_id,
        componenta="continut.postare",
        livrabil_id=lv.id,
        prioritate=Prioritate.P2,
        max_tokeni=1200,
        variabile={
            "canal": lv.canal,
            "hook": hook,
            "brief": brief.text_pentru_autor(b),
            "exemple": exemple_text(db, lv),
        },
    )
    if not isinstance(r.iesire, PostareScrisa):
        raise TypeError("ieșirea nu respectă schema promptului")
    text = editor.editeaza(r.iesire.text)
    if not text.startswith(hook):
        text = f"{hook}\n\n{text}"
    hashtaguri = [h.lstrip("#").strip() for h in r.iesire.hashtaguri if h.strip("# ")]
    return validare.ContinutNou(
        text=text,
        campuri={"hook": hook, "hashtaguri": hashtaguri},
        autor=COMPONENTA_POSTARE,
        model_autor=r.model,
    )


# Autorii pe tip de livrabil: E4 (postări) aici, E2 (scripturi video) în `scripturi`, înregistrat la import.
AUTORI: dict[str, Callable[[Session, productie.Livrabil, dict[str, object]], validare.ContinutNou]] = {
    "postare": _scrie_postarea
}


def scrie(db: Session, livrabil_id: uuid.UUID) -> validare.ContinutLivrabil | None:
    """Scrie versiunea completă a unui livrabil `briefat` (sau reluat în `in_scriere`) și îl trimite în
    validare
    (`in_validare`); `None` dacă autorul a eșuat (livrabilul e în coada de erori). Ridică `gateway.Amanat`
    (nimic nu
    s-a mutat) sau `ScriereRefuzata`."""
    lv = productie.blocheaza(db, livrabil_id)
    b = brief.al_livrabilului(db, lv.id)
    if b is None:
        raise ScriereRefuzata("livrabilul nu are brief")
    if lv.tip not in AUTORI:
        raise ScriereRefuzata(f"niciun autor pentru tipul {lv.tip}")
    stare = Stare(lv.stare)
    if stare not in (Stare.BRIEFAT, Stare.IN_SCRIERE):
        raise ScriereRefuzata(f"livrabilul este „{productie.ETICHETE[stare]}”, nu „Briefat”")
    try:
        nou = AUTORI[lv.tip](db, lv, b.continut)
    except AutorEsuat as exc:
        if stare is Stare.BRIEFAT:
            productie.muta(db, lv.id, Stare.BRIEFAT, Stare.IN_SCRIERE, componenta="continut", motiv="scriere")
        productie.muta(
            db, lv.id, Stare.IN_SCRIERE, Stare.COADA_DE_ERORI, componenta="continut", motiv=str(exc)[:300]
        )
        return None
    if stare is Stare.BRIEFAT:
        productie.muta(db, lv.id, Stare.BRIEFAT, Stare.IN_SCRIERE, componenta=nou.autor, motiv="scriere")
    rand = validare.continut.scrie(
        db,
        lv.id,
        text=nou.text,
        campuri=nou.campuri,
        active=nou.active,
        autor=nou.autor,
        model_autor=nou.model_autor,
    )
    productie.muta(
        db, lv.id, Stare.IN_SCRIERE, Stare.IN_VALIDARE, componenta=nou.autor, motiv="trimis la validare"
    )
    return rand


def repara(db: Session, sarcina: validare.SarcinaReparatie) -> validare.ContinutNou | None:
    """Autorul reparațiilor pentru livrabilele din calendar (cele cu brief); `None` pentru celelalte."""
    if brief.al_livrabilului(db, sarcina.livrabil_id) is None:
        return None
    r = gateway.apeleaza(
        db,
        prompt="continut.repara@1",
        schema=TextReparat,
        tenant_id=sarcina.tenant_id,
        componenta="continut.repara",
        livrabil_id=sarcina.livrabil_id,
        prioritate=Prioritate.P2,
        max_tokeni=1500,
        variabile={
            "tip": sarcina.tip,
            "canal": sarcina.canal,
            "text": sarcina.continut.text,
            "instructiune": sarcina.instructiune,
        },
    )
    if not isinstance(r.iesire, TextReparat):
        raise TypeError("ieșirea nu respectă schema promptului")
    campuri = dict(sarcina.continut.campuri)
    text = editor.editeaza(r.iesire.text)
    if isinstance(campuri.get("hook"), str):
        campuri["hook"] = validare.propozitii(text)[0] if validare.propozitii(text) else campuri["hook"]
    return validare.ContinutNou(
        text=text,
        campuri=campuri,
        active=list(sarcina.continut.active),
        autor=sarcina.continut.autor or COMPONENTA_POSTARE,
        model_autor=r.model,
    )


def dupa_validare(db: Session, lv: productie.Livrabil) -> None:
    """Pasul 9 din §13.2 pentru livrabilele din calendar: aprobarea, dacă nivelul de autonomie o cere."""
    if Stare(lv.stare) is not Stare.VALIDAT or brief.al_livrabilului(db, lv.id) is None:
        return
    decizie = productie.autonomie.decide(db, lv)
    if decizie is productie.Decizie.APROBARE:
        productie.aprobari.cere(db, lv.id, componenta="continut")
    elif decizie is productie.Decizie.AUTOMAT:
        productie.muta(
            db, lv.id, Stare.VALIDAT, Stare.APROBAT, componenta="continut", motiv="nivel de autonomie automat"
        )
    # L0 (umbră): livrabilul se produce, dar nu merge mai departe


validare.autor.inregistreaza_sursa(repara)
validare.ciclu.inregistreaza_dupa_validare(dupa_validare)
