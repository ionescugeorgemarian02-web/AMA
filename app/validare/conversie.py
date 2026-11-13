"""G8 Lizibilitate și conversie (docs/09 §9.4, docs/13 §13.1 și §13.4): hook, un singur apel la acțiune,
text ușor de citit.

V1 (determinist, `date/conversie.toml`, praguri [I]):
- apeluri la acțiune: se numără GRUPELE distincte de forme imperative (cumpărare, contact, navigare,
înscriere, vizită, social,
  încercare); mai mult de o grupă → respins („un singur mesaj și un singur apel la acțiune”); niciunul, la
  tipurile care îl cer → avertisment;
- hook (prima frază, sau câmpul `hook`): deschideri fără conținut („Bună ziua”, „Vă informăm”) și prima
frază prea lungă → avertisment;
- lizibilitate: fraze foarte lungi, media cuvintelor pe propoziție, procentul de cuvinte lungi și indicele
ILA (documentat în fișierul de date).
V3 (opțional): rubrica «hook clar» / «un singur mesaj», DOAR când V1 a semnalat hook-ul; confirmarea cere
fragment literal.
"""

import re
from dataclasses import dataclass
from typing import Any

from app.validare import judecator, registru, text_ro
from app.validare.afirmatii import baza
from app.validare.date_validare import incarca
from app.validare.intrare import Continut, Intrare
from app.validare.probleme import Problema, verdict_din_probleme
from app.validare.verdict import Severitate, Treapta, Verdict

COD = "G8"
VERSIUNE = "1"
VERSIUNE_V3 = "1"
PROPOZITIE = re.compile(r"(?<=[.!?…])\s+(?=[^\W\d_a-z]|[„\"“#@0-9])|\n+")


def propozitii(text: str) -> list[str]:
    """Propozițiile unui text (după . ! ? … și rânduri noi); adresele nu se rup (punctul din linkuri
    nu închide propoziția)."""
    protejat = text_ro.URL.sub(lambda m: m.group(0).replace(".", "․"), text)
    return [p.replace("․", ".").strip() for p in PROPOZITIE.split(protejat) if p and p.strip()]


# --- apeluri la acțiune -----------------------------------------------------------------------------------
# -------------------------


@dataclass(frozen=True)
class ApelAction:
    grupa: str
    fragment: str


def apeluri(text: str) -> list[ApelAction]:
    """Toate formele imperative de apel la acțiune din text, cu grupa lor, în ordinea apariției."""
    b = baza(text)
    gasite: list[tuple[int, ApelAction]] = []
    for grupa, sabloane in incarca("conversie")["cta"]["grupe"].items():
        for s in sabloane:
            for m in re.finditer(s, b):
                gasite.append((m.start(), ApelAction(grupa, text[m.start() : m.end()])))
    return [a for _, a in sorted(gasite, key=lambda x: x[0])]


def grupe_distincte(continut: Continut) -> list[ApelAction]:
    """Un apel pe grupă: prima apariție. Câmpul `cta` contribuie cu grupele lui; dacă nu se potrivește nicio
    grupă și textul nu are
    apeluri, câmpul însuși este apelul (o grupă proprie)."""
    in_text = apeluri(
        continut.text_complet if not continut.campuri.get("cta") else _fara_camp(continut, "cta")
    )
    in_camp = apeluri(str(continut.campuri.get("cta") or ""))
    prima: dict[str, ApelAction] = {}
    for a in [*in_text, *in_camp]:
        prima.setdefault(a.grupa, a)
    if not prima and str(continut.campuri.get("cta") or "").strip():
        prima["cta_camp"] = ApelAction("cta_camp", str(continut.campuri["cta"]).strip()[:80])
    return list(prima.values())


def _fara_camp(continut: Continut, camp: str) -> str:
    return "\n".join(t for n, t in continut.texte() if not n.startswith(camp))


def probleme_apeluri(tip: str, continut: Continut) -> list[Problema]:
    grupe = grupe_distincte(continut)
    if len(grupe) > 1:
        lista = "; ".join(f"„{a.fragment}” ({a.grupa})" for a in grupe)
        return [
            Problema(
                "G8.apeluri_multiple",
                grupe[1].fragment,
                f"Textul are {len(grupe)} apeluri la acțiune diferite ({lista}). Păstrează un singur "
                f"apel și scoate-le pe celelalte.",
                detalii=", ".join(a.grupa for a in grupe),
            )
        ]
    if not grupe and tip in incarca("conversie")["cta"]["tipuri_cu_apel"]:
        return [
            Problema(
                "G8.fara_apel_la_actiune",
                "",
                "Textul nu are niciun apel la acțiune; adaugă unul singur, clar (ce trebuie să facă "
                "cititorul).",
                blocant=False,
                severitate=Severitate.MAJORA,
            )
        ]
    return []


# --- hook -------------------------------------------------------------------------------------------------
# ------------------------


def prima_fraza(continut: Continut) -> str:
    hook = continut.campuri.get("hook")
    if isinstance(hook, str) and hook.strip():
        return hook.strip()
    p = propozitii(continut.text)
    return p[0] if p else ""


def probleme_hook(continut: Continut) -> list[Problema]:
    fraza = prima_fraza(continut)
    if not fraza:
        return []
    cfg = incarca("conversie")["hook"]
    b = baza(fraza)
    probleme = []
    for slab in cfg["deschideri_slabe"]:
        if b.startswith(slab):
            probleme.append(
                Problema(
                    "G8.hook_deschidere_slaba",
                    fraza[:100],
                    "Prima frază este o formulă fără conținut; începe direct cu ce interesează "
                    "cititorul (o întrebare, o cifră, un rezultat).",
                    blocant=False,
                    severitate=Severitate.MINORA,
                )
            )
            break
    n = len(text_ro.cuvinte(fraza))
    if n > int(cfg["cuvinte_maxim"]):
        probleme.append(
            Problema(
                "G8.hook_lung",
                fraza[:100],
                f"Prima frază are {n} de cuvinte; scurteaz-o la cel mult {cfg['cuvinte_maxim']}, ca să "
                f"țină atenția.",
                blocant=False,
                severitate=Severitate.MINORA,
            )
        )
    return probleme


# --- lizibilitate -----------------------------------------------------------------------------------------
# --------------------------


@dataclass(frozen=True)
class Lizibilitate:
    cuvinte: int
    propozitii: int
    medie: float  # cuvinte pe propoziție
    procent_lungi: float
    indice: float  # ILA 0–100


def lizibilitate(text: str) -> Lizibilitate:
    """Indicele AMA de lizibilitate (ILA, vezi `date/conversie.toml`): 100 − 2 × medie − 0,8 × procent
    de cuvinte lungi."""
    cfg = incarca("conversie")["lizibilitate"]
    cuv = text_ro.cuvinte(text)
    prop = [p for p in propozitii(text_ro.fara_adrese(text)) if text_ro.cuvinte(p)]
    if not cuv or not prop:
        return Lizibilitate(0, 0, 0.0, 0.0, 100.0)
    medie = len(cuv) / len(prop)
    lungi = sum(1 for c in cuv if len(c) >= int(cfg["cuvant_lung_litere"])) / len(cuv) * 100
    indice = max(0.0, min(100.0, 100 - 2 * medie - 0.8 * lungi))
    return Lizibilitate(len(cuv), len(prop), round(medie, 1), round(lungi, 1), round(indice, 1))


def probleme_lizibilitate(text: str) -> tuple[list[Problema], Lizibilitate]:
    cfg = incarca("conversie")["lizibilitate"]
    liz = lizibilitate(text)
    probleme: list[Problema] = []
    if liz.cuvinte < int(cfg["cuvinte_minim"]):
        return probleme, liz
    for p in propozitii(text):
        n = len(text_ro.cuvinte(p))
        if n > int(cfg["fraza_maxima_cuvinte"]):
            probleme.append(
                Problema(
                    "G8.fraza_prea_lunga",
                    p[:100],
                    f"Fraza care începe cu „{p[:50]}…” are {n} de cuvinte; împarte-o în fraze mai "
                    f"scurte (cel mult "
                    f"{cfg['fraza_maxima_cuvinte']} de cuvinte).",
                    blocant=False,
                    severitate=Severitate.MINORA,
                )
            )
            break
    if liz.indice < float(cfg["indice_minim"]):
        probleme.append(
            Problema(
                "G8.text_greu_de_citit",
                "",
                f"Textul este greu de citit (indice {liz.indice:.0f} din 100, minim "
                f"{cfg['indice_minim']}): fraze de {liz.medie:.0f} "
                f"cuvinte în medie și {liz.procent_lungi:.0f}% cuvinte lungi. Folosește fraze și "
                f"cuvinte mai scurte.",
                blocant=False,
                severitate=Severitate.MAJORA,
                detalii=f"ILA={liz.indice}",
            )
        )
    return probleme, liz


@registru.validator(
    registru.DefinitieValidator(
        COD,
        "Lizibilitate și conversie",
        VERSIUNE,
        Treapta.V1,
        60,
        descriere="Un singur apel la acțiune, hook (prima frază), lizibilitate (indice ILA)",
    )
)
def g8_reguli(intrare: Intrare) -> Verdict:
    probleme_liz, liz = probleme_lizibilitate(intrare.text)
    hook = probleme_hook(intrare.continut)
    intrare.memo("g8.hook_slab", lambda: bool(hook))
    detalii: dict[str, Any] = {
        "ila": liz.indice,
        "cuvinte": liz.cuvinte,
        "medie_cuvinte_pe_propozitie": liz.medie,
        "procent_cuvinte_lungi": liz.procent_lungi,
        "hook_slab": bool(hook),
    }
    return verdict_din_probleme(
        COD,
        VERSIUNE,
        Treapta.V1,
        [*probleme_apeluri(intrare.livrabil.tip, intrare.continut), *hook, *probleme_liz],
        detalii=detalii,
    )


CRITERII_V3 = {
    "hook_clar": "Prima frază atrage atenția și spune despre ce este mesajul (nu este un salut sau o "
    "formulă goală).",
    "un_singur_mesaj": "Textul transmite un singur mesaj principal, nu mai multe fără legătură între ele.",
}
INSTRUCTIUNI_V3 = {
    "hook_clar": "Rescrie prima frază ca un cârlig clar: întrebare, cifră sau rezultat, direct la subiect.",
    "un_singur_mesaj": "Păstrează un singur mesaj principal; scoate sau mută în alt livrabil restul.",
}


@registru.validator(
    registru.DefinitieValidator(
        COD,
        "Conversie (judecător)",
        VERSIUNE_V3,
        Treapta.V3,
        60,
        foloseste_model=True,
        descriere="Rubrica «hook clar» / «un singur mesaj», doar când V1 a semnalat hook-ul",
    )
)
def g8_judecator(intrare: Intrare) -> Verdict | None:
    if not intrare.memo("g8.hook_slab", lambda: bool(probleme_hook(intrare.continut))):
        return None  # hook-ul trece regulile simple: nu se consumă cotă
    return judecator.judeca(
        intrare,
        validator=COD,
        versiune=VERSIUNE_V3,
        treapta=Treapta.V3,
        prompt="validare.g8_conversie",
        criterii=CRITERII_V3,
        instructiuni=INSTRUCTIUNI_V3,
    )
