"""Fotografiile reale pentru demonstrația A/B (F-editorial, decizia 8), din Wikimedia Commons.

Rulează DOAR în jobul `editorial` din CI (sau manual), niciodată din aplicație sau din testele obișnuite.
Pentru fiecare subiect (transmisia bicicletei, frâna, devizul de service) caută fișiere în spațiul de nume
File (`list=search`, `srnamespace=6`), citește `imageinfo` (url, extmetadata, mărime, mime, miniatura de
1080 px) și păstrează prima FOTOGRAFIE care are licență liberă (CC0, domeniu public, CC BY, CC BY-SA), e JPEG
și are cel puțin 800 px lățime. Fiecare subiect are o listă de căutări de rezervă. Scrie imaginile și
`LICENTE.json` (titlu, pagina, autorul, licența, sha256) în directorul dat.

    uv run python scripts/foto_test_commons.py rezultate/fotografii

Codul de ieșire: 0 dacă toate subiectele au fotografie, 1 altfel (ce s-a găsit rămâne scris).
"""

import argparse
import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

API = "https://commons.wikimedia.org/w/api.php"
UA = "AMA-test/1.0"  # generic, fără date personale
LATIME_MIN = 800
LATIME_DESCARCARE = 1080
REZULTATE_PE_CAUTARE = 12

# cheie -> căutări în ordine, fiecare cu subiectul scris pe activ (ce se vede, pentru `media.selectie`)
CAUTARI: dict[str, list[tuple[str, str]]] = {
    "transmisie": [
        ("bicycle chain cassette sprocket", "transmisie: lanț pe pinionul casetei"),
        ("bicycle chain sprocket close-up", "transmisie: lanț pe pinion"),
        ("bicycle drivetrain chain", "transmisie: lanțul bicicletei pe pinion"),
        ("bicycle rear derailleur chain", "transmisie: lanț pe pinionul din spate"),
    ],
    "frana": [
        ("bicycle disc brake caliper", "frâna bicicletei: etrierul pe discul roții"),
        ("bicycle brake caliper", "frâna bicicletei: etrierul pe roată"),
        ("bicycle rim brake", "frâna bicicletei pe roată"),
        ("bicycle brake", "frâna bicicletei"),
    ],
    "deviz": [
        ("bicycle repair invoice", "deviz de service pentru bicicletă, pe bancul de lucru"),
        ("repair shop invoice", "deviz de service scris, pe bancul de lucru"),
        ("job sheet workshop", "fișă de lucru de service, pe bancul de lucru"),
        ("bicycle mechanic workbench", "bancul de lucru al mecanicului de biciclete"),
        ("bicycle repair shop workbench", "bancul de lucru al mecanicului, în atelier"),
        ("bicycle workshop tools", "bancul de lucru al mecanicului, cu scule"),
    ],
}

_LIBERE = re.compile(r"^(cc0|public domain|pd\b.*|cc by(-sa)? \d(\.\d)?.*|cc by(-sa)?)$", re.I)
_INTERZISE = re.compile(r"\b(nc|nd|non-?commercial|no ?deriv)", re.I)


@dataclass(frozen=True)
class Candidat:
    titlu: str
    url_pagina: str
    url_fisier: str  # miniatura de 1080 px (sau originalul, dacă e mai mic)
    latime: int
    inaltime: int
    mime: str
    licenta: str
    url_licenta: str
    autor: str


def licenta_libera(nume: str) -> bool:
    """CC0, domeniu public, CC BY sau CC BY-SA (orice versiune); nimic cu NC sau ND."""
    n = " ".join(nume.strip().split())
    return bool(n) and not _INTERZISE.search(n) and bool(_LIBERE.match(n))


def _text(html_: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", html_ or "")).split())


def url_cautare(q: str) -> str:
    return API + "?" + urllib.parse.urlencode({
        "action": "query", "list": "search", "srsearch": q, "srnamespace": 6,
        "srlimit": REZULTATE_PE_CAUTARE, "format": "json", "formatversion": 2,
    })  # fmt: skip


def url_info(titluri: list[str]) -> str:
    return API + "?" + urllib.parse.urlencode({
        "action": "query", "titles": "|".join(titluri), "prop": "imageinfo",
        "iiprop": "url|extmetadata|size|mime", "iiurlwidth": LATIME_DESCARCARE, "format": "json",
        "formatversion": 2,
    })  # fmt: skip


def parseaza_cautare(r: dict[str, Any]) -> list[str]:
    """Titlurile fișierelor JPEG din răspunsul `list=search`, în ordinea relevanței."""
    out = []
    for x in (r.get("query") or {}).get("search") or []:
        t = str(x.get("title") or "")
        if t.startswith("File:") and t.lower().endswith((".jpg", ".jpeg")):
            out.append(t)
    return out


def parseaza_info(r: dict[str, Any], ordine: list[str] | None = None) -> list[Candidat]:
    """Candidații din `prop=imageinfo` (formatversion 1 sau 2), în ordinea `ordine` dacă e dată."""
    pagini = (r.get("query") or {}).get("pages") or []
    if isinstance(pagini, dict):
        pagini = list(pagini.values())
    out: dict[str, Candidat] = {}
    for p in pagini:
        info = (p.get("imageinfo") or [None])[0]
        if not info:
            continue
        meta = info.get("extmetadata") or {}

        def m(k: str, meta: dict[str, Any] = meta) -> str:
            return _text(str((meta.get(k) or {}).get("value") or ""))

        out[str(p.get("title"))] = Candidat(
            titlu=str(p.get("title")),
            url_pagina=str(info.get("descriptionurl") or ""),
            url_fisier=str(info.get("thumburl") or info.get("url") or ""),
            latime=int(info.get("width") or 0),
            inaltime=int(info.get("height") or 0),
            mime=str(info.get("mime") or ""),
            licenta=m("LicenseShortName"),
            url_licenta=m("LicenseUrl"),
            autor=m("Artist") or m("Credit") or "necunoscut",
        )
    chei = [t for t in (ordine or []) if t in out] + [t for t in out if t not in (ordine or [])]
    return [out[t] for t in chei]


def acceptat(c: Candidat) -> str:
    """Motivul refuzului sau „” dacă fotografia e bună."""
    if c.mime != "image/jpeg":
        return f"mime {c.mime}"
    if c.latime < LATIME_MIN:
        return f"lățime {c.latime} px"
    if not licenta_libera(c.licenta):
        return f"licență {c.licenta or 'necunoscută'}"
    if not c.url_fisier.startswith("https://"):
        return "fără URL de fișier"
    return ""


def _get(url: str, *, incercari: int = 3) -> bytes:
    if not url.startswith("https://"):
        raise ValueError(f"doar https: {url}")
    cerere = urllib.request.Request(url, headers={"User-Agent": UA})  # noqa: S310 (verificat mai sus)
    for k in range(incercari):
        try:
            with urllib.request.urlopen(cerere, timeout=60) as r:  # noqa: S310 (doar https, adresă fixă)
                return bytes(r.read())
        except OSError:
            if k == incercari - 1:
                raise
            time.sleep(2 * (k + 1))
    raise RuntimeError("inaccesibil")


def _json(url: str) -> dict[str, Any]:
    return dict(json.loads(_get(url)))


def descarca(director: Path) -> dict[str, dict[str, Any]]:
    director.mkdir(parents=True, exist_ok=True)
    licente: dict[str, dict[str, Any]] = {}
    for cheie, cautari in CAUTARI.items():
        for q, subiect in cautari:
            try:
                titluri = parseaza_cautare(_json(url_cautare(q)))
                candidati = parseaza_info(_json(url_info(titluri)), titluri) if titluri else []
            except OSError as e:
                print(f"{cheie}: „{q}”: {e}", file=sys.stderr)
                continue
            for c in candidati:
                motiv = acceptat(c)
                if motiv:
                    print(f"{cheie}: refuzat {c.titlu}: {motiv}", file=sys.stderr)
                    continue
                corp = _get(c.url_fisier)
                if not corp.startswith(b"\xff\xd8"):
                    print(f"{cheie}: refuzat {c.titlu}: nu e JPEG", file=sys.stderr)
                    continue
                fisier = f"{cheie}.jpg"
                (director / fisier).write_bytes(corp)
                licente[cheie] = {
                    "fisier": fisier, "subiect": subiect, "cautare": q, **asdict(c),
                    "sha256": hashlib.sha256(corp).hexdigest(), "sursa": "Wikimedia Commons",
                }  # fmt: skip
                print(f"{cheie}: {c.titlu} ({c.licenta}, {c.autor})")
                break
            if cheie in licente:
                break
        if cheie not in licente:
            print(f"{cheie}: nicio fotografie acceptată", file=sys.stderr)
    (director / "LICENTE.json").write_text(
        json.dumps(licente, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return licente


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("director", type=Path)
    a = p.parse_args(argv)
    gasite = descarca(a.director)
    return 0 if set(gasite) == set(CAUTARI) else 1


if __name__ == "__main__":
    raise SystemExit(main())
