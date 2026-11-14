"""Normalizarea textului românesc înainte de sinteză (F8.2, docs/14 §14.4). Nucleu pur, determinist.

Ordinea: sedilă -> virgulă; dicționarul de pronunție al clientului; adrese web și emailuri; telefoane; date și
ore; sume (lei, bani, euro); procente; unități; ordinale; abrevieri; numerele rămase; simbolurile.

Acordul numeralului se face după substantivul care urmează (heuristică pentru română, [I]): pluralul
masculin în „-i” cere „doi / un”, pluralul în „-e”, „-uri”, „-ă” cere „două / o”; de la 20 în sus (și la sute
întregi) se pune „de” înaintea substantivului („douăzeci de lei”). Excepțiile: `FEMININE` și `MASCULINE`.
"""

import re

UNITATI_0_19 = [
    "zero",
    "unu",
    "doi",
    "trei",
    "patru",
    "cinci",
    "șase",
    "șapte",
    "opt",
    "nouă",
    "zece",
    "unsprezece",
    "doisprezece",
    "treisprezece",
    "paisprezece",
    "cincisprezece",
    "șaisprezece",
    "șaptesprezece",
    "optsprezece",
    "nouăsprezece",
]
ZECI = [
    "",
    "",
    "douăzeci",
    "treizeci",
    "patruzeci",
    "cincizeci",
    "șaizeci",
    "șaptezeci",
    "optzeci",
    "nouăzeci",
]
LUNI = [
    "ianuarie",
    "februarie",
    "martie",
    "aprilie",
    "mai",
    "iunie",
    "iulie",
    "august",
    "septembrie",
    "octombrie",
    "noiembrie",
    "decembrie",
]
ORDINALE = {
    1: ("primul", "prima"),
    2: ("al doilea", "a doua"),
    3: ("al treilea", "a treia"),
    4: ("al patrulea", "a patra"),
    5: ("al cincilea", "a cincea"),
    6: ("al șaselea", "a șasea"),
    7: ("al șaptelea", "a șaptea"),
    8: ("al optulea", "a opta"),
    9: ("al nouălea", "a noua"),
    10: ("al zecelea", "a zecea"),
}

# substantive feminine (sau neutre la plural) fără terminația obișnuită, și masculine în „-e”
FEMININE = {
    "zi",
    "zile",
    "mii",
    "lună",
    "luni",
    "săptămâni",
    "ori",
    "dăți",
    "grade",
    "sute",
    "comenzi",
    "recenzii",
    "ediții",
    "mese",
    "persoane",
    "oferte",
}
MASCULINE = {"leu", "euro", "frate", "pește", "câine", "munte", "dinte", "ani", "oameni"}
CUVINTE_LEGATURA = {
    "de",
    "din",
    "și",
    "sau",
    "la",
    "în",
    "pe",
    "cu",
    "pentru",
    "până",
    "lei",
    "după",
    "ca",
    "că",
    "dar",
    "iar",
    "este",
    "e",
    "sunt",
    "a",
    "al",
    "ale",
    "ai",
    "o",
    "un",
}

# unități: simbol -> (singular, plural, gen) ; gen: m / f (f = feminin sau neutru, „două”)
UNITATI = {
    "kg": ("kilogram", "kilograme", "f"),
    "g": ("gram", "grame", "f"),
    "mg": ("miligram", "miligrame", "f"),
    "km": ("kilometru", "kilometri", "m"),
    "m": ("metru", "metri", "m"),
    "cm": ("centimetru", "centimetri", "m"),
    "mm": ("milimetru", "milimetri", "m"),
    "l": ("litru", "litri", "m"),
    "ml": ("mililitru", "mililitri", "m"),
    "min": ("minut", "minute", "f"),
    "h": ("oră", "ore", "f"),
    "°C": ("grad Celsius", "grade Celsius", "f"),
    "mp": ("metru pătrat", "metri pătrați", "m"),
    "m²": ("metru pătrat", "metri pătrați", "m"),
    "km/h": ("kilometru pe oră", "kilometri pe oră", "m"),
    "GB": ("gigabait", "gigabaiți", "m"),
    "MB": ("megabait", "megabaiți", "m"),
}
ABREVIERI = {
    "nr.": "numărul",
    "str.": "strada",
    "bd.": "bulevardul",
    "bdul.": "bulevardul",
    "tel.": "telefon",
    "etc.": "etcetera",
    "ex.": "exemplu",
    "dl.": "domnul",
    "dna.": "doamna",
    "d-na": "doamna",
    "dl": "domnul",
    "d-voastră": "dumneavoastră",
    "dvs.": "dumneavoastră",
    "ș.a.": "și altele",
    "aprox.": "aproximativ",
    "jud.": "județul",
    "loc.": "localitatea",
    "sec.": "secolul",
    "pag.": "pagina",
    "max.": "maximum",
    "min.": "minimum",
    "cca.": "circa",
    "art.": "articolul",
    "alin.": "alineatul",
    "prof.": "profesorul",
    "dr.": "doctorul",
    "ing.": "inginerul",
    "ian.": "ianuarie",
    "feb.": "februarie",
    "dec.": "decembrie",
    "SRL": "se re le",
    "S.R.L.": "se re le",
    "PFA": "pe fe a",
    "TVA": "te ve a",
    "CUI": "cu i",
    "UE": "u e",
    "SMS": "es em es",
    "PDF": "pe de ef",
    "CV": "ce ve",
    "AI": "a i",
    "IT": "i te",
}
SIMBOLURI = {
    "&": " și ",
    "+": " plus ",
    "=": " egal ",
    "€": " euro ",
    "$": " dolari ",
    "#": " ",
    "*": " ",
    "_": " ",
    "|": " ",
    "~": " ",
    "^": " ",
    "<": " ",
    ">": " ",
}
SEDILA = str.maketrans({"ş": "ș", "ţ": "ț", "Ş": "Ș", "Ţ": "Ț"})


def _sub_100(n: int, fem: bool) -> str:
    if n < 20:
        if fem and n == 2:
            return "două"
        if fem and n == 12:
            return "douăsprezece"
        return UNITATI_0_19[n]
    z, u = divmod(n, 10)
    if u == 0:
        return ZECI[z]
    return f"{ZECI[z]} și {_sub_100(u, fem)}"


def _sub_1000(n: int, fem: bool) -> str:
    s, r = divmod(n, 100)
    parti = []
    if s == 1:
        parti.append("o sută")
    elif s > 1:
        parti.append(f"{_sub_100(s, True)} sute")
    if r:
        parti.append(_sub_100(r, fem))
    return " ".join(parti)


def cere_de(n: int) -> bool:
    """„douăzeci de lei”, „o sută de lei”, dar „nouăsprezece lei”, „o sută unu lei”."""
    r = n % 100
    return n >= 20 and (r == 0 or r >= 20)


def _grup(n: int, singular: str, plural: str) -> str:
    if n == 1:
        return singular
    cuv = cardinal(n, fem=True)
    return f"{cuv} {'de ' if cere_de(n) else ''}{plural}"


def cardinal(n: int, *, fem: bool = False) -> str:
    """Numeralul cardinal în cuvinte (până la 999 999 999). `fem`: „două”, „douăsprezece”, „una”."""
    if n < 0:
        return "minus " + cardinal(-n, fem=fem)
    if n < 1000:
        return _sub_1000(n, fem) if n else "zero"
    if n >= 1_000_000_000:
        return " ".join(UNITATI_0_19[int(c)] for c in str(n))
    mil, rest = divmod(n, 1_000_000)
    mii, r = divmod(rest, 1000)
    parti = []
    if mil:
        parti.append(_grup(mil, "un milion", "milioane"))
    if mii:
        parti.append(_grup(mii, "o mie", "mii"))
    if r:
        parti.append(_sub_1000(r, fem))
    return " ".join(parti)


def _fem(cuvant: str) -> bool:
    c = cuvant.lower().strip(".,;:!?)\"'")
    if c in FEMININE:
        return True
    if c in MASCULINE:
        return False
    if c.endswith("uri"):
        return True
    if c.endswith("i"):
        return False
    return c.endswith(("e", "ă", "a"))


def _inainte_de_substantiv(n: int, urmator: str) -> str:
    """Numeralul urmat de un substantiv: „un leu”, „o cafea”, „două ore”, „douăzeci de lei”."""
    fem = _fem(urmator)
    if n == 1:
        return "o" if fem else "un"
    if n == 2:
        return "două" if fem else "doi"
    return cardinal(n, fem=fem) + (" de" if cere_de(n) else "")


def _numar(s: str) -> float:
    """„1.200” -> 1200, „2,5” -> 2.5."""
    s = s.replace(".", "").replace(" ", "")
    return float(s.replace(",", ".")) if "," in s else float(int(s))


def _zecimal(x: float, fem: bool = False) -> str:
    intreg = int(x)
    zec = round((x - intreg) * 100)
    if zec == 0:
        return cardinal(intreg, fem=fem)
    zecs = f"{zec:02d}".rstrip("0") if zec % 10 == 0 else f"{zec:02d}"
    parte = " ".join("zero" for _ in range(len(zecs) - len(zecs.lstrip("0")))) + " " + cardinal(int(zecs))
    return f"{cardinal(intreg, fem=fem)} virgulă {parte.strip()}"


def _suma(m: re.Match[str]) -> str:
    val = _numar(m.group("v"))
    moneda = m.group("m").lower()
    lei, bani = int(val), round((val - int(val)) * 100)
    if moneda in ("€", "euro", "eur"):
        txt = "un euro" if lei == 1 else f"{_inainte_de_substantiv(lei, 'euro')} euro"
        if bani:
            txt += f" și {'un cent' if bani == 1 else _inainte_de_substantiv(bani, 'cenți') + ' cenți'}"
        return txt
    txt = "un leu" if lei == 1 else f"{_inainte_de_substantiv(lei, 'lei')} lei" if lei else ""
    if bani:
        b = "un ban" if bani == 1 else f"{_inainte_de_substantiv(bani, 'bani')} bani"
        txt = f"{txt} și {b}" if txt else b
    return txt or "zero lei"


def _unitate(m: re.Match[str]) -> str:
    val = _numar(m.group("v"))
    sg, pl, gen = UNITATI[m.group("u")]
    if val != int(val):
        return f"{_zecimal(val, gen == 'f')} {pl}"
    n = int(val)
    if n == 1:
        return f"{'o' if sg == 'oră' else 'un'} {sg}"
    return f"{_inainte_de_substantiv(n, 'ore' if gen == 'f' else 'lei')} {pl}"


def _procent(m: re.Match[str]) -> str:
    val = _numar(m.group("v"))
    return f"{_zecimal(val) if val != int(val) else cardinal(int(val))} la sută"


def _ora(m: re.Match[str]) -> str:
    h, mi = int(m.group("h")), int(m.group("mi"))
    ora = cardinal(h, fem=True) if h else "zero"
    if h == 1:
        ora = "unu"
    if mi == 0:
        return ora
    return f"{ora} și {cardinal(mi, fem=True) if mi != 1 else 'un minut'}"


def _zi(z: int) -> str:
    return "întâi" if z == 1 else cardinal(z)


def _data_lunga(m: re.Match[str]) -> str:
    out = f"{_zi(int(m.group('z')))} {m.group('l').lower()}"
    if m.group("a"):
        out += f" {cardinal(int(m.group('a')))}"
    return out


def _data_scurta(m: re.Match[str]) -> str:
    z, luna, an = int(m.group("z")), int(m.group("l")), m.group("a")
    if not (1 <= z <= 31 and 1 <= luna <= 12):
        return m.group(0)
    a = int(an) + (2000 if len(an) == 2 else 0)
    return f"{_zi(z)} {LUNI[luna - 1]} {cardinal(a)}"


def _telefon(m: re.Match[str]) -> str:
    cifre = re.sub(r"\D", "", m.group(0))
    grupe = [cifre[:4], cifre[4:7], cifre[7:]] if len(cifre) == 10 else [cifre]
    return ", ".join(" ".join(UNITATI_0_19[int(c)] for c in g) for g in grupe if g)


def _web(m: re.Match[str]) -> str:
    t = re.sub(r"^https?://", "", m.group(0)).removeprefix("www.").rstrip("/")
    t = t.replace("@", " arond ").replace(".", " punct ").replace("/", " slaș ").replace("-", " cratimă ")
    return re.sub(r"\s+", " ", t).strip()


def _ordinal(m: re.Match[str]) -> str:
    n = int(m.group("n"))
    fem = m.group("art") == "a"
    if n in ORDINALE:
        return ORDINALE[n][1 if fem else 0]
    return f"a {cardinal(n, fem=True)}a" if fem else f"al {cardinal(n)}lea"


def _numar_liber(m: re.Match[str]) -> str:
    v, urm = m.group("v"), m.group("u") or ""
    if m.group("de"):
        n = int(_numar(v)) if "," not in v else 0
        if n and urm.strip().isalpha():
            fem = _fem(urm.strip())
            cuv = ("o" if fem else "un") if n == 1 else cardinal(n, fem=fem)
            return f"{cuv} de{urm}"
        urm = " de" + urm
    if "," in v:
        return _zecimal(_numar(v)) + (f" {urm}" if urm else "")
    n = int(_numar(v))
    if 1000 <= n <= 2100 and len(v) == 4:  # an
        return cardinal(n) + (f" {urm}" if urm else "")
    cuv = urm.strip()
    if cuv and cuv.isalpha() and cuv.islower() and cuv not in CUVINTE_LEGATURA:
        return f"{_inainte_de_substantiv(n, cuv)} {urm}"
    return cardinal(n) + (f" {urm}" if urm else "")


RE_WEB = re.compile(
    r"\b(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:ro|com|eu|net|org|io|md)(?:/[\w/-]*)?"
    r"|\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+",
    re.IGNORECASE,
)
RE_TELEFON = re.compile(r"(?<!\d)0[237]\d{2}[ .]?\d{3}[ .]?\d{3}(?!\d)")
RE_DATA_LUNGA = re.compile(
    r"\b(?P<z>[1-9]|[12]\d|3[01])\s+(?P<l>" + "|".join(LUNI) + r")(?:\s+(?P<a>\d{4}))?\b", re.IGNORECASE
)
RE_DATA_SCURTA = re.compile(r"\b(?P<z>\d{1,2})[./](?P<l>\d{1,2})[./](?P<a>\d{4}|\d{2})\b")
RE_ORA = re.compile(r"\b(?P<h>[01]?\d|2[0-3]):(?P<mi>[0-5]\d)\b")
NUM = r"(?P<v>\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)"
RE_SUMA = re.compile(NUM + r"\s*(?P<m>lei|leu|ron|euro|eur|€)(?![a-zăâîșț])", re.IGNORECASE)
RE_SUMA_EURO_INAINTE = re.compile(r"€\s*" + NUM)
RE_PROCENT = re.compile(NUM + r"\s*%")
RE_UNITATE = re.compile(
    NUM
    + r"\s*(?P<u>"
    + "|".join(re.escape(u) for u in sorted(UNITATI, key=len, reverse=True))
    + r")(?![\w/²])"
)
RE_ORDINAL = re.compile(r"\b(?P<art>al|a)\s+(?P<n>\d+)-(?:lea|a)\b")
RE_INTERVAL = re.compile(r"(?<=\d)\s*[-–]\s*(?=\d)")
RE_NUMAR = re.compile(NUM + r"(?P<de>\s+de(?=\s))?(?P<u>\s+[\wăâîșțĂÂÎȘȚ]+)?")


def _abrevieri(text: str) -> str:
    for ab, tot in sorted(ABREVIERI.items(), key=lambda x: -len(x[0])):
        fl = re.IGNORECASE if ab.islower() else 0

        def inlocuieste(m: re.Match[str], tot: str = tot, fl: int = fl) -> str:
            return tot[0].upper() + tot[1:] if fl and m.group(0)[0].isupper() else tot

        text = re.sub(r"(?<![\w.])" + re.escape(ab) + r"(?!\w)", inlocuieste, text, flags=fl)
    return text


def _dictionar(text: str, dictionar: dict[str, str]) -> str:
    for termen, pron in sorted(dictionar.items(), key=lambda x: -len(x[0])):
        text = re.sub(r"(?<![\w])" + re.escape(termen) + r"(?![\w])", pron, text, flags=re.IGNORECASE)
    return text


def normalizeaza(text: str, dictionar: dict[str, str] | None = None) -> str:
    """Textul gata de citit: fără cifre, fără simboluri, cu diacriticele corecte."""
    t = text.translate(SEDILA)
    t = _dictionar(t, dictionar or {})
    t = RE_WEB.sub(_web, t)
    t = RE_TELEFON.sub(_telefon, t)
    t = RE_DATA_SCURTA.sub(_data_scurta, t)
    t = RE_DATA_LUNGA.sub(_data_lunga, t)
    t = RE_ORA.sub(_ora, t)
    t = re.sub(r"(?<=[A-Za-zăâîșțĂÂÎȘȚ])(?=\d)", " ", t)  # „V60” -> „V 60”
    t = RE_SUMA_EURO_INAINTE.sub(lambda m: _suma_din(m.group("v"), "euro"), t)
    t = RE_SUMA.sub(_suma, t)
    t = RE_PROCENT.sub(_procent, t)
    t = RE_UNITATE.sub(_unitate, t)
    t = RE_ORDINAL.sub(_ordinal, t)
    t = _abrevieri(t)
    t = RE_INTERVAL.sub(" - ", t)
    t = RE_NUMAR.sub(_numar_liber, t)
    t = re.sub(r"(?<=\w) - (?=\w)", " până la ", t)
    for simbol, inlocuire in SIMBOLURI.items():
        t = t.replace(simbol, inlocuire)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def _suma_din(v: str, moneda: str) -> str:
    m = RE_SUMA.match(f"{v} {moneda}")
    return _suma(m) if m else v


def fara_cifre(text: str) -> bool:
    return not re.search(r"\d", text)
