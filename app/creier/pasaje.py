"""Împărțirea textului în pasaje și normalizarea pentru căutare (F4.3, docs/10 §10.5). Nucleu pur.

Pasajele păstrează legătura cu sursa: fiecare are poziția (`pozitie`) și decalajele de caractere (`inceput`,
`sfarsit`) în textul documentului, iar textul lui este EXACT felia `text[inceput:sfarsit]` (verificatorul de
citate din F4.6 se bazează pe asta). Regula: paragrafele (separate prin rând gol) nu se rup decât dacă un
paragraf singur depășește `maxim`; atunci se rupe la propoziții, iar o propoziție uriașă la cuvinte. Pasajele
vecine se suprapun cu cel mult `suprapunere` caractere, în unități întregi (paragraf / propoziție).
"""

import re
import unicodedata
from dataclasses import dataclass

TINTA = 900  # caractere: un pasaj se închide când următoarea unitate l-ar depăși
MAXIM = 1400  # o unitate mai lungă se rupe
SUPRAPUNERE = 150
MINIM_ALNUM = 3  # un pasaj fără cel puțin atâtea litere / cifre nu se păstrează

STOPURI = frozenset(
    [
        "a",
        "al",
        "ale",
        "alte",
        "alta",
        "altul",
        "am",
        "ai",
        "are",
        "aveti",
        "avem",
        "as",
        "asa",
        "ca",
        "cat",
        "cate",
        "care",
        "cand",
        "ce",
        "cei",
        "cel",
        "cu",
        "cum",
        "da",
        "dar",
        "de",
        "deci",
        "din",
        "desi",
        "dupa",
        "e",
        "el",
        "ea",
        "ele",
        "este",
        "esti",
        "eu",
        "fi",
        "fie",
        "fara",
        "in",
        "intr",
        "intre",
        "iar",
        "la",
        "le",
        "li",
        "lui",
        "ma",
        "mai",
        "mi",
        "mult",
        "ne",
        "nu",
        "o",
        "ori",
        "pe",
        "pentru",
        "pot",
        "poate",
        "poti",
        "prin",
        "sa",
        "se",
        "si",
        "sunt",
        "sau",
        "sub",
        "tot",
        "toate",
        "un",
        "una",
        "unei",
        "unor",
        "unui",
        "va",
        "vi",
        "voi",
        "vor",
        "vreau",
        "ca",
        "imi",
        "iti",
    ]
)  # fără diacritice: se aplică după normalizare


@dataclass(frozen=True)
class Bucata:
    pozitie: int
    inceput: int
    sfarsit: int
    text: str


def normalizeaza(text: str) -> str:
    """Text pentru căutarea lexicală: litere mici, fără diacritice (ș / ş / s, ț / ţ / t, ă / â / î → a / a /
    i),
    orice altceva decât litere și cifre devine spațiu. Determinist."""
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("ß", "ss").replace("ø", "o").replace("đ", "d").replace("ł", "l")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def jetoane(text: str) -> list[str]:
    """Cuvintele semnificative ale unui text, fără cuvinte de legătură, unice, în ordinea apariției."""
    iesire: list[str] = []
    for j in normalizeaza(text).split():
        if len(j) >= 2 and j not in STOPURI and j not in iesire:
            iesire.append(j)
    return iesire


def _unitati(text: str, maxim: int) -> list[tuple[int, int]]:
    """Unitățile de tăiat, ca (început, sfârșit): paragrafele; un paragraf peste `maxim` → propoziții; o
    propoziție
    peste `maxim` → cuvinte."""
    unitati: list[tuple[int, int]] = []
    for m in re.finditer(r"\S(?:.*?\S)?(?=[^\S\n]*\n\s*\n|\s*\Z)", text, re.DOTALL):
        a, b = m.start(), m.end()
        if b - a <= maxim:
            unitati.append((a, b))
            continue
        for p in re.finditer(r"\S.*?(?:[.!?…](?=\s|$)|$)", text[a:b], re.DOTALL):
            pa, pb = a + p.start(), a + p.end()
            while pb - pa > maxim:  # propoziție uriașă: la un spațiu cât mai aproape de limită
                taie = text.rfind(" ", pa, pa + maxim)
                taie = taie if taie > pa else pa + maxim
                unitati.append((pa, taie))
                pa = taie
                while pa < pb and text[pa].isspace():
                    pa += 1
            if pb > pa:
                unitati.append((pa, pb))
    return unitati


def imparte(
    text: str, *, tinta: int = TINTA, maxim: int = MAXIM, suprapunere: int = SUPRAPUNERE
) -> list[Bucata]:
    """Pasajele unui text, în ordine. Textul fiecărui pasaj este `text[inceput:sfarsit]`."""
    if not (0 < tinta <= maxim) or suprapunere < 0 or suprapunere >= tinta:
        raise ValueError("parametri de împărțire nepotriviți")
    unitati = _unitati(text, maxim)
    iesire: list[Bucata] = []
    i = 0
    while i < len(unitati):
        j = i + 1
        while j < len(unitati) and unitati[j][1] - unitati[i][0] <= tinta:
            j += 1
        a, b = unitati[i][0], unitati[j - 1][1]
        if len(re.sub(r"[^A-Za-z0-9À-ž]", "", text[a:b])) >= MINIM_ALNUM:
            iesire.append(Bucata(len(iesire), a, b, text[a:b]))
        if j >= len(unitati):
            break
        # următorul pasaj începe cu cele mai din urmă unități care încap în `suprapunere`, dar măcar cu
        # unitatea
        # următoare celei de început (altfel nu înaintăm)
        k = j
        while k - 1 > i and unitati[j - 1][1] - unitati[k - 1][0] <= suprapunere:
            k -= 1
        i = k
    return iesire


def fuzioneaza(
    clasamente: dict[str, list[str]], *, k: int = 60, ponderi: dict[str, float] | None = None
) -> list[tuple[str, float, dict[str, int]]]:
    """Fuziune de ranguri reciproce (RRF): scorul unui element este suma `pondere / (k + rang)` peste
    clasamentele în
    care apare (rang de la 1). Întoarce (element, scor, ranguri pe clasament), de la cel mai bun; la scoruri
    egale
    câștigă cel cu cel mai bun rang individual, apoi ordinea alfabetică a identificatorului (determinist)."""
    scor: dict[str, float] = {}
    ranguri: dict[str, dict[str, int]] = {}
    for nume, lista in clasamente.items():
        w = (ponderi or {}).get(nume, 1.0)
        vazute: set[str] = set()
        for rang, e in enumerate(lista, 1):
            if e in vazute:
                continue
            vazute.add(e)
            scor[e] = scor.get(e, 0.0) + w / (k + rang)
            ranguri.setdefault(e, {})[nume] = rang
    return sorted(
        ((e, round(s, 12), ranguri[e]) for e, s in scor.items()),
        key=lambda x: (-x[1], min(x[2].values()), x[0]),
    )
