"""G10 Limbă (docs/09 §9.4, docs/13 §13.5): diacritice lipsă, ș / ț cu sedilă, „î” / „â” la locul
nepotrivit, repetiții și
ghilimele (V1, determinist), plus un judecător mic opțional pentru acordul gramatical și registru (V3).

Diacritice lipsă: (1) un dicționar de cuvinte frecvente scrise fără diacritice (`date/limba.toml`; doar
cuvinte a căror
formă fără diacritice nu este ea însăși un cuvânt românesc), (2) raportul literelor cu diacritice: un text
lung fără nicio
diacritică este respins chiar dacă dicționarul nu l-a prins. Cu sedilă (ş ţ) → avertisment, cu corecția
cerută; există și
`corecteaza_sedila` pentru cine vrea să corecteze automat. Editorul nu schimbă fapte (13.5): corectura de
aici nu atinge cifre.
"""

import re

from app.validare import judecator, registru, text_ro
from app.validare.date_validare import incarca
from app.validare.intrare import Intrare
from app.validare.probleme import Problema, verdict_din_probleme
from app.validare.verdict import Severitate, Treapta, Verdict

COD = "G10"
VERSIUNE = "1"
VERSIUNE_V3 = "1"
MAXIM_EXEMPLE = 3


def corecteaza_sedila(text: str) -> str:
    """ş ţ Ş Ţ → ș ț Ș Ț (aceeași literă, codificare corectă)."""
    return text.translate(str.maketrans(incarca("limba")["sedila"]["literele"]))


def _litere(text: str) -> list[str]:
    return [c for c in text if c.isalpha()]


def _probleme_diacritice(text: str) -> list[Problema]:
    d = incarca("limba")
    dic = d["cuvinte_frecvente_fara_diacritice"]
    cfg = d["diacritice"]
    probleme: list[Problema] = []
    hit: list[tuple[str, str]] = []
    for cuv in text_ro.cuvinte(text):
        if len(cuv) >= 2 and cuv.isupper():
            continue  # sigle și titluri în majuscule (USA, TVA)
        corect = dic.get(cuv.lower())
        if corect is not None:
            hit.append((cuv, corect if cuv.islower() else corect[0].upper() + corect[1:]))
    n_cuvinte = len(text_ro.cuvinte(text))
    litere = _litere(text_ro.fara_adrese(text))
    cu_diacritice = sum(1 for c in litere if c in text_ro.DIACRITICE + text_ro.SEDILA)
    raport = cu_diacritice / len(litere) if litere else 1.0
    fara_nicio = n_cuvinte >= cfg["cuvinte_minim"] and raport < cfg["prag_raport_minim"]
    if hit or fara_nicio:
        exemple = list(dict.fromkeys(hit))[:MAXIM_EXEMPLE]
        ex = "; ".join(f"„{a}” → „{b}”" for a, b in exemple)
        blocant = fara_nicio or len(hit) >= cfg["greseli_pentru_esec"]
        probleme.append(
            Problema(
                "G10.diacritice_lipsa",
                exemple[0][0] if exemple else text.strip()[:60],
                "Textul trebuie scris cu toate diacriticele românești (ă, â, î, ș, ț)"
                + (f"; de exemplu {ex}." if ex else "."),
                blocant=blocant,
                severitate=Severitate.MAJORA,
                detalii=f"cuvinte din dicționar: {len(hit)}; raportul diacriticelor: {raport:.3f}",
            )
        )
    return probleme


def _probleme_sedila(text: str) -> list[Problema]:
    gasite = sorted({c for c in text if c in text_ro.SEDILA})
    if not gasite:
        return []
    return [
        Problema(
            "G10.sedila",
            "".join(gasite),
            "Folosește ș și ț cu virgulă (nu cu sedilă: ş, ţ).",
            blocant=False,
            severitate=Severitate.MINORA,
            detalii=f"litere cu sedilă: {''.join(gasite)}",
        )
    ]


def _probleme_i_a(text: str) -> list[Problema]:
    prefixe = tuple(incarca("limba")["i_a"]["prefixe_cu_i"])
    rele: list[str] = []
    for cuv in text_ro.cuvinte(text):
        mic = cuv.lower()
        if len(mic) < 3:
            continue
        if mic[0] == "â" or mic[-1] == "â":
            rele.append(cuv)
        elif "î" in mic[1:-1]:
            poz = mic.index("î", 1)
            if not mic[:poz].endswith(prefixe):
                rele.append(cuv)
    if not rele:
        return []
    ex = ", ".join(f"„{x}”" for x in list(dict.fromkeys(rele))[:MAXIM_EXEMPLE])
    return [
        Problema(
            "G10.i_sau_a",
            rele[0],
            f"Verifică „î” / „â”: „î” la începutul și sfârșitul cuvântului, „â” în interior ({ex}).",
            blocant=False,
            severitate=Severitate.MINORA,
        )
    ]


def _probleme_tipografie(text: str) -> list[Problema]:
    corp = text_ro.fara_adrese(text)
    probleme: list[Problema] = []
    if '"' in corp:
        probleme.append(
            Problema(
                "G10.ghilimele",
                '"',
                "Folosește ghilimelele românești „…” în loc de ghilimele drepte.",
                blocant=False,
                severitate=Severitate.MINORA,
            )
        )
    if re.search(r"\w - \w", corp):
        probleme.append(
            Problema(
                "G10.cratima",
                re.search(r"\w - \w", corp).group(0),  # type: ignore[union-attr]
                "Pentru o pauză în frază folosește linia de pauză „–” (cu spații), nu cratima „-”.",
                blocant=False,
                severitate=Severitate.MINORA,
            )
        )
    m = re.search(r"\b([^\W\d_]{3,})\s+\1\b", corp, re.IGNORECASE)
    if m:
        probleme.append(
            Problema(
                "G10.repetitie",
                m.group(0),
                f"Cuvântul „{m.group(1)}” este repetat; scoate una dintre apariții.",
                blocant=False,
                severitate=Severitate.MINORA,
            )
        )
    return probleme


def probleme_limba(text: str) -> list[Problema]:
    """Toate problemele de limbă ale unui text (nucleu pur)."""
    return [
        *_probleme_diacritice(text),
        *_probleme_sedila(text),
        *_probleme_i_a(text),
        *_probleme_tipografie(text),
    ]


@registru.validator(
    registru.DefinitieValidator(
        COD,
        "Limbă",
        VERSIUNE,
        Treapta.V1,
        20,
        descriere="Diacritice lipsă, sedilă, î / â, ghilimele, repetiții",
    )
)
def g10_reguli(intrare: Intrare) -> Verdict:
    return verdict_din_probleme(COD, VERSIUNE, Treapta.V1, probleme_limba(intrare.text))


CRITERII_V3 = {
    "acord": "Acordul gramatical este corect (subiect–predicat, adjectiv–substantiv, gen și număr).",
    "registru": "Registrul este același în tot textul (tu sau dumneavoastră), fără amestec.",
}
INSTRUCTIUNI_V3 = {
    "acord": "Corectează acordul gramatical din fragmentul indicat.",
    "registru": "Păstrează același registru în tot textul (fără amestec de tu și dumneavoastră).",
}


@registru.validator(
    registru.DefinitieValidator(
        COD,
        "Limbă (judecător)",
        VERSIUNE_V3,
        Treapta.V3,
        20,
        foloseste_model=True,
        descriere="Acord gramatical și registru, prin rubrică da / nu cu dovadă (model diferit de autor)",
    )
)
def g10_judecator(intrare: Intrare) -> Verdict:
    return judecator.judeca(
        intrare,
        validator=COD,
        versiune=VERSIUNE_V3,
        treapta=Treapta.V3,
        prompt="validare.g10_limba",
        criterii=CRITERII_V3,
        instructiuni=INSTRUCTIUNI_V3,
    )
