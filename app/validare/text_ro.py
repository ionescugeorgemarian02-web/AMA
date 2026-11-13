"""Unelte pure pentru text românesc, comune validatorilor (F5.2+): tokenizare, curățarea textului de ce nu e
limbă
(adrese, hashtag-uri), detecția limbii, găsirea și verificarea linkurilor. Fără bază de date, fără model,
fără rețea."""

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.validare.date_validare import incarca

DIACRITICE = "ăâîșțĂÂÎȘȚ"
SEDILA = "şţŞŢ"
CUVANT = re.compile(r"[^\W\d_]+", re.UNICODE)
URL = re.compile(r"(?:https?://|www\.)[^\s<>\"“”«»]+", re.IGNORECASE)
URL_STRICAT = re.compile(
    r"\b(?:https?:/(?!/)[^\s<>\"]+|https?//[^\s<>\"]+|h?tps?://[^\s<>\"]+|https?:///[^\s<>\"]*|https?://(?=\s|$))",
    re.IGNORECASE,
)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
HASHTAG = re.compile(r"[#@][\w]+", re.UNICODE)
ETICHETA_HOST = re.compile(r"^(?!-)[^\W_](?:[\w-]{0,61}[^\W_])?$", re.UNICODE)
FINAL_LINK = ".,;:!?)]}»”'’…"


def fara_diacritice(text: str) -> str:
    """Litera de bază: ă → a, ș → s, ț → t (și formele cu sedilă)."""
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


def fara_adrese(text: str) -> str:
    """Textul fără linkuri, adrese de email, hashtag-uri și @mențiuni (ele nu sunt limbă)."""
    for sablon in (URL, URL_STRICAT, EMAIL, HASHTAG):
        text = sablon.sub(" ", text)
    return text


def cuvinte(text: str, *, fara_adrese_: bool = True) -> list[str]:
    """Cuvintele (litere, inclusiv cu diacritice); cratima desparte (într-o → într, o)."""
    return CUVANT.findall(fara_adrese(text) if fara_adrese_ else text)


@dataclass(frozen=True)
class Limba:
    cod: str  # „ro”, „en” sau „necunoscuta”
    cuvinte: int
    raport_ro: float
    raport_en: float


def detecteaza_limba(text: str) -> Limba:
    """Limba probabilă, după raportul cuvintelor funcționale (determinist, fără model). Sub
    `cuvinte_minim_limba` cuvinte nu se judecă (`cod="prea_scurt"`)."""
    d = incarca("limba")["detectie_limba"]
    ro, en = frozenset(d["romana"]), frozenset(d["engleza"])
    minim = int(incarca("structura")["generale"]["cuvinte_minim_limba"])
    c = [fara_diacritice(x).lower() for x in cuvinte(text)]
    n = len(c)
    if n < minim:
        return Limba("prea_scurt", n, 0.0, 0.0)
    r_ro = sum(1 for x in c if x in ro) / n
    r_en = sum(1 for x in c if x in en) / n
    if r_en >= d["prag_engleza"] and r_en > r_ro:
        return Limba("en", n, r_ro, r_en)
    if r_ro < d["prag_romana_minim"]:
        return Limba("necunoscuta", n, r_ro, r_en)
    return Limba("ro", n, r_ro, r_en)


# --- linkuri
# ------------------------------------------------------------------------------------------------------


def linkuri_in_text(text: str) -> list[str]:
    """Candidații de link din text, fără punctuația de la sfârșit (http(s)://… și www.…)."""
    gasite = [m.group(0).rstrip(FINAL_LINK) for m in URL.finditer(text)]
    return [g for g in gasite if g]


def linkuri_stricate_in_text(text: str) -> list[str]:
    """Ce arată a link, dar are schema greșită (`http:/x.ro`, `https//x.ro`, `htps://x.ro`,
    `https://`)."""
    return [m.group(0).rstrip(FINAL_LINK) or m.group(0) for m in URL_STRICAT.finditer(text)]


def motiv_link_invalid(link: str) -> str | None:
    """`None` dacă linkul e bine format (schemă http(s), gazdă cu cel puțin două etichete și o extensie
    literală,
    port numeric); altfel motivul. NU se face nicio cerere în rețea."""
    candidat = link.strip()
    if re.search(r"\s", candidat):
        return "conține spații"
    if candidat.lower().startswith("www."):
        candidat = "https://" + candidat
    try:
        p = urlsplit(candidat)
        gazda, port = p.hostname, p.port
    except ValueError:
        return "adresă ilizibilă"
    if p.scheme.lower() not in ("http", "https"):
        return "schema trebuie să fie http sau https"
    if not gazda:
        return "lipsește domeniul"
    etichete = gazda.split(".")
    if len(etichete) < 2 or not all(ETICHETA_HOST.match(e) for e in etichete):
        return "domeniu invalid"
    if not re.fullmatch(r"[^\W\d_]{2,24}|xn--[a-z0-9-]{2,20}", etichete[-1], re.UNICODE):
        return "extensia domeniului este invalidă"
    if port is not None and not 1 <= port <= 65535:
        return "port invalid"
    if p.username or p.password:
        return "linkul nu are voie să conțină utilizator și parolă"
    return None
