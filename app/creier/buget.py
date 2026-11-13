"""Bugetul de tokeni al pachetului de context (F4.7, docs/10 §10.3). Nucleu pur, determinist.

Estimatorul este simplu și documentat: 1 token ≈ 3 caractere (la fel ca estimarea cotelor din gateway pentru
română); rotunjit în sus. Trunchierea nu rupe elemente: un element intră întreg sau nu intră. Secțiunile se
parcurg în ordinea priorității (cele dintâi se pierd ultimele); în interiorul unei secțiuni, elementele în
ordinea dată (deja sortată după relevanță de apelant). Un element care nu încape se sare (se notează), iar
următoarele, mai mici, pot încăpea. Secțiunile „obligatorii” (reguli și interdicții) intră întotdeauna și se
rezervă primele: dacă singure depășesc bugetul, pachetul spune `depasit`.
"""

from dataclasses import dataclass, field

CARACTERE_PE_TOKEN = 3


def estimeaza_tokeni(text: str) -> int:
    return -(-len(text) // CARACTERE_PE_TOKEN)


@dataclass(frozen=True)
class Candidat:
    sectiune: str
    cheie: str  # identificator stabil al elementului (pentru raportul de trunchiere)
    text: str


@dataclass(frozen=True)
class Alegere:
    pastrate: list[Candidat]
    taiate: list[tuple[Candidat, str]]  # (element, motiv)
    tokeni: int
    depasit: bool
    pe_sectiune: dict[str, int] = field(default_factory=dict)


def alege(
    candidati: list[Candidat], *, prioritati: list[str], obligatorii: frozenset[str], buget: int
) -> Alegere:
    """Alege elementele care încap în `buget`. `prioritati`: secțiunile, de la cea mai importantă.

    Întâi se rezervă elementele secțiunilor obligatorii (indiferent de poziția lor în `prioritati`), apoi
    restul, în ordinea priorității, cât mai încap. Rezultatul păstrează ordinea priorității, nu pe cea a
    intrării."""
    ordine = {s: i for i, s in enumerate(prioritati)}
    sortate = sorted(enumerate(candidati), key=lambda p: (ordine.get(p[1].sectiune, len(ordine)), p[0]))
    ramas = buget
    tinute: set[int] = set()
    taiate: list[tuple[Candidat, str]] = []
    for idx, c in sortate:
        if c.sectiune in obligatorii:
            tinute.add(idx)
            ramas -= estimeaza_tokeni(c.text)
    depasit = ramas < 0
    for idx, c in sortate:
        if c.sectiune in obligatorii:
            continue
        t = estimeaza_tokeni(c.text)
        if t <= ramas:
            tinute.add(idx)
            ramas -= t
        else:
            taiate.append((c, "buget"))
    pastrate = [c for idx, c in sortate if idx in tinute]
    pe_sectiune: dict[str, int] = {}
    for c in pastrate:
        pe_sectiune[c.sectiune] = pe_sectiune.get(c.sectiune, 0) + estimeaza_tokeni(c.text)
    return Alegere(pastrate, taiate, buget - ramas, depasit, pe_sectiune)
