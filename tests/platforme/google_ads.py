"""# SIMULAT: Google Ads API (REST), ca server HTTP local. Forma urmează documentația publică:
`customers/<id>/googleAds:searchStream` (GAQL, rezultate în loturi, câmpuri camelCase, numere ca text,
`costMicros`), `customers/<id>/campaignBudgets:mutate`, `campaigns:mutate`, `adGroups:mutate`,
`adGroupAds:mutate` (operații `create` / `update` + `updateMask`), erorile `{"error": {"code", "status"}}`.
Cere antetul `developer-token`. Cheltuiala se produce ca la Meta (`zi(…)`), iar `manager` e totalul din consolă."""

import datetime as dt
import re
import secrets
from typing import Any

import httpx

from tests.platforme.baza import PlatformaHttp

VERSIUNE = "v21"
DEV_TOKEN = "dev-token-test"  # pragma: allowlist secret
MICRO = 10_000  # micro pe ban


class GoogleAdsSimulat(PlatformaHttp):
    def __init__(self, client: str = "1234567890") -> None:
        super().__init__()
        self.client = client
        self.stare = "ENABLED"
        self.bugete: dict[str, int] = {}  # resourceName → amountMicros
        self.campanii_: dict[str, dict[str, Any]] = {}  # id → campanie
        self.grupuri: dict[str, str] = {}  # id grup → id campanie
        self.reclame_: dict[str, dict[str, Any]] = {}  # id reclamă → {name, status, campanie, …}
        self.zile: dict[tuple[str, dt.date], dict[str, int]] = {}  # (id reclamă, zi) → cifre (micro)
        self.scrieri: list[dict[str, Any]] = []

    # --- controlul testului ---------------------------------------------------------------------------------
    @staticmethod
    def _id() -> str:
        return str(20_000_000_000 + secrets.randbelow(10**9))

    def adauga_campanie(self, nume: str, buget_bani: int, stare: str = "ENABLED") -> str:
        b = f"customers/{self.client}/campaignBudgets/{self._id()}"
        self.bugete[b] = buget_bani * MICRO
        cid = self._id()
        self.campanii_[cid] = {"id": cid, "name": nume, "status": stare, "campaignBudget": b}
        rid = self._id()
        self.reclame_[rid] = {"id": rid, "name": f"{nume} · reclama", "status": "ENABLED", "campanie": cid}
        return cid

    def buget_bani(self, cid: str) -> int:
        return self.bugete[self.campanii_[cid]["campaignBudget"]] // MICRO

    def zi(self, zi: dt.date, *, ritm: float = 1.0, cpm_bani: int = 1500, ctr: float = 0.03,
           conversie: float = 0.1) -> None:  # fmt: skip
        for c in self.campanii_.values():
            ads = [a for a in self.reclame_.values() if a["campanie"] == c["id"] and a["status"] == "ENABLED"]
            if c["status"] != "ENABLED" or not ads:
                continue
            total = int(self.bugete[c["campaignBudget"]] // MICRO * ritm)
            for a in ads:
                bani = total // len(ads)
                afis = bani * 1000 // cpm_bani
                clic = int(afis * ctr)
                z = self.zile.setdefault(
                    (a["id"], zi), {"bani": 0, "afisari": 0, "clicuri": 0, "rezultate": 0}
                )
                for k, v in (
                    ("bani", bani),
                    ("afisari", afis),
                    ("clicuri", clic),
                    ("rezultate", int(clic * conversie)),
                ):
                    z[k] += v

    def manager(self, de_la: dt.date, pana_la: dt.date) -> dict[str, int]:
        t = {"bani": 0, "afisari": 0, "clicuri": 0, "rezultate": 0}
        for (_, zi), v in self.zile.items():
            if de_la <= zi <= pana_la:
                for k in t:
                    t[k] += v[k]
        return t

    # --- rute -----------------------------------------------------------------------------------------------
    @staticmethod
    def eroare(cod: int, stare: str, mesaj: str) -> httpx.Response:
        return httpx.Response(cod, json={"error": {"code": cod, "message": mesaj, "status": stare}})

    def trateaza(self, req: httpx.Request) -> httpx.Response:
        if not self.autorizat(req):
            return self.eroare(
                401, "UNAUTHENTICATED", "Request is missing required authentication credential."
            )
        if req.headers.get("developer-token") != DEV_TOKEN:
            return self.eroare(403, "PERMISSION_DENIED", "The developer token is not approved.")
        d = self.defect()
        if d == "temporar":
            return self.eroare(503, "UNAVAILABLE", "The service is currently unavailable.")
        if d == "timeout":
            return self.timeout(req)
        m = re.fullmatch(rf"/{VERSIUNE}/customers/(\d+)/(googleAds:searchStream|\w+:mutate)", req.url.path)
        if not m or m.group(1) != self.client:
            return self.eroare(404, "NOT_FOUND", "Customer not found.")
        corp = self.corp(req)
        if m.group(2) == "googleAds:searchStream":
            return self._cauta(str(corp.get("query", "")))
        r = self._mutate(m.group(2).split(":")[0], corp.get("operations", []))
        if d == "pierde_raspunsul":
            raise httpx.ReadTimeout("simulat: răspuns pierdut")
        return r

    def _mutate(self, colectie: str, operatii: list[dict[str, Any]]) -> httpx.Response:
        rezultate = []
        for op in operatii:
            self.scrieri.append({"colectie": colectie, **op})
            if "create" in op:
                c = op["create"]
                oid = self._id()
                if colectie == "campaignBudgets":
                    nume = f"customers/{self.client}/campaignBudgets/{oid}"
                    self.bugete[nume] = int(c["amountMicros"])
                elif colectie == "campaigns":
                    if (
                        c.get("status") not in ("PAUSED", "ENABLED")
                        or c.get("campaignBudget") not in self.bugete
                    ):
                        return self.eroare(400, "INVALID_ARGUMENT", "Request contains an invalid argument.")
                    self.campanii_[oid] = {"id": oid, "name": c["name"], "status": c["status"],
                                           "campaignBudget": c["campaignBudget"]}  # fmt: skip
                    nume = f"customers/{self.client}/campaigns/{oid}"
                elif colectie == "adGroups":
                    self.grupuri[oid] = str(c["campaign"]).rsplit("/", 1)[1]
                    nume = f"customers/{self.client}/adGroups/{oid}"
                elif colectie == "adGroupAds":
                    grup = str(c["adGroup"]).rsplit("/", 1)[1]
                    self.reclame_[oid] = {"id": oid, "name": c.get("ad", {}).get("name", ""), "status": c["status"],
                                          "campanie": self.grupuri[grup], "ad": c.get("ad", {})}  # fmt: skip
                    nume = f"customers/{self.client}/adGroupAds/{grup}~{oid}"
                else:
                    return self.eroare(400, "INVALID_ARGUMENT", "Unknown resource.")
                rezultate.append({"resourceName": nume})
            elif "update" in op:
                u, masca = op["update"], str(op.get("updateMask", "")).split(",")
                nume = str(u["resourceName"])
                if colectie == "campaignBudgets" and nume in self.bugete and "amount_micros" in masca:
                    self.bugete[nume] = int(u["amountMicros"])
                elif (
                    colectie == "campaigns" and nume.rsplit("/", 1)[1] in self.campanii_ and "status" in masca
                ):
                    self.campanii_[nume.rsplit("/", 1)[1]]["status"] = u["status"]
                else:
                    return self.eroare(400, "INVALID_ARGUMENT", "Resource not found or field not in mask.")
                rezultate.append({"resourceName": nume})
        return self.json(200, {"results": rezultate})

    def _cauta(self, q: str) -> httpx.Response:
        if "FROM customer" in q:
            return self.json(200, [{"results": [{"customer": {"id": self.client, "status": self.stare}}]}])
        if "FROM campaign_budget" in q or ("FROM campaign" in q and "segments.date" not in q):
            m = re.search(r"campaign\.name = '([^']*)'", q)
            res = [{"campaign": {"id": c["id"], "name": c["name"], "status": c["status"],
                                 "resourceName": f"customers/{self.client}/campaigns/{c['id']}",
                                 "campaignBudget": c["campaignBudget"]},
                    "campaignBudget": {"amountMicros": str(self.bugete[c["campaignBudget"]])}}
                   for c in self.campanii_.values() if not m or c["name"] == m.group(1)]  # fmt: skip
            return self.json(200, [{"results": res}] if res else [])
        m = re.search(r"BETWEEN '([\d-]+)' AND '([\d-]+)'", q)
        if not m:
            return self.eroare(400, "INVALID_ARGUMENT", "Query error.")
        de_la, pana_la = dt.date.fromisoformat(m.group(1)), dt.date.fromisoformat(m.group(2))
        pe_reclama = "FROM ad_group_ad" in q
        grup: dict[tuple[str, dt.date], dict[str, int]] = {}
        for (rid, zi), v in sorted(self.zile.items(), key=lambda x: (x[0][1], x[0][0])):
            if de_la <= zi <= pana_la:
                g = grup.setdefault(
                    (rid if pe_reclama else self.reclame_[rid]["campanie"], zi), dict.fromkeys(v, 0)
                )
                for k in g:
                    g[k] += v[k]
        res = []
        for (oid, zi), v in grup.items():
            camp = self.campanii_[self.reclame_[oid]["campanie"] if pe_reclama else oid]
            r: dict[str, Any] = {
                "campaign": {"resourceName": f"customers/{self.client}/campaigns/{camp['id']}", "id": camp["id"],
                             "name": camp["name"]},
                "segments": {"date": zi.isoformat()},
                "metrics": {"costMicros": str(v["bani"] * MICRO), "impressions": str(v["afisari"]),
                            "clicks": str(v["clicuri"]), "conversions": float(v["rezultate"])},
            }  # fmt: skip
            if pe_reclama:
                r["adGroupAd"] = {"ad": {"id": oid, "name": self.reclame_[oid]["name"]}}
            res.append(r)
        loturi = [
            {"results": res[i : i + 3]} for i in range(0, len(res), 3)
        ]  # loturi mici: se vede împărțirea
        return self.json(200, loturi)
