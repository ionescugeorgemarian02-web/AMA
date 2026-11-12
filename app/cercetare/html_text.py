"""Extragerea textului dintr-un HTML (F4.2): titlu, text principal, linkuri, directive `robots` din pagină.

Alegere: parserul din biblioteca standard (`html.parser`), fără dependență nouă. Nu are nevoie de arbore
(construim textul într-o singură trecere), tolerează HTML stricat și nu execută nimic. Prețul: fără
euristici „readability”; compensăm cu regula simplă „dacă există `<main>` sau `<article>` cu suficient text,
doar el; altfel tot corpul fără navigație, subsol, formulare și scripturi”.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser

SARITE = frozenset(
    {"script", "style", "noscript", "template", "svg", "iframe", "nav", "footer", "aside", "form", "select",
     "button", "head", "object", "embed", "canvas", "dialog", "menu"}
)  # fmt: skip
BLOC = frozenset(
    {"p", "div", "section", "article", "main", "header", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol",
     "table", "tr", "br", "blockquote", "pre", "figure", "figcaption", "dd", "dt", "dl", "hr", "address",
     "details", "summary"}
)  # fmt: skip
SINGURATICE = frozenset(
    {"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "embed", "source", "track", "wbr"}
)
TEXT_MAXIM = 400_000
MAIN_MINIM = 200  # caractere: sub atât, `<main>` nu e considerat conținut principal


@dataclass
class Pagina:
    titlu: str = ""
    descriere: str = ""
    text: str = ""
    linkuri: list[str] = field(default_factory=list)
    canonic: str = ""
    noindex: bool = False
    nofollow: bool = False
    limba: str = ""


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pagina = Pagina()
        self._adancime_sarita = 0
        self._stiva: list[tuple[str, bool]] = []  # (tag, a incrementat contorul de săritură)
        self._in_titlu = False
        self._titlu: list[str] = []
        self._general: list[str] = []
        self._principal: list[str] = []
        self._in_principal = 0

    def _ascuns(self, atribute: dict[str, str | None]) -> bool:
        return "hidden" in atribute or (atribute.get("aria-hidden") or "").lower() == "true"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "html" and a.get("lang"):
            self.pagina.limba = (a["lang"] or "")[:10].lower()
        if tag == "title":
            self._in_titlu = True
        if tag == "meta":
            nume = (a.get("name") or "").lower()
            continut = a.get("content") or ""
            if nume == "description" and not self.pagina.descriere:
                self.pagina.descriere = continut.strip()[:500]
            elif nume in ("robots", "googlebot"):
                directive = {d.strip().lower() for d in continut.split(",")}
                self.pagina.noindex = self.pagina.noindex or "noindex" in directive or "none" in directive
                self.pagina.nofollow = self.pagina.nofollow or "nofollow" in directive or "none" in directive
        elif tag == "link" and (a.get("rel") or "").lower() == "canonical" and a.get("href"):
            self.pagina.canonic = (a["href"] or "").strip()
        elif tag == "a" and a.get("href") and "nofollow" not in (a.get("rel") or "").lower():
            self.pagina.linkuri.append(a["href"] or "")
        if tag in SINGURATICE:
            if tag in BLOC and not self._adancime_sarita:
                self._spatiu("\n")
            return
        sarit = tag in SARITE or self._ascuns(a)
        if sarit:
            self._adancime_sarita += 1
        self._stiva.append((tag, sarit))
        if tag in ("main", "article") and not self._adancime_sarita:
            self._in_principal += 1
        if tag in BLOC and not self._adancime_sarita:
            self._spatiu("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in SINGURATICE:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_titlu = False
        for i in range(len(self._stiva) - 1, -1, -1):  # HTML stricat: închide până la tagul potrivit
            if self._stiva[i][0] == tag:
                for _t, sarit in reversed(self._stiva[i:]):
                    if sarit:
                        self._adancime_sarita -= 1
                del self._stiva[i:]
                break
        else:
            return
        if tag in ("main", "article") and self._in_principal and not self._adancime_sarita:
            self._in_principal -= 1
        if tag in BLOC and not self._adancime_sarita:
            self._spatiu("\n")

    def _spatiu(self, s: str) -> None:
        self._general.append(s)
        if self._in_principal:
            self._principal.append(s)

    def handle_data(self, data: str) -> None:
        if self._in_titlu:
            self._titlu.append(data)
            return
        if self._adancime_sarita:
            return
        self._general.append(data)
        if self._in_principal:
            self._principal.append(data)


def _curata(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\xa0", " ")
    text = re.sub(r"[​-‏⁠﻿‪-‮]", "", text)
    text = re.sub(r"[^\S\n]+", " ", text)
    linii = [linie.strip() for linie in text.split("\n")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(linii))
    return text.strip()


def extrage(html: str) -> Pagina:
    e = _Extractor()
    try:
        e.feed(html[:3_000_000])
        e.close()
    except Exception:  # noqa: S110 - HTML grav stricat: păstrăm ce s-a extras până acolo
        pass
    p = e.pagina
    p.titlu = _curata(" ".join(e._titlu)).replace("\n", " ")[:300]
    principal = _curata("".join(e._principal))
    p.text = (principal if len(principal) >= MAIN_MINIM else _curata("".join(e._general)))[:TEXT_MAXIM]
    return p


def decodeaza(corp: bytes, content_type: str = "") -> str:
    """Octeți → text. Setul de caractere din antet, apoi din `<meta charset>`, apoi UTF-8; caracterele
    nevalide se înlocuiesc. Cuprinde și paginile vechi românești (ISO-8859-2, windows-1250)."""
    m = re.search(r"charset=([\w-]+)", content_type, re.IGNORECASE)
    nume = m.group(1) if m else None
    if nume is None:
        m2 = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", corp[:4096], re.IGNORECASE)
        nume = m2.group(1).decode("ascii", "ignore") if m2 else "utf-8"
    try:
        return corp.decode(nume, errors="replace")
    except LookupError:
        return corp.decode("utf-8", errors="replace")
