"""Contul Google Ads prin Google Ads API (REST; F13.2; scrierea vine în F13.4).

Citirea: `POST /<versiune>/customers/<id>/googleAds:searchStream`, cu o interogare GAQL pe campanie și pe
reclamă (`segments.date`), antetele `developer-token` și `login-customer-id`.
Costul vine în micro-unități (`metrics.cost_micros`); 1 leu = 1.000.000 micro = 100 de bani. Conversiile sunt
zecimale (modelele de atribuire le împart); se rotunjesc în jos la rezultate întregi.

# NEVERIFICAT: versiunea API, nivelul de acces (Explorer/Basic, docs/16 §16.2), contul de administrator (MCC)
și forma exactă a răspunsurilor, la migrare. Testat pe Google Ads API simulat (contract HTTP local).
"""

import datetime as dt
import json
import uuid
from typing import Any

import httpx

from app.config import get_settings
from app.connectors.contract import RandReclame, RezultatPlatforma, StareCont, Token
from app.connectors.publicare.baza import ClientHttp, DepozitBaza, DepozitTokenuri, token_sau_autentificare
from app.operare.motor import EroareDefinitiva

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

    # --- scrierea (F13.4): campania în pauză (grupul și reclamele active sub ea); căutare după nume
    # înainte de
    # creare, ca reîncercarea după un răspuns pierdut să nu dubleze campania.
    def _mutate(
        self, tenant_id: uuid.UUID, cid: str, colectie: str, operatii: list[dict[str, Any]]
    ) -> list[str]:
        corp = self.cere(tenant_id, f"customers/{cid}/{colectie}:mutate", {"operations": operatii})
        return [str(r["resourceName"]) for r in corp.get("results", [])]

    def _campanie(
        self, tenant_id: uuid.UUID, cid: str, *, nume: str = "", id_: str = ""
    ) -> dict[str, Any] | None:
        gaql = "SELECT campaign.id, campaign.name, campaign.status, campaign.campaign_budget FROM campaign"
        if nume:
            gaql += " WHERE campaign.name = '" + nume.replace("'", "") + "'"
        for r in self.cauta(tenant_id, cid, gaql):
            c = r.get("campaign") or {}
            if (not nume or c.get("name") == nume.replace("'", "")) and (not id_ or str(c.get("id")) == id_):
                return dict(c)
        return None

    def scrie(self, tenant_id: uuid.UUID, payload: dict[str, Any]) -> RezultatPlatforma:
        cid = client_id(str(payload["cont_extern"]))
        actiune = payload["actiune"]
        if actiune == "creeaza_campanie":
            nume = str(payload["nume"]).replace("'", "")
            gasita = self._campanie(tenant_id, cid, nume=nume)
            if gasita is not None:
                return RezultatPlatforma(id_extern=str(gasita["id"]), link=json.dumps({"reclame": {}}))
            [buget] = self._mutate(
                tenant_id,
                cid,
                "campaignBudgets",
                [
                    {
                        "create": {
                            "name": f"{nume} · buget",
                            "amountMicros": str(int(payload["buget_zilnic_bani"]) * MICRO_PE_BAN),
                            "deliveryMethod": "STANDARD",
                            "explicitlyShared": False,
                        }
                    }
                ],
            )
            [campanie] = self._mutate(
                tenant_id,
                cid,
                "campaigns",
                [
                    {
                        "create": {
                            "name": nume,
                            "status": "PAUSED",
                            "campaignBudget": buget,
                            "advertisingChannelType": "SEARCH",
                            "manualCpc": {},
                            "containsEuPoliticalAdvertising": "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING",
                        }
                    }
                ],
            )
            [grup] = self._mutate(
                tenant_id,
                cid,
                "adGroups",
                [{"create": {"name": f"{nume} · grup", "campaign": campanie, "status": "ENABLED"}}],
            )
            harta: dict[str, str] = {}
            for r in payload.get("reclame", []):
                [anunt] = self._mutate(
                    tenant_id,
                    cid,
                    "adGroupAds",
                    [
                        {
                            "create": {
                                "adGroup": grup,
                                "status": "ENABLED",
                                "ad": {
                                    "name": r["nume"],
                                    "finalUrls": [r["link"]],
                                    "responsiveSearchAd": {
                                        "headlines": [{"text": r["titlu"][:30]}],
                                        "descriptions": [{"text": r["text"][:90]}],
                                    },
                                },
                            }
                        }
                    ],
                )
                harta[r["nume"]] = anunt
            return RezultatPlatforma(
                id_extern=campanie.rsplit("/", 1)[1], link=json.dumps({"reclame": harta})
            )
        obiect = str(payload["obiect_extern"])
        if actiune == "stare_campanie":
            stare = "PAUSED" if payload["stare"] == "pauza" else "ENABLED"
            self._mutate(
                tenant_id,
                cid,
                "campaigns",
                [
                    {
                        "update": {"resourceName": f"customers/{cid}/campaigns/{obiect}", "status": stare},
                        "updateMask": "status",
                    }
                ],
            )
        elif actiune == "stare_anunt":
            stare = "PAUSED" if payload["stare"] == "pauza" else "ENABLED"
            self._mutate(
                tenant_id,
                cid,
                "adGroupAds",
                [{"update": {"resourceName": obiect, "status": stare}, "updateMask": "status"}],
            )
        elif actiune == "buget_campanie":
            c = self._campanie(tenant_id, cid, id_=obiect)
            if c is None:
                raise EroareDefinitiva("campania nu există la Google Ads")
            self._mutate(
                tenant_id,
                cid,
                "campaignBudgets",
                [
                    {
                        "update": {
                            "resourceName": c["campaignBudget"],
                            "amountMicros": str(int(payload["buget_zilnic_bani"]) * MICRO_PE_BAN),
                        },
                        "updateMask": "amount_micros",
                    }
                ],
            )
        else:
            raise EroareDefinitiva(f"acțiune necunoscută: {actiune}")
        return RezultatPlatforma(id_extern=obiect)
