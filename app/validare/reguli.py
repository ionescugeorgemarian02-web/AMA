"""Pachetele de reguli (docs/09 §9.7): fișiere TOML versionate în `rulepacks/` (pe platformă, pe nișă,
generale), încărcate
cu validare de schemă, plus evaluarea pură a unei reguli asupra unui text.

- O regulă are identificator, text, tip de potrivire (`cuvant`, `lista`, `regex`, `calcul`, `obligatoriu`),
severitate (`minora` =
  avertisment, `majora` = blochează și se repară, `critica` = carantină), sursă (politica platformei sau
  legea, cu URL), marcaj
  (`[I]` = sursa nu a fost verificată de un om), data ultimei verificări și cel puțin un exemplu care
  trebuie blocat și unul care
  trebuie să treacă (un test le rulează automat: `verifica_exemple`).
- Regulile se schimbă DOAR prin revizuire umană. Acest modul citește fișierele și nu are nicio cale de
scriere spre ele (gardă:
  `tests/unit/test_reguli_garzi.py`); regulile pe client sunt în bază (`reguli_client.py`), cu autor uman
  obligatoriu.
- Tiparele se potrivesc pe textul fără diacritice și cu litere mici (`afirmatii.baza`: aceeași lungime, deci
fragmentul se
  extrage exact din textul original).
"""

import functools
import hashlib
import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.validare.afirmatii import baza

DIRECTOR = Path(__file__).resolve().parents[2] / "rulepacks"
POTRIVIRI = ("cuvant", "lista", "regex", "calcul", "obligatoriu")
FRAGMENT_MAXIM = 160


class ReguliInvalide(ValueError):
    """Un pachet de reguli nu respectă schema (se vede la încărcare, nu la rulare)."""


class Sursa(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tip: Literal["politica_platformei", "lege"]
    titlu: str = Field(min_length=5, max_length=300)
    url: str = Field(pattern=r"^https?://[^\s]+$", max_length=500)


class Exemplu(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=3, max_length=4000)
    campuri: dict[str, Any] = Field(default_factory=dict)
    canal: str | None = None


class Conditie(BaseModel):
    model_config = ConfigDict(extra="forbid")
    camp: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    este: bool | str


@dataclass(frozen=True)
class Context:
    """Ce se știe despre textul evaluat, în afară de text."""

    canal: str = ""
    tip: str = ""
    campuri: dict[str, Any] | None = None


# --- calcule (funcții mici, fără efecte, cu parametri din fișier)
# ------------------------------------------------------------


def _raport_majuscule(text: str, parametri: dict[str, Any]) -> list[str]:
    litere = [c for c in text if c.isalpha()]
    if len(litere) < int(parametri.get("minim_litere", 20)):
        return []
    raport = sum(1 for c in litere if c.isupper()) / len(litere)
    return [text.strip()[:FRAGMENT_MAXIM]] if raport > float(parametri.get("prag", 0.5)) else []


def _hashtaguri(text: str, parametri: dict[str, Any]) -> list[str]:
    gasite = re.findall(r"#\w+", text)
    return (
        [" ".join(gasite[: int(parametri.get("maxim", 10)) + 1])[:FRAGMENT_MAXIM]]
        if len(gasite) > int(parametri.get("maxim", 10))
        else []
    )


def _semne_exclamare(text: str, parametri: dict[str, Any]) -> list[str]:
    n = text.count("!")
    return ["!" * min(n, 8)] if n > int(parametri.get("maxim", 3)) else []


CALCULE: dict[str, Callable[[str, dict[str, Any]], list[str]]] = {
    "raport_majuscule": _raport_majuscule,
    "hashtaguri": _hashtaguri,
    "semne_exclamare": _semne_exclamare,
}


class Regula(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{2,60}$")
    text: str = Field(min_length=10, max_length=500)
    potrivire: Literal["cuvant", "lista", "regex", "calcul", "obligatoriu"]
    tipare: list[str] = Field(default_factory=list, max_length=40)
    calcul: str | None = None
    parametri: dict[str, Any] = Field(default_factory=dict)
    daca_text: list[str] = Field(default_factory=list, max_length=10)
    conditie: Conditie | None = None
    canale: list[str] = Field(default_factory=list)
    tipuri: list[str] = Field(default_factory=list)
    severitate: Literal["minora", "majora", "critica"]
    sursa: Sursa
    marcaj: Literal["[I]", "verificat"]
    verificat_la: date
    instructiune: str | None = Field(default=None, max_length=400)
    exemple_blocate: list[Exemplu] = Field(min_length=1, max_length=20)
    exemple_trece: list[Exemplu] = Field(min_length=1, max_length=20)

    @field_validator("exemple_blocate", "exemple_trece", mode="before")
    @classmethod
    def _exemple(cls, v: Any) -> Any:
        return [{"text": x} if isinstance(x, str) else x for x in v] if isinstance(v, list) else v

    @model_validator(mode="after")
    def _coerenta(self) -> "Regula":
        if self.potrivire == "calcul":
            if self.calcul not in CALCULE:
                raise ValueError(f"calcul necunoscut: {self.calcul!r}; există {sorted(CALCULE)}")
            if self.tipare:
                raise ValueError("o regulă de calcul nu are tipare")
        else:
            if self.calcul is not None:
                raise ValueError("`calcul` se folosește doar la potrivirea „calcul”")
            if not self.tipare:
                raise ValueError("lipsesc tiparele")
        for t in (
            (*self.tipare, *self.daca_text) if self.potrivire in ("regex", "obligatoriu") else self.daca_text
        ):
            try:
                re.compile(t)
            except re.error as exc:
                raise ValueError(f"expresie regulată invalidă {t!r}: {exc}") from None
            if len(t) > 400:
                raise ValueError("expresie regulată prea lungă")
        if self.daca_text and self.potrivire != "obligatoriu":
            raise ValueError("`daca_text` se folosește doar la potrivirea „obligatoriu”")
        return self


class Pachet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pachet: str = Field(pattern=r"^[a-z][a-z0-9-]{1,40}$")
    tip: Literal["general", "platforma", "nisa", "juridic"]
    titlu: str = Field(min_length=5, max_length=200)
    versiune: int = Field(ge=1)
    canale: list[str] = Field(default_factory=list)
    se_aplica: Literal["mereu", "nisa"] = "mereu"
    nisa: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,40}$")
    reguli: list[Regula] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _coerenta(self) -> "Pachet":
        if self.tip in ("general", "platforma", "juridic") and not self.canale:
            raise ValueError("un pachet general / de platformă își numește canalele (sau „*”)")
        if self.tip == "nisa" and self.nisa is None:
            raise ValueError("un pachet de nișă își numește nișa")
        ids = [r.id for r in self.reguli]
        if len(ids) != len(set(ids)):
            raise ValueError("identificatori de reguli dublați în pachet")
        return self


@dataclass(frozen=True)
class PachetIncarcat:
    pachet: Pachet
    amprenta: str  # sha256 al fișierului: identifică exact versiunea regulilor care au judecat un text
    fisier: str

    @property
    def nume(self) -> str:
        return self.pachet.pachet


@dataclass(frozen=True)
class Potrivire:
    regula: Regula
    fragment: str  # exact din text; gol când lipsește ceva obligatoriu


# --- încărcare --------------------------------------------------------------------------------------------
# -------------------


def _citeste(cale: Path) -> PachetIncarcat:
    brut = cale.read_bytes()
    try:
        date_ = tomllib.loads(brut.decode("utf-8"))
        pachet = Pachet.model_validate(date_)
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        raise ReguliInvalide(f"{cale.name}: {exc}") from exc
    return PachetIncarcat(pachet, hashlib.sha256(brut).hexdigest(), cale.name)


@functools.cache
def incarca(director: Path = DIRECTOR) -> tuple[PachetIncarcat, ...]:
    """Toate pachetele din `rulepacks/` (și `nise/`), validate; identificatori unici în tot setul."""
    pachete = [_citeste(c) for c in sorted(director.rglob("*.toml"))]
    nume = [p.nume for p in pachete]
    if len(nume) != len(set(nume)):
        raise ReguliInvalide("nume de pachet dublate")
    ids = [r.id for p in pachete for r in p.pachet.reguli]
    dubluri = sorted({i for i in ids if ids.count(i) > 1})
    if dubluri:
        raise ReguliInvalide(f"identificatori de reguli dublați între pachete: {dubluri}")
    return tuple(pachete)


def selecteaza(
    canal: str, nise: list[str] | tuple[str, ...] = (), director: Path = DIRECTOR
) -> list[PachetIncarcat]:
    """Pachetele unui livrabil: generale, ale platformei canalului și ale nișelor (mereu sau declarate)."""
    iesire = []
    for p in incarca(director):
        pk = p.pachet
        if pk.tip == "juridic":
            continue  # pachetul juridic îl aplică G9, nu G3
        if pk.tip == "nisa":
            if pk.se_aplica == "mereu" or pk.nisa in nise:
                iesire.append(p)
        elif "*" in pk.canale or canal in pk.canale:
            iesire.append(p)
    return iesire


# --- evaluare (pură) --------------------------------------------------------------------------------------
# ---------------------


def pachete_juridice(canal: str, director: Path = DIRECTOR) -> list[PachetIncarcat]:
    """Pachetele de mențiuni obligatorii (tip `juridic`), aplicate de G9."""
    return [
        p
        for p in incarca(director)
        if p.pachet.tip == "juridic" and ("*" in p.pachet.canale or canal in p.pachet.canale)
    ]


def se_aplica(r: Regula, ctx: Context) -> bool:
    if r.canale and ctx.canal not in r.canale:
        return False
    if r.tipuri and ctx.tip not in r.tipuri:
        return False
    if r.conditie is not None:
        return (ctx.campuri or {}).get(r.conditie.camp) == r.conditie.este
    return True


def _fragmente(text: str, b: str, sablon: str) -> list[str]:
    return [text[m.start() : m.end()][:FRAGMENT_MAXIM] for m in re.finditer(sablon, b) if m.end() > m.start()]


def potriviri(r: Regula, text: str, ctx: Context | None = None) -> list[Potrivire]:
    """Fragmentele din `text` care încalcă regula (sau o potrivire cu fragment gol când lipsește ceva
    obligatoriu)."""
    ctx = ctx or Context()
    if not se_aplica(r, ctx):
        return []
    b = baza(text)
    if r.potrivire == "calcul":
        assert r.calcul is not None  # noqa: S101  (validat la încărcare)
        return [Potrivire(r, f) for f in CALCULE[r.calcul](text, r.parametri)]
    if r.potrivire == "obligatoriu":
        if r.daca_text and not any(re.search(t, b) for t in r.daca_text):
            return []
        return [] if any(re.search(t, b) for t in r.tipare) else [Potrivire(r, "")]
    if r.potrivire == "regex":
        sabloane = r.tipare
    else:  # cuvant | lista: se potrivesc ca expresii întregi, cu litere mici și fără diacritice
        marginit = [r"(?<![a-z0-9])" + re.escape(baza(t)) + r"(?![a-z0-9])" for t in r.tipare]
        sabloane = marginit
    gasite = [f for s in sabloane for f in _fragmente(text, b, s)]
    return [Potrivire(r, f) for f in dict.fromkeys(gasite)]


def verifica_exemple(r: Regula, canal_implicit: str = "") -> list[str]:
    """Probleme ale exemplelor unei reguli (listă goală = în regulă): fiecare exemplu „blocat” trebuie să
    producă o potrivire,
    fiecare exemplu „trece” nu are voie să producă niciuna."""
    probleme = []
    for tip, exemple, asteptat in (("blocat", r.exemple_blocate, True), ("trece", r.exemple_trece, False)):
        for e in exemple:
            ctx = Context(canal=e.canal or canal_implicit, campuri=e.campuri)
            gasit = bool(potriviri(r, e.text, ctx))
            if gasit != asteptat:
                probleme.append(
                    f"{r.id}: exemplul „{tip}” {'nu a fost blocat' if asteptat else 'a fost blocat'}: "
                    f"{e.text[:80]!r}"
                )
    return probleme


def toate_regulile(director: Path = DIRECTOR) -> list[tuple[PachetIncarcat, Regula]]:
    return [(p, r) for p in incarca(director) for r in p.pachet.reguli]
