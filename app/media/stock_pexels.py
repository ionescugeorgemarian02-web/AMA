"""Adaptorul Pexels (F-idee, „Imagini reale”): foto și video, cu cheia `PEXELS_API_KEY`.

# NEVERIFICAT: De verificat la migrare (API-ul real nu e accesibil din CI; testat doar pe JSON fictiv).

Licența Pexels: uz gratuit, inclusiv comercial, fără atribuire obligatorie; condițiile cer
totuși menționarea sursei („Photo/Video by <autor> on Pexels”) unde se poate și interzic
revânzarea fișierului ca atare. Atribuirea se păstrează oricum pe activ. Se preferă fișierele
verticale (orientation=portrait) și HD; clipurile se transcodează local la 1080×1920 H.264,
fără sunet, ≤ 15 s.
"""

import json
import os
import urllib.parse
from collections.abc import Mapping
from typing import Any

from app.media.furnizori import RezultatStock
from app.media.stock_commons import DURATA_MAX, DURATA_MIN, Http, ca_jpeg, http_get, transcodeaza_vertical

API_FOTO = "https://api.pexels.com/v1/search"
API_VIDEO = "https://api.pexels.com/videos/search"
LICENTA = (
    "Licența Pexels (https://www.pexels.com/license/): uz gratuit, inclusiv comercial, modificare permisă, "
    "atribuire neobligatorie dar recomandată; interzise revânzarea fișierului nemodificat, sugerarea "
    "aprobării de către persoanele sau mărcile din imagine și redistribuirea ca serviciu de stock."
)


def alege_fisier_video(fisiere: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Fișierul mp4 cel mai potrivit: vertical înaintea orizontalului, apoi cel mai apropiat de 1080 px lățime
    (fără să depășească inutil 4K)."""
    mp4 = [f for f in fisiere if str(f.get("file_type") or "") == "video/mp4" and f.get("link")]
    if not mp4:
        return None

    def scor(f: dict[str, Any]) -> tuple[int, int]:
        w, h = int(f.get("width") or 0), int(f.get("height") or 0)
        return (0 if h > w else 1, abs(min(w, h) - 1080))

    return min(mp4, key=scor)


def parseaza_foto(r: dict[str, Any]) -> list[RezultatStock]:
    out = []
    for p in r.get("photos") or []:
        src = p.get("src") or {}
        url_fisier = str(src.get("large2x") or src.get("portrait") or src.get("original") or "")
        if not url_fisier.startswith("https://") or int(p.get("width") or 0) < 800:
            continue
        autor = str(p.get("photographer") or "necunoscut")
        out.append(
            RezultatStock(
                furnizor="pexels",
                identificator=f"foto-{p.get('id')}",
                autor=autor,
                url=str(p.get("url") or ""),
                tip="foto",
                licenta_text=f"Photo by {autor} on Pexels ({p.get('url')}). {LICENTA}",
                descriere=str(p.get("alt") or "")[:300],
                url_fisier=url_fisier,
                licenta="Pexels License",
                url_licenta="https://www.pexels.com/license/",
            )
        )
    return out


def parseaza_video(r: dict[str, Any]) -> list[RezultatStock]:
    out = []
    for v in r.get("videos") or []:
        durata = float(v.get("duration") or 0)
        f = alege_fisier_video(v.get("video_files") or [])
        if f is None or not DURATA_MIN <= durata <= DURATA_MAX or not str(f["link"]).startswith("https://"):
            continue
        autor = str((v.get("user") or {}).get("name") or "necunoscut")
        out.append(
            RezultatStock(
                furnizor="pexels",
                identificator=f"video-{v.get('id')}",
                autor=autor,
                url=str(v.get("url") or ""),
                tip="video",
                licenta_text=f"Video by {autor} on Pexels ({v.get('url')}). {LICENTA}",
                descriere=str(v.get("url") or "").rstrip("/").rsplit("/", 1)[-1][:300],
                url_fisier=str(f["link"]),
                licenta="Pexels License",
                url_licenta="https://www.pexels.com/license/",
            )
        )
    return out


class StockPexels:
    """# NEVERIFICAT: De verificat la migrare. Implementează `FurnizorStock`."""

    nume = "pexels"

    def __init__(self, cheie: str | None = None, http: Http | None = None) -> None:
        self._cheie = (cheie if cheie is not None else os.environ.get("PEXELS_API_KEY", "")).strip()
        if not self._cheie:
            raise ValueError("lipsește PEXELS_API_KEY")
        self._http: Http = http or http_get

    def _antete(self) -> Mapping[str, str]:
        return {"Authorization": self._cheie, "Accept": "application/json"}

    def cauta(self, interogare: str, *, tip: str = "foto", n: int = 3) -> list[RezultatStock]:
        baza = API_VIDEO if tip == "video" else API_FOTO
        p: dict[str, Any] = {
            "query": interogare,
            "orientation": "portrait",
            "per_page": max(5, min(80, n * 3)),
        }
        if tip == "video":
            p["size"] = "medium"
        q = urllib.parse.urlencode(p)
        r = json.loads(self._http(f"{baza}?{q}", self._antete()))
        return (parseaza_video(r) if tip == "video" else parseaza_foto(r))[:n]

    def descarca(self, r: RezultatStock) -> bytes:
        corp = self._http(r.url_fisier, {})
        return transcodeaza_vertical(corp, sufix=".mp4") if r.tip == "video" else ca_jpeg(corp)
