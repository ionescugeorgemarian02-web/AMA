"""Cititorul de metrici YouTube (F10.1): `videos.list?part=statistics` (Data API v3).

- Dă vizualizări, aprecieri și comentarii. Timpul de vizionare și curba de retenție vin din YouTube
  Analytics API (F10.2), nu de aici.
- Fiecare citire costă unități din cota zilnică a proiectului (aceeași evidență ca la publicare, F9.4):
  cota epuizată = `EroareTemporara` (se reîncearcă la următoarea rulare).
- Clipul șters sau privat pentru cont = lista `items` goală → `EroareDefinitiva`.

Curba de retenție (F10.2, `CititorRetentieYoutube`): YouTube Analytics API, `GET /v2/reports` cu
`dimensions=elapsedVideoTimeRatio` și `metrics=audienceWatchRatio`, filtrat pe clip: 100 de puncte (docs/02).
Cere permisiunea `yt-analytics.readonly` la autorizarea contului; fără ea, platforma răspunde 403
(`EroareDefinitiva`) și curba lipsește, restul metricilor rămân.

# NEVERIFICAT: costul real în unități al `videos.list` (1 [I]) și cifrele pe un clip real; forma răspunsului
Analytics și întârzierea datelor (de regulă 2–3 zile) pe un canal real; testat pe API simulat (contract HTTP
local).
"""

import datetime as dt
import uuid
from collections.abc import Callable

import httpx

from app.config import get_settings
from app.connectors.contract import Metrici
from app.connectors.publicare.baza import ClientHttp, DepozitBaza, DepozitTokenuri, token_sau_autentificare
from app.connectors.publicare.youtube import API, Contor, ContorBaza, costuri, zi_pacific
from app.operare.motor import EroareDefinitiva, EroareTemporara

ANALYTICS = "https://youtubeanalytics.googleapis.com"
SCOP_ANALYTICS = "https://www.googleapis.com/auth/yt-analytics.readonly"

STATISTICI: dict[str, str] = {
    "viewCount": "vizualizari",
    "likeCount": "aprecieri",
    "commentCount": "comentarii",
}


def _intreg(valoare: object) -> int | None:
    """Data API întoarce numerele ca text."""
    try:
        return int(str(valoare))
    except ValueError:
        return None


class CititorYoutube:
    canal = "youtube"

    def __init__(
        self,
        *,
        costuri_unitati: dict[str, int] | None = None,
        cota_zi: int = 10_000,
        depozit: DepozitTokenuri | None = None,
        contor: Contor | None = None,
        transport: httpx.BaseTransport | None = None,
        ceas: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self.cost, self.cota_zi = costuri_unitati or {}, cota_zi
        self.depozit, self.contor = depozit or DepozitBaza(), contor or ContorBaza()
        self.http = ClientHttp(API, transport)
        self.ceas = ceas or (lambda: dt.datetime.now(dt.UTC))

    @classmethod
    def din_setari(cls) -> "CititorYoutube":
        s = get_settings()
        return cls(costuri_unitati=costuri(s.youtube_costuri), cota_zi=s.youtube_cota_zi)

    def metrici(self, tenant_id: uuid.UUID, id_extern: str) -> Metrici:
        token = token_sau_autentificare(self.depozit, tenant_id, self.canal)
        n, zi = self.cost.get("videos.list", 1), zi_pacific(self.ceas())
        if self.contor.consumat("youtube", zi) + n > self.cota_zi:
            raise EroareTemporara("cota YouTube pe azi e epuizată (citirea metricilor se amână)")
        self.contor.adauga("youtube", zi, n)
        r = self.http.cere(
            "GET", "youtube/v3/videos", token=token, params={"part": "statistics", "id": id_extern}
        ).json()
        elemente = r.get("items") or []
        if not elemente:
            raise EroareDefinitiva("clipul nu există sau nu e vizibil contului")
        st = elemente[0].get("statistics") or {}
        cifre = {camp: v for nume, camp in STATISTICI.items() if (v := _intreg(st.get(nume))) is not None}
        return Metrici(**cifre)


def puncte_din_raport(corp: dict[str, object]) -> list[tuple[float, float]]:
    """Nucleu pur: raportul Analytics (`columnHeaders` + `rows`) → punctele curbei, în ordinea poziției.
    Rândurile fără numere se ignoră; coloanele se caută după nume, nu după poziție."""
    antete = corp.get("columnHeaders")
    nume = [str(a.get("name")) for a in antete if isinstance(a, dict)] if isinstance(antete, list) else []
    if "elapsedVideoTimeRatio" not in nume or "audienceWatchRatio" not in nume:
        return []
    ix, iy = nume.index("elapsedVideoTimeRatio"), nume.index("audienceWatchRatio")
    randuri = corp.get("rows")
    puncte: list[tuple[float, float]] = []
    for r in randuri if isinstance(randuri, list) else []:
        if not isinstance(r, list) or len(r) <= max(ix, iy):
            continue
        x, y = r[ix], r[iy]
        if all(isinstance(v, int | float) and not isinstance(v, bool) for v in (x, y)):
            puncte.append((float(x), float(y)))
    return sorted(puncte)


class CititorRetentieYoutube:
    canal = "youtube"

    def __init__(
        self, *, depozit: DepozitTokenuri | None = None, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.depozit = depozit or DepozitBaza()
        self.http = ClientHttp(ANALYTICS, transport)

    @classmethod
    def din_setari(cls) -> "CititorRetentieYoutube":
        return cls()

    def retentie(
        self, tenant_id: uuid.UUID, id_extern: str, de_la: dt.date, pana_la: dt.date
    ) -> list[tuple[float, float]]:
        token = token_sau_autentificare(self.depozit, tenant_id, self.canal)
        r = self.http.cere(
            "GET",
            "v2/reports",
            token=token,
            params={
                "ids": "channel==MINE",
                "metrics": "audienceWatchRatio",
                "dimensions": "elapsedVideoTimeRatio",
                "filters": f"video=={id_extern}",
                "startDate": de_la.isoformat(),
                "endDate": pana_la.isoformat(),
            },
        )
        return puncte_din_raport(dict(r.json()))
