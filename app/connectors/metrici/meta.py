"""Cititorii de metrici Meta (F10.1): Facebook Pages și Instagram, prin Graph API.

- Facebook: `GET /{post}/insights?metric=…` (afișări, acoperire, clicuri) și
  `GET /{post}?fields=shares,comments.summary(true),reactions.summary(true)` (interacțiuni).
- Instagram: `GET /{media}/insights?metric=…` (acoperire, vizualizări, aprecieri, comentarii, distribuiri,
  salvări).
- O metrică pe care platforma nu o întoarce rămâne `None` (nu devine zero).
- Postarea ștearsă (Graph: codul 100) = `EroareDefinitiva`; restul erorilor, după clasificarea Graph (F9.2).

# NEVERIFICAT: numele metricilor de mai jos se schimbă între versiunile Graph (Meta a înlocuit în 2025
impresiile cu „views”); se verifică pe contul agenției la migrare și se corectează în constantele `METRICI_*`.
Permisiunile de citire (`read_insights`, `instagram_manage_insights`) trec prin App Review. Testat pe Graph
simulat (contract HTTP local).
"""

import uuid
from typing import Any, ClassVar

import httpx

from app.config import get_settings
from app.connectors.contract import Metrici, Token
from app.connectors.publicare.baza import (
    ClientHttp,
    DepozitBaza,
    DepozitTokenuri,
    mesaj_platforma,
    token_sau_autentificare,
)
from app.connectors.publicare.facebook import GRAPH, clasifica_graph
from app.operare.motor import EroareDefinitiva

# numele metricii la platformă → câmpul din `Metrici`
METRICI_FACEBOOK: dict[str, str] = {
    "post_impressions": "afisari",
    "post_impressions_unique": "acoperire",
    "post_clicks": "clicuri",
    "post_video_views": "vizualizari",
}
METRICI_INSTAGRAM: dict[str, str] = {
    "views": "vizualizari",
    "reach": "acoperire",
    "likes": "aprecieri",
    "comments": "comentarii",
    "shares": "distribuiri",
    "saved": "salvari",
}


def din_insights(corp: dict[str, Any], harta: dict[str, str]) -> dict[str, int]:
    """Nucleu pur: răspunsul `insights` (lista `data`, fiecare cu `name` și `values[0].value` sau
    `total_value.value`) → câmpurile noastre. Valorile care nu sunt numere se ignoră."""
    out: dict[str, int] = {}
    for m in corp.get("data", []):
        camp = harta.get(str(m.get("name")))
        if camp is None:
            continue
        v: Any = (m.get("total_value") or {}).get("value")
        if v is None and m.get("values"):
            v = m["values"][0].get("value")
        if isinstance(v, int | float) and not isinstance(v, bool):
            out[camp] = int(v)
    return out


class CititorMeta:
    canal = "meta"
    harta: ClassVar[dict[str, str]] = {}

    def __init__(
        self,
        *,
        versiune: str = "v23.0",
        depozit: DepozitTokenuri | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.depozit = depozit or DepozitBaza()
        self.http = ClientHttp(f"{GRAPH}/{versiune}", transport, clasificator=clasifica_graph)

    @classmethod
    def din_setari(cls) -> "CititorMeta":
        return cls(versiune=get_settings().meta_graph_versiune)

    def _get(self, cale: str, token: Token, **params: str) -> dict[str, Any]:
        r = self.http.cere("GET", cale, token=token, params=params, clasifica_erori=False)
        if r.status_code in (400, 404):
            try:
                cod = r.json().get("error", {}).get("code")
            except ValueError:
                cod = None
            if cod == 100 or r.status_code == 404:
                raise EroareDefinitiva(f"postarea nu există sau nu are metrici: {mesaj_platforma(r)}")
        clasifica_graph(r)
        return dict(r.json())

    def _insights(self, token: Token, id_extern: str) -> dict[str, int]:
        return din_insights(
            self._get(f"{id_extern}/insights", token, metric=",".join(self.harta)), self.harta
        )

    def metrici(self, tenant_id: uuid.UUID, id_extern: str) -> Metrici:
        token = token_sau_autentificare(self.depozit, tenant_id, self.canal)
        return Metrici(**self._insights(token, id_extern))


class CititorFacebook(CititorMeta):
    canal = "facebook"
    harta = METRICI_FACEBOOK

    def metrici(self, tenant_id: uuid.UUID, id_extern: str) -> Metrici:
        token = token_sau_autentificare(self.depozit, tenant_id, self.canal)
        cifre = self._insights(token, id_extern)
        p = self._get(
            id_extern, token, fields="shares,comments.summary(true).limit(0),reactions.summary(true).limit(0)"
        )
        for camp, valoare in (
            ("distribuiri", (p.get("shares") or {}).get("count")),
            ("comentarii", ((p.get("comments") or {}).get("summary") or {}).get("total_count")),
            ("aprecieri", ((p.get("reactions") or {}).get("summary") or {}).get("total_count")),
        ):
            if isinstance(valoare, int) and not isinstance(valoare, bool):
                cifre[camp] = valoare
        return Metrici(**cifre)


class CititorInstagram(CititorMeta):
    canal = "instagram"
    harta = METRICI_INSTAGRAM
