"""Stock real fără cheie din Wikimedia Commons (F-idee, „Imagini reale”): foto și video, cu atribuire.

Căutare în spațiul de nume File (`list=search`, `srnamespace=6`), apoi `prop=imageinfo` (url,
extmetadata, mărime, mime, metadate pentru durată; miniatura de 1080 px pentru foto). Licențe acceptate:
CC0, domeniu public, CC BY, CC BY-SA (orice versiune); refuzate NC, ND, „fair use” și licențele
necunoscute.

- Foto: JPEG sau PNG cu lățimea ≥ 800 px; se descarcă miniatura de 1080 px și se salvează ca JPEG.
- Video: webm / ogv (sau mp4), durata ≥ 3 s și ≤ 60 s când se poate citi; originalul se transcodează local cu
  ffmpeg la MP4 H.264 vertical 1080×1920, fără sunet, cel mult 15 s (decupare centrată; scalare cu fundal
  estompat doar pentru cadre panoramice, unde decuparea ar pierde subiectul).

Rețeaua: doar https, User-Agent generic, limită de timp, cereri seriale (cel puțin 1 s între ele) și
reîncercări; la limitarea de rată (429/503) se respectă `Retry-After`. Testele injectează `http`.
"""

import html
import io
import json
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from app.media import ffmpeg
from app.media.furnizori import RezultatStock

API = "https://commons.wikimedia.org/w/api.php"
UA = "AMA/1.0 (test)"  # generic, fără date personale
LATIME_MIN_FOTO = 800
LATIME_DESCARCARE = 1080
INALTIME_MIN_VIDEO = 360
DURATA_MIN = 3.0
DURATA_MAX = 60.0
DURATA_CLIP = 15.0
OCTETI_MAX = 200 * 1024 * 1024
RAPORT_PANORAMIC = 2.0  # peste 2:1 decuparea centrată ar păstra prea puțin: scalare + fundal estompat

MIME_FOTO = ("image/jpeg", "image/png")
MIME_VIDEO = ("video/webm", "application/ogg", "video/ogg", "video/mp4")

_LIBERE = re.compile(r"^(cc0( 1\.0)?|public domain.*|pd\b.*|cc[ -]by(-sa)?([ -]\d(\.\d)?)?.*)$", re.I)
_INTERZISE = re.compile(r"\b(nc|nd|non-?commercial|no ?deriv\w*|fair ?use)\b", re.I)

Http = Callable[[str, Mapping[str, str]], bytes]


def licenta_libera(nume: str) -> bool:
    """CC0, domeniu public, CC BY sau CC BY-SA; nimic cu NC, ND sau „fair use”."""
    n = " ".join((nume or "").strip().split())
    return bool(n) and not _INTERZISE.search(n) and bool(_LIBERE.match(n))


def _text(html_: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", html_ or "")).split())


@dataclass(frozen=True)
class Fisier:
    titlu: str
    url_pagina: str
    url_original: str
    url_miniatura: str
    latime: int
    inaltime: int
    mime: str
    licenta: str
    url_licenta: str
    autor: str
    durata: float | None  # secunde, pentru video, dacă metadatele o dau
    descriere: str


def url_cautare(q: str, tip: str, n: int) -> str:
    filtru = "filetype:video" if tip == "video" else "filetype:bitmap"
    return API + "?" + urllib.parse.urlencode({
        "action": "query", "list": "search", "srsearch": f"{q} {filtru}", "srnamespace": 6,
        "srlimit": max(10, min(50, n * 6)), "format": "json", "formatversion": 2,
    })  # fmt: skip


def url_info(titluri: list[str], tip: str) -> str:
    p: dict[str, Any] = {
        "action": "query", "titles": "|".join(titluri), "prop": "imageinfo",
        "iiprop": "url|extmetadata|size|mime" + ("|metadata" if tip == "video" else ""),
        "format": "json", "formatversion": 2,
    }  # fmt: skip
    if tip == "foto":
        p["iiurlwidth"] = LATIME_DESCARCARE
    return API + "?" + urllib.parse.urlencode(p)


def parseaza_cautare(r: dict[str, Any]) -> list[str]:
    """Titlurile fișierelor din răspunsul `list=search`, în ordinea relevanței."""
    return [
        str(x.get("title"))
        for x in (r.get("query") or {}).get("search") or []
        if str(x.get("title") or "").startswith("File:")
    ]


def _durata(info: dict[str, Any]) -> float | None:
    for m in info.get("metadata") or []:
        if isinstance(m, dict) and m.get("name") in ("length", "playtime_seconds", "duration"):
            try:
                return float(m.get("value") or 0) or None
            except (TypeError, ValueError):
                return None
    return None


def parseaza_info(r: dict[str, Any], ordine: list[str] | None = None) -> list[Fisier]:
    """Fișierele din `prop=imageinfo` (formatversion 1 sau 2), în ordinea `ordine` dacă e dată."""
    pagini = (r.get("query") or {}).get("pages") or []
    if isinstance(pagini, dict):
        pagini = list(pagini.values())
    out: dict[str, Fisier] = {}
    for p in pagini:
        info = (p.get("imageinfo") or [None])[0]
        if not info:
            continue
        meta = info.get("extmetadata") or {}

        def m(k: str, meta: dict[str, Any] = meta) -> str:
            return _text(str((meta.get(k) or {}).get("value") or ""))

        titlu = str(p.get("title"))
        out[titlu] = Fisier(
            titlu=titlu,
            url_pagina=str(info.get("descriptionurl") or ""),
            url_original=str(info.get("url") or ""),
            url_miniatura=str(info.get("thumburl") or info.get("url") or ""),
            latime=int(info.get("width") or 0),
            inaltime=int(info.get("height") or 0),
            mime=str(info.get("mime") or ""),
            licenta=m("LicenseShortName"),
            url_licenta=m("LicenseUrl"),
            autor=m("Artist") or m("Credit") or "necunoscut",
            durata=_durata(info),
            descriere=(m("ImageDescription") or m("ObjectName") or titlu.removeprefix("File:"))[:300],
        )
    chei = [t for t in (ordine or []) if t in out] + [t for t in out if t not in (ordine or [])]
    return [out[t] for t in chei]


def motiv_refuz(f: Fisier, tip: str) -> str:
    """Motivul refuzului sau „” dacă fișierul e bun pentru tipul cerut."""
    if not licenta_libera(f.licenta):
        return f"licență {f.licenta or 'necunoscută'}"
    if tip == "video":
        if f.mime not in MIME_VIDEO:
            return f"mime {f.mime}"
        if f.inaltime and f.inaltime < INALTIME_MIN_VIDEO:
            return f"înălțime {f.inaltime} px"
        if f.durata is not None and not DURATA_MIN <= f.durata <= DURATA_MAX:
            return f"durată {f.durata:.1f} s"
        url = f.url_original
    else:
        if f.mime not in MIME_FOTO:
            return f"mime {f.mime}"
        if f.latime < LATIME_MIN_FOTO:
            return f"lățime {f.latime} px"
        url = f.url_miniatura
    if not url.startswith("https://"):
        return "fără URL https de fișier"
    return ""


def text_atribuire(f: Fisier) -> str:
    """Atribuirea cerută de CC BY / BY-SA (titlu, autor, sursă, licență), salvată ca copie a licenței."""
    lic = f.licenta + (f" ({f.url_licenta})" if f.url_licenta else "")
    return (
        f"„{f.titlu.removeprefix('File:')}” de {f.autor}, Wikimedia Commons, {f.url_pagina}. Licență: {lic}. "
        "Atribuirea autorului și a licenței este obligatorie la fiecare utilizare (exceptând CC0 / domeniu "
        "public); lucrările derivate sub CC BY-SA păstrează aceeași licență."
    )


def rezultat(f: Fisier, tip: str, furnizor: str = "wikimedia-commons") -> RezultatStock:
    return RezultatStock(
        furnizor=furnizor,
        identificator=f.titlu,
        autor=f.autor,
        url=f.url_pagina,
        tip=tip,
        licenta_text=text_atribuire(f),
        descriere=f.descriere,
        url_fisier=f.url_original if tip == "video" else f.url_miniatura,
        licenta=f.licenta,
        url_licenta=f.url_licenta,
    )


# --- transcodarea locală (comună adaptoarelor de stock)


def filtru_vertical(latime: int, inaltime: int) -> tuple[str, str]:
    """(opțiune, filtru) ffmpeg pentru 1080×1920: decupare centrată; la panoramice, fundal estompat."""
    if latime and inaltime and latime / inaltime > RAPORT_PANORAMIC:
        return "-filter_complex", (
            "[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            "boxblur=20:2[fundal];[b]scale=1080:-2[prim];[fundal][prim]overlay=(W-w)/2:(H-h)/2,"
            "fps=30,setsar=1,format=yuv420p[v]"
        )
    return "-vf", ("crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',scale=1080:1920,fps=30,setsar=1,format=yuv420p")


def comanda_transcodare(intrare: str, iesire: str, *, latime: int, inaltime: int) -> list[str]:
    optiune, filtru = filtru_vertical(latime, inaltime)
    harta = ["-map", "[v]"] if optiune == "-filter_complex" else []
    return [
        "-i", intrare, "-t", f"{DURATA_CLIP:g}", optiune, filtru, *harta,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-profile:v", "high", "-an",
        "-movflags", "+faststart", iesire,
    ]  # fmt: skip


def transcodeaza_vertical(corp: bytes, *, sufix: str = ".webm") -> bytes:
    """Orice clip → MP4 H.264 1080×1920, fără sunet, ≤ 15 s. Refuză clipurile sub 3 s."""
    with tempfile.TemporaryDirectory() as d:
        intrare, iesire = Path(d) / f"sursa{sufix}", Path(d) / "vertical.mp4"
        intrare.write_bytes(corp)
        info = ffmpeg.probe(intrare)
        video = next((s for s in info.get("streams") or [] if s.get("codec_type") == "video"), None)
        if video is None:
            raise ValueError("fișierul nu are pistă video")
        try:
            durata = float((info.get("format") or {}).get("duration") or 0)
        except ValueError:
            durata = 0.0
        if durata and durata < DURATA_MIN:
            raise ValueError(f"clip prea scurt ({durata:.1f} s)")
        latime, inaltime = int(video.get("width") or 0), int(video.get("height") or 0)
        ffmpeg.ruleaza(
            comanda_transcodare(str(intrare), str(iesire), latime=latime, inaltime=inaltime), fir=2
        )
        return iesire.read_bytes()


def ca_jpeg(corp: bytes) -> bytes:
    with Image.open(io.BytesIO(corp)) as img:
        out = io.BytesIO()
        img.convert("RGB").save(out, "JPEG", quality=90)
        return out.getvalue()


# --- rețeaua


STATUS_LIMITARE = (429, 503)  # limitare de rată / suprasolicitare: se reîncearcă după `Retry-After`
INCERCARI_LIMITARE = 6
ASTEPTARE_MAX = 60.0  # o singură pauză nu trece de un minut, oricât cere serverul
PAUZA_MIN = (
    1.0  # cereri seriale, rare: eticheta API-ului Wikimedia (o rafală de pe IP-ul CI-ului primește 429)
)
_ultima_cerere = 0.0


def _asteptare_limitare(eroare: urllib.error.HTTPError, k: int) -> float:
    """Pauza după un 429/503: `Retry-After` (în secunde) dacă e dat, altfel exponențial (2, 4, 8, … s)."""
    try:
        cerut = float(eroare.headers.get("Retry-After") or "")
    except (TypeError, ValueError):
        cerut = 2.0 * 2**k
    return min(ASTEPTARE_MAX, max(1.0, cerut))


def http_get(
    url: str,
    antete: Mapping[str, str],
    *,
    incercari: int = 3,
    timp: float = 30.0,
    dormi: Callable[[float], None] = time.sleep,
) -> bytes:
    """GET https cu reîncercări. Erorile de rețea și 5xx: `incercari` încercări. Limitarea de rată (429,
    503): până la `INCERCARI_LIMITARE`, cu pauza cerută de server (`Retry-After`) sau exponențială.
    Alte 4xx: imediat."""
    global _ultima_cerere
    if not url.startswith("https://"):
        raise ValueError("doar https")
    cerere = urllib.request.Request(url, headers={"User-Agent": UA, **antete})  # noqa: S310 (doar https)
    k = 0
    while True:
        if (rest := PAUZA_MIN - (time.monotonic() - _ultima_cerere)) > 0:
            dormi(rest)
        _ultima_cerere = time.monotonic()
        try:
            with urllib.request.urlopen(cerere, timeout=timp) as r:  # noqa: S310 (doar https)
                corp = bytes(r.read(OCTETI_MAX + 1))
            if len(corp) > OCTETI_MAX:
                raise ValueError("fișier prea mare")
            return corp
        except urllib.error.HTTPError as e:
            limitare = e.code in STATUS_LIMITARE
            if (not limitare and e.code < 500) or k >= (INCERCARI_LIMITARE if limitare else incercari) - 1:
                raise
            dormi(_asteptare_limitare(e, k) if limitare else 1.5 * (k + 1))
        except OSError:
            if k >= incercari - 1:
                raise
            dormi(1.5 * (k + 1))
        k += 1


class StockCommons:
    """Wikimedia Commons, fără cheie. Implementează `FurnizorStock`."""

    nume = "wikimedia-commons"

    def __init__(self, http: Http | None = None) -> None:
        self._http: Http = http or http_get
        self.refuzate: list[tuple[str, str]] = []  # (titlu, motiv), pentru raport

    def _json(self, url: str) -> dict[str, Any]:
        return dict(json.loads(self._http(url, {"Accept": "application/json"})))

    def cauta(self, interogare: str, *, tip: str = "foto", n: int = 3) -> list[RezultatStock]:
        if tip not in ("foto", "video"):
            raise ValueError(f"tip necunoscut: {tip}")
        titluri = parseaza_cautare(self._json(url_cautare(interogare, tip, n)))
        if not titluri:
            return []
        out: list[RezultatStock] = []
        for f in parseaza_info(self._json(url_info(titluri[:50], tip)), titluri):
            motiv = motiv_refuz(f, tip)
            if motiv:
                self.refuzate.append((f.titlu, motiv))
                continue
            out.append(rezultat(f, tip, self.nume))
            if len(out) >= n:
                break
        return out

    def descarca(self, r: RezultatStock) -> bytes:
        corp = self._http(r.url_fisier, {})
        if r.tip == "video":
            sufix = Path(urllib.parse.urlparse(r.url_fisier).path).suffix or ".webm"
            return transcodeaza_vertical(corp, sufix=sufix)
        return ca_jpeg(corp)
