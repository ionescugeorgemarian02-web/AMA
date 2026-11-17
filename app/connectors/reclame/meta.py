"""Contul de reclame Meta prin Marketing API (F13.1; scrierea vine în F13.4).

Citirea: `GET /act_<id>/insights?level=campaign&time_increment=1&time_range=…` (cheltuiala, afișări, clicuri,
acțiuni), cu paginare (`paging.next`). Cheltuiala vine ca text zecimal în moneda contului; se păstrează în
subunități (bani), fără rotunjiri pe drum. Rezultatul urmărit e acțiunea `ACTIUNE_REZULTAT` (lead-ul de pe
pagina de audit).

# NEVERIFICAT: forma reală a răspunsurilor pe contul agenției (versiunea Graph, numele acțiunii de conversie,
fusul orar al contului pentru „zi”) se verifică la migrare. Accesul cere `ads_read`/`ads_management` (App
Review, firmă verificată, docs/16 §16.2). Testat pe Marketing API simulat (contract HTTP local).
"""

import datetime as dt
import json
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.config import get_settings
from app.connectors.contract import RandReclame, StareCont
from app.connectors.publicare.baza import ClientHttp, DepozitBaza, DepozitTokenuri, token_sau_autentificare
from app.connectors.publicare.facebook import GRAPH, clasifica_graph
from app.operare.motor import EroareDefinitiva

CANAL_TOKEN = "meta_ads"  # noqa: S105  (numele canalului din depozit, nu un secret)
ACTIUNE_REZULTAT = "lead"
CAMPURI = "campaign_id,campaign_name,spend,impressions,clicks,actions,date_start"
# account_status din Marketing API: 1 = activ; restul (dezactivat, neplătit, în revizuire de risc) = problemă.
STARI_CONT = {2: "cont dezactivat", 3: "plată restantă", 7: "în revizuire de risc", 9: "perioadă de grație",
              100: "închidere în curs", 101: "închis", 201: "orice activ închis"}  # fmt: skip
PAGINI_MAXIME = 50


def bani(text: Any) -> int:
    """`"12.34"` → 1234. Valorile care nu sunt numere devin 0 (Marketing API dă `spend` mereu ca text)."""
    try:
        return int((Decimal(str(text)) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return 0


def _intreg(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def rand_din_insights(r: dict[str, Any], nivel: str) -> RandReclame:
    """Nucleu pur: un rând `insights` → `RandReclame`."""
    rezultate = sum(
        _intreg(a.get("value")) for a in r.get("actions") or [] if a.get("action_type") == ACTIUNE_REZULTAT
    )
    reclama = nivel == "reclama"
    return RandReclame(
        nivel=nivel,
        id_extern=str(r.get("ad_id" if reclama else "campaign_id", "")),
        nume=str(r.get("ad_name" if reclama else "campaign_name", "")),
        zi=dt.date.fromisoformat(str(r["date_start"])),
        cheltuiala_bani=bani(r.get("spend", "0")),
        afisari=_intreg(r.get("impressions")),
        clicuri=_intreg(r.get("clicks")),
        rezultate=rezultate,
        parinte_extern=str(r.get("campaign_id", "")) if reclama else "",
    )


class ContMeta:
    platforma = "meta"

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
    def din_setari(cls) -> "ContMeta":
        return cls(versiune=get_settings().meta_graph_versiune)

    def _token(self, tenant_id: uuid.UUID) -> Any:
        return token_sau_autentificare(self.depozit, tenant_id, CANAL_TOKEN)

    @staticmethod
    def _act(cont_extern: str) -> str:
        return cont_extern if cont_extern.startswith("act_") else f"act_{cont_extern}"

    def _insights(
        self, tenant_id: uuid.UUID, cont_extern: str, de_la: dt.date, pana_la: dt.date, nivel: str
    ) -> list[RandReclame]:
        token = self._token(tenant_id)
        params: dict[str, str] | None = {
            "level": "ad" if nivel == "reclama" else "campaign",
            "fields": CAMPURI + (",ad_id,ad_name" if nivel == "reclama" else ""),
            "time_increment": "1",
            "time_range": json.dumps({"since": de_la.isoformat(), "until": pana_la.isoformat()}),
            "limit": "100",
        }
        url = f"{self._act(cont_extern)}/insights"
        randuri: list[RandReclame] = []
        for _ in range(PAGINI_MAXIME):
            corp = self.http.cere("GET", url, token=token, params=params).json()
            randuri.extend(rand_din_insights(r, nivel) for r in corp.get("data", []))
            urmator = (corp.get("paging") or {}).get("next")
            if not urmator:
                return randuri
            url, params = str(urmator), None
        raise EroareDefinitiva("prea multe pagini de rezultate")

    def rezultate(
        self, tenant_id: uuid.UUID, cont_extern: str, de_la: dt.date, pana_la: dt.date
    ) -> list[RandReclame]:
        return [
            *self._insights(tenant_id, cont_extern, de_la, pana_la, "campanie"),
            *self._insights(tenant_id, cont_extern, de_la, pana_la, "reclama"),
        ]

    def stare_cont(self, tenant_id: uuid.UUID, cont_extern: str) -> StareCont:
        corp = self.http.cere(
            "GET", self._act(cont_extern), token=self._token(tenant_id),
            params={"fields": "account_status,disable_reason"},
        ).json()  # fmt: skip
        cod = _intreg(corp.get("account_status"))
        return StareCont(activ=cod == 1, motiv="" if cod == 1 else STARI_CONT.get(cod, f"stare {cod}"))
