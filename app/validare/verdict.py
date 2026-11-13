"""Forma unui verdict (docs/09 §9.2). Nucleu pur: fără bază de date, fără model, fără rețea.

Un validator întoarce: identitatea și versiunea lui, treapta, verdictul (`trece` / `avertisment` / `esec`),
severitatea, scorul, dovezile (fragmentul EXACT și regula încălcată), instrucțiunea de corectare și costul.

- `esec`: blochează livrabilul și oprește cascada. Severitatea hotărăște ce urmează: `majora` = blocaj
reparabil
  (autorul primește instrucțiunea), `critica` = nu se repară prin rescriere, livrabilul intră în carantină.
- `avertisment`: nu blochează; se adună (`agregare`), iar peste un prag livrabilul merge la om.
- `trece`: nu are severitate.

Un verdict nu se poate construi incomplet: un eșec fără dovadă sau fără instrucțiune este o eroare de
programare.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class Rezultat(StrEnum):
    TRECE = "trece"
    AVERTISMENT = "avertisment"
    ESEC = "esec"


class Severitate(StrEnum):
    MINORA = "minora"
    MAJORA = "majora"
    CRITICA = "critica"


class Treapta(StrEnum):
    """Treptele cascadei (9.1), în ordinea rulării."""

    V0 = "V0"  # structură
    V1 = "V1"  # reguli: liste și calcule
    V2 = "V2"  # similaritate (vectori)
    V3 = "V3"  # judecători mici
    V4 = "V4"  # judecător puternic
    V5 = "V5"  # om

    @property
    def ordine(self) -> int:
        return int(self.value[1])

    @property
    def gratuita(self) -> bool:
        """V0–V2 nu consumă cotă de model: toți pașii treptei rulează înainte să se oprească cascada."""
        return self.ordine <= 2


ETICHETE_TREAPTA = {
    Treapta.V0: "V0 Structură",
    Treapta.V1: "V1 Reguli",
    Treapta.V2: "V2 Similaritate",
    Treapta.V3: "V3 Judecători mici",
    Treapta.V4: "V4 Judecător puternic",
    Treapta.V5: "V5 Om",
}
ETICHETE_REZULTAT = {Rezultat.TRECE: "trece", Rezultat.AVERTISMENT: "avertisment", Rezultat.ESEC: "eșec"}
ETICHETE_SEVERITATE = {
    Severitate.MINORA: "minoră",
    Severitate.MAJORA: "majoră",
    Severitate.CRITICA: "critică",
}
FRAGMENT_MAXIM = 300
INSTRUCTIUNE_MAXIMA = 1200


class VerdictInvalid(ValueError):
    """Verdict construit în afara formei din 9.2 (eroare de programare a validatorului)."""


@dataclass(frozen=True)
class Dovada:
    """Fragmentul exact din text și regula încălcată. `fragment` poate fi gol doar pentru ce LIPSEȘTE din
    text (un
    câmp obligatoriu, o mențiune): atunci `regula` spune ce lipsește."""

    fragment: str
    regula: str
    detalii: str = ""

    def __post_init__(self) -> None:
        if not self.regula.strip():
            raise VerdictInvalid("dovada cere regula încălcată")
        object.__setattr__(self, "fragment", self.fragment[:FRAGMENT_MAXIM])

    def json(self) -> dict[str, str]:
        return {"fragment": self.fragment, "regula": self.regula, "detalii": self.detalii}


@dataclass(frozen=True)
class Cost:
    apeluri_llm: int = 0
    tokeni_intrare: int = 0
    tokeni_iesire: int = 0
    pret_umbra: Decimal = Decimal(0)
    durata_ms: int = 0

    def __add__(self, alt: "Cost") -> "Cost":
        return Cost(
            self.apeluri_llm + alt.apeluri_llm,
            self.tokeni_intrare + alt.tokeni_intrare,
            self.tokeni_iesire + alt.tokeni_iesire,
            self.pret_umbra + alt.pret_umbra,
            self.durata_ms + alt.durata_ms,
        )

    def json(self) -> dict[str, Any]:
        return {
            "apeluri_llm": self.apeluri_llm,
            "tokeni_intrare": self.tokeni_intrare,
            "tokeni_iesire": self.tokeni_iesire,
            "pret_umbra": str(self.pret_umbra),
            "durata_ms": self.durata_ms,
        }


FARA_COST = Cost()


@dataclass(frozen=True)
class Verdict:
    validator: str  # codul G: „G1”
    versiune: str  # versiunea validatorului (a codului lui); ce mai identifică rularea merge în `detalii`
    treapta: Treapta
    rezultat: Rezultat
    severitate: Severitate | None = None
    scor: float = 1.0  # 1.0 = fără probleme; 0.0 = cel mai rău
    dovezi: tuple[Dovada, ...] = ()
    instructiune: str = ""
    cost: Cost = FARA_COST
    detalii: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.scor <= 1.0:
            raise VerdictInvalid("scorul e între 0 și 1")
        if not self.validator.strip() or not self.versiune.strip():
            raise VerdictInvalid("verdictul cere identitatea și versiunea validatorului")
        if self.rezultat is Rezultat.TRECE:
            if self.severitate is not None:
                raise VerdictInvalid("un verdict „trece” nu are severitate")
            return
        if self.severitate is None:
            raise VerdictInvalid(f"un verdict „{self.rezultat.value}” cere severitate")
        if not self.dovezi:
            raise VerdictInvalid(f"un verdict „{self.rezultat.value}” cere cel puțin o dovadă")
        if not self.instructiune.strip():
            raise VerdictInvalid(f"un verdict „{self.rezultat.value}” cere instrucțiunea de corectare")
        if self.rezultat is Rezultat.ESEC and self.severitate is Severitate.MINORA:
            raise VerdictInvalid("un eșec este cel puțin „majoră”; ce e minor este avertisment")
        object.__setattr__(self, "instructiune", self.instructiune.strip()[:INSTRUCTIUNE_MAXIMA])

    @property
    def blocheaza(self) -> bool:
        return self.rezultat is Rezultat.ESEC

    @property
    def critic(self) -> bool:
        return self.rezultat is Rezultat.ESEC and self.severitate is Severitate.CRITICA


def trece(validator: str, versiune: str, treapta: Treapta, **kw: Any) -> Verdict:
    return Verdict(validator, versiune, treapta, Rezultat.TRECE, **kw)


def avertisment(
    validator: str,
    versiune: str,
    treapta: Treapta,
    *,
    dovezi: tuple[Dovada, ...] | list[Dovada],
    instructiune: str,
    severitate: Severitate = Severitate.MINORA,
    scor: float = 0.7,
    **kw: Any,
) -> Verdict:
    return Verdict(
        validator,
        versiune,
        treapta,
        Rezultat.AVERTISMENT,
        severitate,
        scor,
        tuple(dovezi),
        instructiune,
        **kw,
    )


def esec(
    validator: str,
    versiune: str,
    treapta: Treapta,
    *,
    dovezi: tuple[Dovada, ...] | list[Dovada],
    instructiune: str,
    severitate: Severitate = Severitate.MAJORA,
    scor: float = 0.0,
    **kw: Any,
) -> Verdict:
    return Verdict(
        validator, versiune, treapta, Rezultat.ESEC, severitate, scor, tuple(dovezi), instructiune, **kw
    )
