"""Acoperirea afirmațiilor de către registrul de fapte (G2, docs/09 §9.3). Nucleu pur: fără bază de date,
fără model.

Registrul este alcătuit din intrări (`IntrareRegistru`): faptele aprobate și valabile ale clientului,
ofertele (cu prețul
și prețul de referință), eventual citate din surse de cercetare verificate. Cifrele și prețurile se compară
EXACT
(`Decimal`, aceeași normalizare ca la verificatorul de citate), fără model:

- preț: numărul și moneda (lei ≡ RON) trebuie să existe în registru; dacă lângă preț apare numele unei
oferte sau al unui fapt
  cunoscut, prețul trebuie să fie al LUI (un preț real, dar al altui produs, e „preț diferit”);
- procent: număr din registru sau reducere CALCULATĂ din preț și prețul de referință al unei oferte (cu
toleranță de rotunjire);
- termen / dată / oră / cifră: aceeași valoare (și unitate de timp) într-o intrare;
- superlativ / comparație / promisiune: cuvintele semnificative ale expresiei trebuie să apară în aceeași
intrare.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from app.creier import citat
from app.validare import afirmatii as extractor
from app.validare.afirmatii import Afirmatie, baza
from app.validare.date_validare import incarca


class Acoperire(StrEnum):
    ACOPERITA = "acoperita"
    DIFERITA = "diferita"  # valoare diferită de a registrului pentru același subiect
    NEACOPERITA = "neacoperita"


@dataclass(frozen=True)
class IntrareRegistru:
    id: str
    felul: str  # fapt | oferta | sursa
    nume: str  # subiectul faptului sau numele ofertei
    text: str  # tot textul intrării, fără diacritice și cu litere mici
    tip: str = ""  # tipul faptului (pret, termen, garantie …); la oferte „oferta”
    afisare: str = ""  # textul intrării, pe scurt, pentru judecător și pentru ecrane
    numere: frozenset[Decimal] = frozenset()
    preturi: tuple[
        tuple[Decimal, str], ...
    ] = ()  # (număr, monedă); pentru oferte: prețul și prețul de referință
    pret_curent: tuple[Decimal, str] | None = None  # doar la oferte
    pret_ref: tuple[Decimal, str] | None = None  # prețul de referință al ofertei (reducere)
    reducere_pct: Decimal | None = None  # calculată din preț și preț de referință
    procente: frozenset[Decimal] = frozenset()
    date: frozenset[tuple[int, int, int | None]] = frozenset()
    ore: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Registru:
    intrari: tuple[IntrareRegistru, ...] = ()
    fereastra: int = 90
    _radacini: dict[str, frozenset[str]] = field(default_factory=dict, compare=False, repr=False)


def _radacini_text(text: str) -> frozenset[str]:
    n = int(incarca("afirmatii")["acoperire"]["radacina"])
    return frozenset(c[:n] for c in re.findall(r"[a-z0-9]{3,}", baza(text)))


def intrare_din_texte(
    id_: str,
    felul: str,
    nume: str,
    texte: Iterable[str],
    *,
    numar: Decimal | None = None,
    moneda: str | None = None,
    unitate: str | None = None,
    tip: str = "",
    pret: tuple[Decimal, str] | None = None,
    pret_referinta: tuple[Decimal, str] | None = None,
    date_valabilitate: Iterable[tuple[int, int, int]] = (),
) -> IntrareRegistru:
    """Construiește o intrare din textele ei, folosind ACELAȘI extractor ca pentru textul de validat (deci
    aceleași
    normalizări): prețurile, procentele, datele și orele din text intră structurat în registru."""
    toate = [t for t in (nume, *texte) if t and t.strip()]
    corp = "\n".join(toate)
    numere: set[Decimal] = set()
    preturi: list[tuple[Decimal, str]] = []
    procente: set[Decimal] = set()
    date: set[tuple[int, int, int | None]] = set(date_valabilitate)
    ore: set[str] = set()
    for a in extractor.extrage(corp):
        if a.valoare is not None:
            numere.add(a.valoare)
        if a.tip == "pret" and a.valoare is not None and a.moneda:
            preturi.append((a.valoare, a.moneda))
        elif a.tip == "procent" and a.valoare is not None:
            procente.add(a.valoare)
        elif a.tip == "data" and a.data:
            date.add(a.data)
        elif a.tip == "ora" and a.ora:
            ore.add(a.ora)
    for n in citat.numere_din(corp):  # și numerele goale, din textul intrării
        numere.add(n)
    if numar is not None:
        numere.add(numar)
        if moneda:
            preturi.append((numar, moneda))
        if unitate and "%" in unitate:
            procente.add(numar)
    reducere = None
    if pret is not None:
        numere.add(pret[0])
        preturi.append(pret)
    if pret_referinta is not None:
        numere.add(pret_referinta[0])
        preturi.append(pret_referinta)
        if pret is not None and pret_referinta[0] > 0:
            reducere = (pret_referinta[0] - pret[0]) / pret_referinta[0] * 100
    return IntrareRegistru(
        id=id_,
        felul=felul,
        nume=nume,
        tip=tip,
        afisare=" ".join(corp.split())[:240],
        text=baza(corp),
        numere=frozenset(numere),
        preturi=tuple(dict.fromkeys(preturi)),
        pret_curent=pret,
        pret_ref=pret_referinta,
        reducere_pct=reducere,
        procente=frozenset(procente),
        date=frozenset(date),
        ore=frozenset(ore),
    )


# --- potrivire
# ----------------------------------------------------------------------------------------------------


def _jetoane_nume(nume: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(c[:5] for c in re.findall(r"[a-z]{4,}", baza(nume))))


def apropiate(text: str, a: Afirmatie, reg: Registru) -> list[IntrareRegistru]:
    """Intrările al căror nume apare lângă afirmație (toate jetoanele numelui, rădăcini de 5 litere)."""
    fereastra = reg.fereastra
    b = baza(text)
    din, pana = max(0, a.start - fereastra), min(len(b), a.sfarsit + fereastra)
    zona = b[din:pana]
    zona_jetoane = {c[:5] for c in re.findall(r"[a-z]{4,}", zona)}
    gasite = []
    for i in reg.intrari:
        jet = _jetoane_nume(i.nume)
        if jet and all(j in zona_jetoane for j in jet):
            gasite.append(i)
    # preferă numele cele mai specifice (cele mai multe jetoane); „Abonament Lunar” bate „Abonament”
    if gasite:
        cel_mai_lung = max(len(_jetoane_nume(i.nume)) for i in gasite)
        gasite = [i for i in gasite if len(_jetoane_nume(i.nume)) == cel_mai_lung]
    return gasite


def _acelasi(a: Decimal, b: Decimal) -> bool:
    return a == b


def _pret_ok(a: Afirmatie, preturi: Iterable[tuple[Decimal, str]]) -> bool:
    return any(
        _acelasi(p, a.valoare) and (a.moneda is None or m == a.moneda)
        for p, m in preturi
        if a.valoare is not None
    )


MARCAJE_REFERINTA = (
    "in loc de",
    "de la",
    "initial",
    "pret vechi",
    "pretul vechi",
    "anterior",
    "fata de",
    "era ",
)


def _marcaj_referinta(text: str, a: Afirmatie) -> bool:
    """Prețul e prezentat ca preț anterior („în loc de 59 lei”, „redus de la 59 lei”)?"""
    inainte = baza(text)[max(0, a.start - 30) : a.start]
    return any(m in inainte for m in MARCAJE_REFERINTA)


def _preturi_permise(i: IntrareRegistru, referinta: bool) -> list[tuple[Decimal, str]]:
    """Prețul ACTUAL al intrării; prețul de referință doar când textul îl numește ca preț anterior."""
    if i.pret_curent is None:
        return list(i.preturi)
    permise = [i.pret_curent]
    if referinta and i.pret_ref is not None:
        permise.append(i.pret_ref)
    return permise


def _cuvinte_in(a: Afirmatie, i: IntrareRegistru) -> bool:
    radacini = _radacini_text(i.text)
    if not a.cuvinte:  # expresie fără cuvinte semnificative: se cere expresia întreagă
        return baza(a.fragment) in i.text
    return all(c in radacini for c in a.cuvinte)


def acopera(text: str, a: Afirmatie, reg: Registru) -> tuple[Acoperire, str]:
    """(verdictul, ce spune registrul — pentru instrucțiune). Nu folosește niciun model."""
    cfg = incarca("afirmatii")["acoperire"]
    if a.tip == "pret":
        aproape = [i for i in apropiate(text, a, reg) if i.preturi]
        if aproape:
            referinta = _marcaj_referinta(text, a)
            if any(_pret_ok(a, _preturi_permise(i, referinta)) for i in aproape):
                return Acoperire.ACOPERITA, ""
            asteptat = "; ".join(
                f"{i.nume}: {_fmt(i.pret_curent[0] if i.pret_curent else i.preturi[0][0])} "
                f"{i.pret_curent[1] if i.pret_curent else i.preturi[0][1]}"
                for i in aproape
            )
            return Acoperire.DIFERITA, asteptat
        if _pret_ok(a, (p for i in reg.intrari for p in i.preturi)):
            return Acoperire.ACOPERITA, ""
        return Acoperire.NEACOPERITA, ""
    if a.tip == "procent":
        if any(a.valoare in i.procente for i in reg.intrari):
            return Acoperire.ACOPERITA, ""
        tol = Decimal(str(cfg["toleranta_reducere"]))
        calculate = [i for i in reg.intrari if i.reducere_pct is not None]
        for i in calculate:
            if (
                a.valoare is not None
                and i.reducere_pct is not None
                and abs(a.valoare - i.reducere_pct) <= tol
            ):
                return Acoperire.ACOPERITA, ""
        aproape = [i for i in apropiate(text, a, reg) if i.reducere_pct is not None]
        if aproape and (reducere := aproape[0].reducere_pct) is not None:
            return (
                Acoperire.DIFERITA,
                f"{aproape[0].nume}: reducere {_fmt(reducere.quantize(Decimal('0.1')))}%",
            )
        return Acoperire.NEACOPERITA, ""
    if a.tip == "termen":
        for i in reg.intrari:
            if a.valoare in i.numere and a.unitate and a.unitate in baza(i.text):
                return Acoperire.ACOPERITA, ""
        return Acoperire.NEACOPERITA, ""
    if a.tip == "data":
        d = a.data
        if d is None:
            return Acoperire.NEACOPERITA, ""
        for i in reg.intrari:
            for zi, luna, an in i.date:
                if (zi, luna) == (d[0], d[1]) and (d[2] is None or an is None or an == d[2]):
                    return Acoperire.ACOPERITA, ""
                if d[0] == 0 and an == d[2]:  # „din 2019”
                    return Acoperire.ACOPERITA, ""
        return Acoperire.NEACOPERITA, ""
    if a.tip == "ora":
        return (
            (Acoperire.ACOPERITA, "")
            if any(a.ora in i.ore for i in reg.intrari)
            else (Acoperire.NEACOPERITA, "")
        )
    if a.tip == "cifra":
        return (
            (Acoperire.ACOPERITA, "")
            if any(a.valoare in i.numere for i in reg.intrari)
            else (Acoperire.NEACOPERITA, "")
        )
    # superlativ, comparație, promisiune
    return (
        (Acoperire.ACOPERITA, "")
        if any(_cuvinte_in(a, i) for i in reg.intrari)
        else (Acoperire.NEACOPERITA, "")
    )


def _fmt(v: Decimal) -> str:
    s = format(v.normalize(), "f")
    return s


@dataclass(frozen=True)
class Constatare:
    afirmatie: Afirmatie
    acoperire: Acoperire
    registru_spune: str = ""


def verifica(text: str, reg: Registru, afirmatii: list[Afirmatie] | None = None) -> list[Constatare]:
    """Fiecare afirmație a textului, cu acoperirea ei."""
    gasite = extractor.extrage(text) if afirmatii is None else afirmatii
    iesire = []
    for a in gasite:
        ac, spune = acopera(text, a, reg)
        iesire.append(Constatare(a, ac, spune))
    return iesire
