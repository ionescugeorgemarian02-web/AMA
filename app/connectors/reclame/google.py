"""Contul Google Ads prin Google Ads API (REST; F13.2; scrierea vine în F13.4).

Citirea: `POST /<versiune>/customers/<id>/googleAds:searchStream`, cu o interogare GAQL pe campanie și pe
reclamă (`segments.date`), antetele `developer-token` și `login-customer-id`.
Costul vine în micro-unități (`metrics.cost_micros`); 1 leu = 1.000.000 micro = 100 de bani. Conversiile sunt
zecimale (modelele de atribuire le împart); se rotunjesc în jos la rezultate întregi.

# NEVERIFICAT: versiunea API, nivelul de acces (Explorer/Basic, docs/16 §16.2), contul de administrator (MCC)
și forma exactă a răspunsurilor, la migrare. Testat pe Google Ads API simulat (contract HTTP local).
"""

import datetime as dt
import uuid
from typing import Any

import httpx

from app.config import get_settings
from app.connectors.contract import RandReclame, StareCont, Token
from app.connectors.publicare.baza import ClientHttp, DepozitBaza, DepozitTokenuri, token_sau_autentificare

BAZA = "https://googleads.googleapis.com"
CANAL_TOKEN = "google_ads"  # noqa: S105  (numele canalului din depozit, nu un secret)
MICRO_PE_BAN = 10_000
INTEROGARE_CAMPANII = (
    "SELECT campaign.id, campaign.name, segments.date, metrics.cost_micros, metrics.impressions, "
    "metrics.clicks, metrics.conversions FROM campaign WHERE segments.date BETWEEN '{de_la}' AND '{pana_la}'"
)
INTEROGARE_RECLAME = (
    "SELECT campaign.id, ad_group_ad.ad.id, ad_group_ad.ad.name, segments.date, metrics.cost_micros, "
    "metrics.impressions, metrics.clicks, metrics.conversions FROM ad_group_ad "
    "WHERE segments.date BETWEEN '{de_la}' AND '{pana_la}'"
)


def _intreg(v: Any) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def rand_din_gaql(r: dict[str, Any], nivel: str) -> RandReclame:
    """Nucleu pur: un rând `searchStream` → `RandReclame` (câmpurile vin în camelCase, numerele ca text)."""
    c, m = r.get("campaign") or {}, r.get("metrics") or {}
    ad = (r.get("adGroupAd") or {}).get("ad") or {}
    reclama = nivel == "reclama"
    return RandReclame(
        nivel=nivel,
        id_extern=str(ad.get("id") if reclama else c.get("id", "")),
        nume=str(ad.get("name", "") if reclama else c.get("name", "")),
        zi=dt.date.fromisoformat(str((r.get("segments") or {})["date"])),
        cheltuiala_bani=_intreg(m.get("costMicros")) // MICRO_PE_BAN,
        afisari=_intreg(m.get("impressions")),
        clicuri=_intreg(m.get("clicks")),
        rezultate=_intreg(m.get("conversions")),
        parinte_extern=str(c.get("id", "")) if reclama else "",
    )


def client_id(cont_extern: str) -> str:
    return cont_extern.replace("-", "")


class ContGoogle:
    platforma = "google"

    def __init__(
        self,
        *,
        versiune: str = "v21",
        developer_token: str = "",
        login_customer_id: str = "",
        depozit: DepozitTokenuri | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.depozit = depozit or DepozitBaza()
        self.http = ClientHttp(f"{BAZA}/{versiune}", transport)
        self.developer_token, self.login_customer_id = developer_token, login_customer_id

    @classmethod
    def din_setari(cls) -> "ContGoogle":
        s = get_settings()
        return cls(
            versiune=s.google_ads_versiune,
            developer_token=s.google_ads_developer_token.get_secret_value(),
            login_customer_id=s.google_ads_login_customer_id,
        )

    def _antete(self) -> dict[str, str]:
        a = {"developer-token": self.developer_token}
        if self.login_customer_id:
            a["login-customer-id"] = client_id(self.login_customer_id)
        return a

    def _token(self, tenant_id: uuid.UUID) -> Token:
        return token_sau_autentificare(self.depozit, tenant_id, CANAL_TOKEN)

    def cere(self, tenant_id: uuid.UUID, cale: str, corp: dict[str, Any]) -> Any:
        return self.http.cere(
            "POST", cale, token=self._token(tenant_id), headers=self._antete(), json=corp
        ).json()

    def cauta(self, tenant_id: uuid.UUID, cont_extern: str, gaql: str) -> list[dict[str, Any]]:
        loturi = self.cere(
            tenant_id, f"customers/{client_id(cont_extern)}/googleAds:searchStream", {"query": gaql}
        )
        return [r for lot in loturi or [] for r in lot.get("results", [])]

    def rezultate(
        self, tenant_id: uuid.UUID, cont_extern: str, de_la: dt.date, pana_la: dt.date
    ) -> list[RandReclame]:
        interval = {"de_la": de_la.isoformat(), "pana_la": pana_la.isoformat()}
        campanii = self.cauta(tenant_id, cont_extern, INTEROGARE_CAMPANII.format(**interval))
        reclame = self.cauta(tenant_id, cont_extern, INTEROGARE_RECLAME.format(**interval))
        randuri = [rand_din_gaql(r, "campanie") for r in campanii]
        return randuri + [rand_din_gaql(r, "reclama") for r in reclame]

    def stare_cont(self, tenant_id: uuid.UUID, cont_extern: str) -> StareCont:
        r = self.cauta(tenant_id, cont_extern, "SELECT customer.id, customer.status FROM customer")
        stare = str(((r[0] if r else {}).get("customer") or {}).get("status", "UNKNOWN"))
        return StareCont(activ=stare == "ENABLED", motiv="" if stare == "ENABLED" else f"contul este {stare}")
