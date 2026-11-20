"""Adaptorul Pixabay (F-idee, „Imagini reale”): foto și video cu cheie (`PIXABAY_API_KEY`, parametrul `key`).

# NEVERIFICAT: De verificat la migrare (API-ul real nu e accesibil din CI; testat doar pe JSON fictiv).

Licența Pixabay (Content License): uz gratuit, inclusiv comercial, fără atribuire obligatorie; interzise
revânzarea nemodificată și redistribuirea ca stock. Condițiile API-ului cer descărcarea fișierelor (fără
legături directe permanente) și indicarea sursei la afișarea rezultatelor; atribuirea se păstrează pe activ.
Cheia stă în URL: adresa de căutare nu se scrie în jurnale.
"""

import json
import os
import urllib.parse
from typing import Any

from app.media.furnizori import RezultatStock
from app.media.stock_commons import DURATA_MAX, DURATA_MIN, Http, ca_jpeg, http_get, transcodeaza_vertical

API_FOTO = "https://pixabay.com/api/"
API_VIDEO = "https://pixabay.com/api/videos/"
LICENTA = (
    "Pixabay Content License (https://pixabay.com/service/license-summary/): uz gratuit, inclusiv comercial, "
    "modificare permisă, atribuire neobligatorie; interzise revânzarea sau distribuirea nemodificată și "
    "sugerarea aprobării de către persoanele sau mărcile din imagine."
)


def alege_varianta_video(variante: dict[str, Any]) -> dict[str, Any] | None:
    """Varianta potrivită: cea mai mică dintre cele cu latura scurtă ≥ 1080 px, altfel cea mai mare."""
    bune = [
        v for v in variante.values() if isinstance(v, dict) and str(v.get("url") or "").startswith("https://")
    ]
    if not bune:
        return None

    def latura(v: dict[str, Any]) -> int:
        return min(int(v.get("width") or 0), int(v.get("height") or 0))

    hd = [v for v in bune if latura(v) >= 1080]
    return min(hd, key=latura) if hd else max(bune, key=latura)


def parseaza_foto(r: dict[str, Any]) -> list[RezultatStock]:
    out = []
    for h in r.get("hits") or []:
        url_fisier = str(h.get("largeImageURL") or h.get("webformatURL") or "")
        if not url_fisier.startswith("https://") or int(h.get("imageWidth") or 0) < 800:
            continue
        autor = str(h.get("user") or "necunoscut")
        out.append(
            RezultatStock(
                furnizor="pixabay",
                identificator=f"foto-{h.get('id')}",
                autor=autor,
                url=str(h.get("pageURL") or ""),
                tip="foto",
                licenta_text=f"Imagine de {autor} de pe Pixabay ({h.get('pageURL')}). {LICENTA}",
                descriere=str(h.get("tags") or "")[:300],
                url_fisier=url_fisier,
                licenta="Pixabay Content License",
                url_licenta="https://pixabay.com/service/license-summary/",
            )
        )
    return out


def parseaza_video(r: dict[str, Any]) -> list[RezultatStock]:
    out = []
    for h in r.get("hits") or []:
        v = alege_varianta_video(h.get("videos") or {})
        if v is None or not DURATA_MIN <= float(h.get("duration") or 0) <= DURATA_MAX:
            continue
        autor = str(h.get("user") or "necunoscut")
        out.append(
            RezultatStock(
                furnizor="pixabay",
                identificator=f"video-{h.get('id')}",
                autor=autor,
                url=str(h.get("pageURL") or ""),
                tip="video",
                licenta_text=f"Video de {autor} de pe Pixabay ({h.get('pageURL')}). {LICENTA}",
                descriere=str(h.get("tags") or "")[:300],
                url_fisier=str(v["url"]),
                licenta="Pixabay Content License",
                url_licenta="https://pixabay.com/service/license-summary/",
            )
        )
    return out


class StockPixabay:
    """# NEVERIFICAT: De verificat la migrare. Implementează `FurnizorStock`."""

    nume = "pixabay"

    def __init__(self, cheie: str | None = None, http: Http | None = None) -> None:
        self._cheie = (cheie if cheie is not None else os.environ.get("PIXABAY_API_KEY", "")).strip()
        if not self._cheie:
            raise ValueError("lipsește PIXABAY_API_KEY")
        self._http: Http = http or http_get

    def cauta(self, interogare: str, *, tip: str = "foto", n: int = 3) -> list[RezultatStock]:
        p: dict[str, Any] = {"key": self._cheie, "q": interogare[:100], "safesearch": "true",
                             "per_page": max(3, min(200, n * 3))}  # fmt: skip
        if tip == "video":
            baza = API_VIDEO
        else:
            baza, p["image_type"], p["orientation"] = API_FOTO, "photo", "vertical"
        r = json.loads(self._http(f"{baza}?{urllib.parse.urlencode(p)}", {"Accept": "application/json"}))
        return (parseaza_video(r) if tip == "video" else parseaza_foto(r))[:n]

    def descarca(self, r: RezultatStock) -> bytes:
        corp = self._http(r.url_fisier, {})
        return transcodeaza_vertical(corp, sufix=".mp4") if r.tip == "video" else ca_jpeg(corp)
