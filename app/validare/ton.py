"""G4 Ton (docs/09 §9.4): potrivirea cu ghidul de brand APROBAT al clientului.

- V1 (determinist): vocabularul INTERZIS al ghidului (cuvinte și expresii, cu formele lor, fără diacritice
și fără majuscule) blochează;
  un text lung fără niciun cuvânt din vocabularul PREFERAT primește un avertisment.
- V2 (local): similaritatea cosinus (vectori prin `gateway.vectorizeaza`) dintre text și exemplele aprobate
din ghid (de același canal,
  dacă există). Sub prag → avertisment (tonul e „semnalat”). Pragul depinde de modelul de vectori
  (`date/ton.toml`, [I]).
- V3 (opțional): rubrica „tonul respectă ghidul”, DOAR când V2 a semnalat; dacă rubrica confirmă (cu
fragment literal), textul este respins.

Fără ghid aprobat, tonul nu se poate verifica: avertisment (nu trecere tăcută).
"""

import math
import re
from dataclasses import dataclass, field
from typing import Any

from app import creier, gateway
from app.creier.compartimente import Compartiment
from app.operare.motor import Prioritate
from app.validare import afirmatii, judecator, registru, text_ro
from app.validare.date_validare import incarca
from app.validare.intrare import Intrare
from app.validare.probleme import Problema, verdict_din_probleme
from app.validare.verdict import Cost, Severitate, Treapta, Verdict

COD = "G4"
VERSIUNE = "1"
VERSIUNE_V2 = "1"
VERSIUNE_V3 = "1"


@dataclass(frozen=True)
class Ghid:
    """Ce folosește G4 din ghidul de brand aprobat (cheia `ghid` din `profil_brand`; câmpurile din
    F4.5)."""

    nume: str
    descriere: str
    reguli_da: tuple[str, ...]
    reguli_nu: tuple[str, ...]
    vocabular_preferat: tuple[str, ...]
    vocabular_interzis: tuple[str, ...]
    exemple: tuple[tuple[str, str], ...]  # (canal, text)
    versiune: int = 0

    def exemple_pentru(self, canal: str) -> list[str]:
        maxim = int(incarca("ton")["similaritate"]["exemple_maxim"])
        ale_canalului = [t for c, t in self.exemple if c == canal]
        return (ale_canalului or [t for _, t in self.exemple])[:maxim]

    def ca_text(self) -> str:
        return (
            f"Ton „{self.nume}”: {self.descriere}\nSă faci: {'; '.join(self.reguli_da)}\nSă nu faci: "
            f"{'; '.join(self.reguli_nu)}\n"
            f"Vocabular preferat: {', '.join(self.vocabular_preferat)}\nVocabular interzis: "
            f"{', '.join(self.vocabular_interzis)}\n"
            "Exemple aprobate:\n" + "\n".join(f"- [{c}] {t}" for c, t in self.exemple)
        )


def ghid_din(continut: dict[str, Any], versiune: int = 0) -> Ghid | None:
    """`None` dacă intrarea nu arată a ghid (nu are exemple)."""
    exemple = continut.get("exemple")
    if not isinstance(exemple, list) or not exemple:
        return None

    def lista(cheie: str) -> tuple[str, ...]:
        v = continut.get(cheie)
        return tuple(str(x) for x in v) if isinstance(v, list) else ()

    return Ghid(
        nume=str(continut.get("nume", "")),
        descriere=str(continut.get("descriere", "")),
        reguli_da=lista("reguli_da"),
        reguli_nu=lista("reguli_nu"),
        vocabular_preferat=lista("vocabular_preferat"),
        vocabular_interzis=lista("vocabular_interzis"),
        exemple=tuple(
            (str(e.get("canal", "")), str(e.get("text", "")))
            for e in exemple
            if isinstance(e, dict) and e.get("text")
        ),
        versiune=versiune,
    )


def ghid_aprobat(intrare: Intrare) -> Ghid | None:
    """Ghidul de brand APROBAT și valabil la data livrabilului (o singură citire pe rulare)."""

    def citeste() -> Ghid | None:
        intrari = creier.citire.pentru_context(
            intrare.baza(), intrare.tenant_id, Compartiment.PROFIL_BRAND, intrare.la
        )
        for e in intrari:
            g = ghid_din(e.continut, e.versiune) if e.cheie == "ghid" else None
            if g is not None:
                return g
        return None

    return intrare.memo("g4.ghid", citeste)


# --- V1: vocabular ----------------------------------------------------------------------------------------
# -------------------


def _forma(cuvant: str) -> str:
    return afirmatii.baza(cuvant).strip()


def gaseste_in_text(text: str, termen: str) -> list[str]:
    """Fragmentele exacte din `text` care conțin `termen` (cuvânt cu formele lui, sau expresie). Fără
    diacritice, fără majuscule."""
    t = _forma(termen)
    if not t:
        return []
    b = afirmatii.baza(text)
    cfg = incarca("ton")["vocabular"]
    if " " in t:
        return [
            text[m.start() : m.end()]
            for m in re.finditer(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", b)
        ]
    n = int(cfg["prefix_minim"])
    if len(t) <= n:  # cuvânt scurt: potrivire exactă, pe cuvânt întreg
        sablon = r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])"
    else:  # cuvânt lung: și formele lui (ieftin → ieftină, ieftine)
        sablon = r"(?<![a-z0-9])" + re.escape(t[: max(n, len(t) - 2)]) + r"[a-z0-9]*"
    return [text[m.start() : m.end()] for m in re.finditer(sablon, b)]


def probleme_vocabular(text: str, ghid: Ghid) -> list[Problema]:
    probleme: list[Problema] = []
    for interzis in ghid.vocabular_interzis:
        gasite = gaseste_in_text(text, interzis)
        if gasite:
            probleme.append(
                Problema(
                    "G4.vocabular_interzis",
                    gasite[0],
                    f"Brandul nu folosește „{interzis}” (ghidul de brand); reformulează „{gasite[0]}”.",
                    detalii=f"termen interzis: {interzis}",
                )
            )
    n_cuvinte = len(text_ro.cuvinte(text))
    minim = int(incarca("ton")["vocabular"]["cuvinte_minim_pentru_preferat"])
    nu_foloseste_preferate = not any(gaseste_in_text(text, p) for p in ghid.vocabular_preferat)
    if ghid.vocabular_preferat and n_cuvinte >= minim and nu_foloseste_preferate:
        probleme.append(
            Problema(
                "G4.fara_vocabular_preferat",
                "",
                "Folosește cel puțin un cuvânt din vocabularul preferat al brandului: "
                + ", ".join(ghid.vocabular_preferat[:6])
                + ".",
                blocant=False,
                severitate=Severitate.MINORA,
            )
        )
    return probleme


@registru.validator(
    registru.DefinitieValidator(
        COD,
        "Ton (vocabular)",
        VERSIUNE,
        Treapta.V1,
        50,
        descriere="Vocabularul interzis / preferat al ghidului de brand aprobat",
    )
)
def g4_vocabular(intrare: Intrare) -> Verdict:
    ghid = ghid_aprobat(intrare)
    if ghid is None:
        return _fara_ghid(Treapta.V1, VERSIUNE)
    return verdict_din_probleme(
        COD,
        VERSIUNE,
        Treapta.V1,
        probleme_vocabular(intrare.text, ghid),
        detalii={"ghid_versiune": ghid.versiune},
    )


def _fara_ghid(treapta: Treapta, versiune: str) -> Verdict:
    return verdict_din_probleme(
        COD,
        versiune,
        treapta,
        [
            Problema(
                "G4.fara_ghid_aprobat",
                "",
                "Clientul nu are un ghid de brand aprobat: tonul nu s-a putut verifica; un om trebuie "
                "să-l verifice.",
                blocant=False,
                severitate=Severitate.MINORA,
            )
        ],
        detalii={"ghid": None},
    )


# --- V2: similaritate -------------------------------------------------------------------------------------
# ----------------------


def cosinus(a: list[float], b: list[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return (
        0.0
        if na == 0 or nb == 0
        else max(0.0, min(1.0, sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)))
    )


def cea_mai_apropiata(vector_text: list[float], vectori_exemple: list[list[float]]) -> tuple[float, int]:
    """(similaritatea maximă, indicele exemplului cel mai apropiat) — nucleu pur."""
    scoruri = [cosinus(vector_text, v) for v in vectori_exemple]
    i = max(range(len(scoruri)), key=lambda k: scoruri[k])
    return scoruri[i], i


@dataclass
class Similaritate:
    scor: float | None  # None: nu s-a putut calcula
    exemplu: str = ""
    motiv: str = ""
    durata_ms: int = field(default=0)


def calculeaza_similaritatea(intrare: Intrare, ghid: Ghid) -> Similaritate:
    """Vectorii prin gateway (o singură dată pe rulare). Orice eroare a gateway-ului lasă scorul
    necalculat."""

    def calc() -> Similaritate:
        import time

        exemple = ghid.exemple_pentru(intrare.livrabil.canal)
        start = time.monotonic()
        try:
            vectori = gateway.vectorizeaza(
                [intrare.text[:6000], *exemple],
                tenant_id=intrare.tenant_id,
                componenta="validare.g4",
                prioritate=Prioritate.P1,
            )
        except (gateway.Amanat, gateway.EroareGateway) as exc:
            return Similaritate(None, motiv=type(exc).__name__)
        scor, i = cea_mai_apropiata(vectori[0], vectori[1:])
        return Similaritate(scor, exemple[i], durata_ms=int((time.monotonic() - start) * 1000))

    return intrare.memo("g4.similaritate", calc)


@registru.validator(
    registru.DefinitieValidator(
        COD,
        "Ton (similaritate)",
        VERSIUNE_V2,
        Treapta.V2,
        50,
        descriere="Similaritatea cu exemplele aprobate din ghidul de brand (vectori)",
    )
)
def g4_similaritate(intrare: Intrare) -> Verdict | None:
    cfg = incarca("ton")["similaritate"]
    if len(text_ro.cuvinte(intrare.text)) < int(cfg["text_minim_cuvinte"]):
        return None
    ghid = ghid_aprobat(intrare)
    if ghid is None:
        return None  # lipsa ghidului a fost deja raportată la V1
    s = calculeaza_similaritatea(intrare, ghid)
    cost = Cost(durata_ms=s.durata_ms)
    detalii = {"prag": cfg["prag"], "ghid_versiune": ghid.versiune, "scor_similaritate": s.scor}
    if s.scor is None:
        return verdict_din_probleme(
            COD,
            VERSIUNE_V2,
            Treapta.V2,
            [
                Problema(
                    "G4.similaritate_necalculata",
                    "",
                    "Similaritatea cu tonul brandului nu s-a putut calcula; tonul cere verificare umană.",
                    blocant=False,
                    severitate=Severitate.MINORA,
                    detalii=s.motiv,
                )
            ],
            cost=cost,
            detalii=detalii,
        )
    if s.scor >= float(cfg["prag"]):
        v = verdict_din_probleme(COD, VERSIUNE_V2, Treapta.V2, [], cost=cost, detalii=detalii)
        return v
    return verdict_din_probleme(
        COD,
        VERSIUNE_V2,
        Treapta.V2,
        [
            Problema(
                "G4.ton_departe_de_exemple",
                intrare.text.strip()[:120],
                "Tonul pare departe de exemplele aprobate ale brandului; rescrie în stilul lor. Cel "
                "mai apropiat exemplu: "
                f"„{s.exemplu[:160]}”.",
                blocant=False,
                severitate=Severitate.MAJORA,
                detalii=f"similaritate {s.scor:.2f} < prag {cfg['prag']}",
            )
        ],
        cost=cost,
        detalii=detalii,
    )


# --- V3: rubrica ------------------------------------------------------------------------------------------
# -------------------------

CRITERII_V3 = {
    "ton_potrivit": "Textul respectă tonul descris în ghidul de brand și seamănă ca stil cu exemplele "
    "aprobate."
}
INSTRUCTIUNI_V3 = {
    "ton_potrivit": "Rescrie fragmentul indicat în tonul ghidului de brand (vezi exemplele aprobate)."
}


@registru.validator(
    registru.DefinitieValidator(
        COD,
        "Ton (judecător)",
        VERSIUNE_V3,
        Treapta.V3,
        50,
        foloseste_model=True,
        descriere="Rubrica «tonul respectă ghidul», doar când similaritatea a semnalat",
    )
)
def g4_judecator(intrare: Intrare) -> Verdict | None:
    cfg = incarca("ton")["similaritate"]
    ghid = ghid_aprobat(intrare)
    if ghid is None or len(text_ro.cuvinte(intrare.text)) < int(cfg["text_minim_cuvinte"]):
        return None
    s = calculeaza_similaritatea(intrare, ghid)
    if s.scor is not None and s.scor >= float(cfg["prag"]):
        return None  # tonul e aproape de exemple: nu se consumă cotă
    return judecator.judeca(
        intrare,
        validator=COD,
        versiune=VERSIUNE_V3,
        treapta=Treapta.V3,
        prompt="validare.g4_ton",
        criterii=CRITERII_V3,
        instructiuni=INSTRUCTIUNI_V3,
        extra={"ghid": ghid.ca_text()},
    )
