"""Conectorul YouTube (F9.4): YouTube Data API v3, încărcare reluabilă.

- Autorizarea: OAuth Google (`access_type=offline`): token de acces scurt + token de reîmprospătare; contul
extern
  e canalul (`channels?mine=true`).
- Încărcarea: `POST upload/youtube/v3/videos?uploadType=resumable` cu metadatele (titlu, descriere,
vizibilitate,
  `status.containsSyntheticMedia` = câmpul „conținut modificat sau sintetic”, din eticheta AI a pașaportului),
  apoi `PUT` pe adresa sesiunii cu fișierul.
- Vizibilitatea vine din pachet (`vizibilitate`): publică doar după audit; înainte, privată (15.1). Proiectul
  neauditat își vede oricum clipurile blocate pe privat de platformă; starea afișată se citește înapoi
  (`stare`).
- Costul în unități: fiecare metodă are costul ei (`AMA_YOUTUBE_COSTURI`, valorile citite din consola Google
Cloud;
  sursele spun 100 sau 1.600 pentru încărcare, docs/02), consumul se numără pe ziua Pacific în
  `publicare_cote` (10.000 pe zi [I]). Fără unități pentru o încărcare: temporară, până la resetare.
- `verifica`: lista încărcărilor canalului (`playlistItems`, 1 unitate), după titlu și descriere.

# NEVERIFICAT: costurile reale în unități, cota proiectului, auditul; API simulat (contract HTTP local).
"""

import datetime as dt
import uuid
import zoneinfo
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx

from app.config import get_settings
from app.connectors.contract import EfectDeTrimis, Limite, RezultatPlatforma, StarePostare, Token
from app.connectors.publicare.baza import (
    ClientHttp,
    DepozitBaza,
    DepozitTokenuri,
    cu_expirare,
    text_postare,
    token_sau_autentificare,
)
from app.operare.motor import EroareAutentificare, EroareDefinitiva, EroareTemporara

API = "https://www.googleapis.com"
SCOPURI = (
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",  # cererea B (F10.2): curba de retenție
)
PACIFIC = zoneinfo.ZoneInfo("America/Los_Angeles")


def zi_pacific(acum: dt.datetime | None = None) -> dt.date:
    """Cota YouTube se resetează la miezul nopții, ora Pacificului."""
    return (acum or dt.datetime.now(dt.UTC)).astimezone(PACIFIC).date()


def resetare(acum: dt.datetime | None = None) -> dt.datetime:
    z = zi_pacific(acum) + dt.timedelta(days=1)
    return dt.datetime(z.year, z.month, z.day, tzinfo=PACIFIC).astimezone(dt.UTC)


def costuri(text: str) -> dict[str, int]:
    """`metoda=unități,…` → dicționar (configurarea, din consola Google Cloud)."""
    out: dict[str, int] = {}
    for parte in text.split(","):
        if "=" in parte:
            k, v = parte.split("=", 1)
            out[k.strip()] = int(v)
    return out


class Contor(Protocol):
    def consumat(self, platforma: str, zi: dt.date) -> int: ...
    def adauga(self, platforma: str, zi: dt.date, unitati: int) -> None: ...


class ContorBaza:
    def consumat(self, platforma: str, zi: dt.date) -> int:
        from app.publicare import cote

        return cote.consumat(platforma, zi)

    def adauga(self, platforma: str, zi: dt.date, unitati: int) -> None:
        from app.publicare import cote

        cote.adauga(platforma, zi, unitati)


class ConectorYoutube:
    canal = "youtube"

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        costuri_unitati: dict[str, int],
        cota_zi: int = 10_000,
        depozit: DepozitTokenuri | None = None,
        contor: Contor | None = None,
        transport: httpx.BaseTransport | None = None,
        ceas: Callable[[], dt.datetime] | None = None,
        citeste_fisier: Callable[[str], bytes] | None = None,
    ) -> None:
        self.client_id, self._secret = client_id, client_secret
        self.cost, self.cota_zi = costuri_unitati, cota_zi
        self.depozit, self.contor = depozit or DepozitBaza(), contor or ContorBaza()
        self.http = ClientHttp(API, transport)
        self.ceas = ceas or (lambda: dt.datetime.now(dt.UTC))
        self.citeste_fisier = citeste_fisier or (
            lambda rel: (Path(get_settings().media_dir) / rel).read_bytes()
        )

    @classmethod
    def din_setari(cls) -> "ConectorYoutube":
        s = get_settings()
        return cls(
            client_id=s.google_client_id,
            client_secret=s.google_client_secret.get_secret_value(),
            costuri_unitati=costuri(s.youtube_costuri),
            cota_zi=s.youtube_cota_zi,
        )

    # --- cota în unități ------------------------------------------------------------------------------------
    def _consuma(self, metoda: str) -> None:
        n = self.cost.get(metoda, 1)
        zi = zi_pacific(self.ceas())
        if self.contor.consumat("youtube", zi) + n > self.cota_zi:
            raise EroareTemporara(f"cota YouTube pe azi e epuizată ({metoda} costă {n} unități)")
        self.contor.adauga("youtube", zi, n)

    def limite(self, tenant_id: uuid.UUID) -> Limite:
        self._token(tenant_id)
        acum = self.ceas()
        folosit = self.contor.consumat("youtube", zi_pacific(acum))
        return Limite(
            "contorul de unități (costurile din consola Google Cloud)",
            self.cota_zi - folosit,
            self.cota_zi,
            round(100.0 * folosit / self.cota_zi, 1),
            resetare(acum),
        )

    # --- autorizare -----------------------------------------------------------------------------------------
    def url_autorizare(self, stare: str, redirect: str) -> str:
        q = {
            "client_id": self.client_id,
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": " ".join(SCOPURI),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": stare,
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(q)}"

    def _schimb(self, **date: str) -> dict[str, Any]:
        r = self.http.cere(
            "POST",
            "https://oauth2.googleapis.com/token",
            data={"client_id": self.client_id, "client_secret": self._secret, **date},
        )
        return dict(r.json())

    def schimba_cod(self, cod: str, redirect: str) -> Token:
        d = self._schimb(code=cod, redirect_uri=redirect, grant_type="authorization_code")
        t = Token(str(d["access_token"]), None, str(d.get("refresh_token", "")), "", tuple(SCOPURI))
        self._consuma("channels.list")
        canal = self.http.cere(
            "GET", "youtube/v3/channels", token=t, params={"part": "id", "mine": "true"}
        ).json()
        if not canal.get("items"):
            raise EroareDefinitiva("contul Google nu are un canal YouTube")
        return cu_expirare(
            Token(t.acces, None, t.reimprospatare, str(canal["items"][0]["id"]), t.scopuri),
            d.get("expires_in"),
            self.ceas(),
        )

    def reimprospateaza(self, token: Token) -> Token:
        if not token.reimprospatare:
            raise EroareAutentificare("fără token de reîmprospătare: reautorizare")
        d = self._schimb(refresh_token=token.reimprospatare, grant_type="refresh_token")
        nou = Token(str(d["access_token"]), None, token.reimprospatare, token.cont_extern, token.scopuri)
        return cu_expirare(nou, d.get("expires_in"), self.ceas())

    def _token(self, tenant_id: uuid.UUID) -> Token:
        return token_sau_autentificare(self.depozit, tenant_id, self.canal)

    # --- publicare ------------------------------------------------------------------------------------------
    @staticmethod
    def metadate(payload: dict[str, Any]) -> dict[str, Any]:
        """Nucleu pur: resursa `video` din pachet."""
        titlu = str(payload.get("titlu") or str(payload.get("text", "")).split("\n")[0])[:100]
        return {
            "snippet": {
                "title": titlu,
                "description": text_postare(payload)[:5000],
                "categoryId": "22",
                "defaultLanguage": "ro",
            },
            "status": {
                "privacyStatus": "public" if payload.get("vizibilitate") == "public" else "private",
                "selfDeclaredMadeForKids": False,
                "embeddable": True,
                "containsSyntheticMedia": bool(payload.get("eticheta_ai")),
            },
        }

    def trimite(self, efect: EfectDeTrimis) -> RezultatPlatforma:
        t = self._token(efect.tenant_id)
        fisier = str(efect.payload.get("fisier") or "")
        if not fisier:
            raise EroareDefinitiva("YouTube cere un fișier video")
        date = self.citeste_fisier(fisier)
        self._consuma("videos.insert")
        r = self.http.cere(
            "POST",
            "upload/youtube/v3/videos",
            token=t,
            json=self.metadate(efect.payload),
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={"X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(len(date))},
        )
        sesiune = r.headers.get("location")
        if not sesiune:
            raise EroareTemporara("YouTube nu a întors adresa sesiunii de încărcare")
        v = self.http.cere(
            "PUT", sesiune, token=t, content=date, headers={"Content-Type": "video/mp4"}
        ).json()
        return RezultatPlatforma(str(v["id"]), f"https://www.youtube.com/watch?v={v['id']}")

    def verifica(self, efect: EfectDeTrimis) -> RezultatPlatforma | None:
        t = self._token(efect.tenant_id)
        m = self.metadate(efect.payload)["snippet"]
        self._consuma("channels.list")
        c = self.http.cere(
            "GET", "youtube/v3/channels", token=t, params={"part": "contentDetails", "mine": "true"}
        )
        items = c.json().get("items") or []
        if not items:
            return None
        lista = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        self._consuma("playlistItems.list")
        r = self.http.cere(
            "GET",
            "youtube/v3/playlistItems",
            token=t,
            params={"part": "snippet", "playlistId": lista, "maxResults": "25"},
        ).json()
        for it in r.get("items", []):
            s = it.get("snippet", {})
            if s.get("title") == m["title"] and s.get("description") == m["description"]:
                vid = str(s["resourceId"]["videoId"])
                return RezultatPlatforma(vid, f"https://www.youtube.com/watch?v={vid}")
        return None

    def stare(self, tenant_id: uuid.UUID, id_extern: str) -> StarePostare:
        t = self._token(tenant_id)
        self._consuma("videos.list")
        r = self.http.cere(
            "GET", "youtube/v3/videos", token=t, params={"part": "status", "id": id_extern}
        ).json()
        if not r.get("items"):
            return StarePostare.INEXISTENTA
        s = r["items"][0]["status"]
        if s.get("uploadStatus") in ("rejected", "failed", "deleted"):
            return StarePostare.ESUATA
        if s.get("uploadStatus") == "uploaded":
            return StarePostare.IN_PROCESARE
        return StarePostare.PUBLICATA if s.get("privacyStatus") == "public" else StarePostare.PRIVATA
