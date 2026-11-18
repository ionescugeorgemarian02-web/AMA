"""# SIMULAT: TikTok API for Business (Marketing API v1.3) ca server HTTP local: HTTP 200 cu `code` în corp,
tokenul în antetul `Access-Token`, campanii / grupuri / reclame, raportul pe zi cu paginare, starea contului."""

import json
from typing import Any

import httpx

from tests.platforme.baza import PlatformaHttp


class TiktokAdsSimulat(PlatformaHttp):
    def __init__(self) -> None:
        super().__init__()
        self.campanii: dict[str, dict[str, Any]] = {}
        self.grupuri: dict[str, dict[str, Any]] = {}
        self.reclame: dict[str, dict[str, Any]] = {}
        self.raport: list[dict[str, Any]] = []  # rânduri {dimensions, metrics}, cu `data_level`
        self.stare_cont = "STATUS_ENABLE"
        self.pe_pagina = 2
        self.n = 0

    @staticmethod
    def raspuns(cod: int = 0, mesaj: str = "OK", date: Any = None) -> httpx.Response:
        return httpx.Response(
            200, json={"code": cod, "message": mesaj, "data": date or {}, "request_id": "r"}
        )

    def autorizat(self, req: httpx.Request) -> bool:
        return req.headers.get("access-token", "") in self.tokenuri and not req.headers.get("authorization")

    def _id(self) -> str:
        self.n += 1
        return str(1800000000000000 + self.n)

    def trateaza(self, req: httpx.Request) -> httpx.Response:
        if not self.autorizat(req):
            return self.raspuns(40105, "Access token is incorrect or has been revoked.")
        cale = req.url.path.removeprefix("/open_api/v1.3/")
        p = dict(req.url.params)
        if req.method == "POST":
            d = self.defect()
            if d == "temporar":
                return self.raspuns(50000, "System error")
            if d == "definitiv":
                return self.raspuns(40002, "Invalid parameter")
            return self._scrie(cale, json.loads(req.content))
        if cale == "advertiser/info/":
            return self.raspuns(
                date={
                    "list": [{"advertiser_id": json.loads(p["advertiser_ids"])[0], "status": self.stare_cont}]
                }
            )
        if cale == "report/integrated/get/":
            randuri = [r for r in self.raport if r["data_level"] == p["data_level"]]
            pagina, total = int(p.get("page", 1)), max(1, -(-len(randuri) // self.pe_pagina))
            felie = randuri[(pagina - 1) * self.pe_pagina : pagina * self.pe_pagina]
            lista = [{"dimensions": r["dimensions"], "metrics": r["metrics"]} for r in felie]
            return self.raspuns(date={"list": lista, "page_info": {"page": pagina, "total_page": total}})
        if cale.endswith("/get/"):
            return self._cauta(cale.split("/")[0], json.loads(p.get("filtering", "{}")))
        return self.raspuns(40002, "Unknown endpoint")

    def _cauta(self, colectie: str, f: dict[str, Any]) -> httpx.Response:
        if colectie == "campaign":
            lista = [c for c in self.campanii.values() if c["campaign_name"] == f.get("campaign_name")]
        elif colectie == "adgroup":
            lista = [g for g in self.grupuri.values() if g["campaign_id"] in f.get("campaign_ids", [])]
        else:
            lista = [a for a in self.reclame.values() if a["adgroup_id"] in f.get("adgroup_ids", [])]
        return self.raspuns(date={"list": lista})

    def _scrie(self, cale: str, c: dict[str, Any]) -> httpx.Response:
        if cale == "campaign/create/":
            if c.get("operation_status") != "DISABLE" or c.get("budget_mode") != "BUDGET_MODE_DAY":
                return self.raspuns(40002, "campania se creează oprită, cu buget pe zi")
            i = self._id()
            self.campanii[i] = {"campaign_id": i, **{k: v for k, v in c.items() if k != "advertiser_id"}}
            return self.raspuns(date={"campaign_id": i})
        if cale == "adgroup/create/":
            if c.get("campaign_id") not in self.campanii:
                return self.raspuns(40002, "campaign not found")
            i = self._id()
            self.grupuri[i] = {"adgroup_id": i, **{k: v for k, v in c.items() if k != "advertiser_id"}}
            return self.raspuns(date={"adgroup_id": i})
        if cale == "ad/create/":
            if c.get("adgroup_id") not in self.grupuri or not c.get("creatives"):
                return self.raspuns(40002, "adgroup not found")
            ids = []
            for cr in c["creatives"]:
                i = self._id()
                self.reclame[i] = {
                    "ad_id": i,
                    "adgroup_id": c["adgroup_id"],
                    "operation_status": "ENABLE",
                    **cr,
                }
                ids.append(i)
            return self.raspuns(date={"ad_ids": ids})
        if cale == "campaign/status/update/":
            for i in c["campaign_ids"]:
                self.campanii[i]["operation_status"] = c["operation_status"]
            return self.raspuns(date={"campaign_ids": c["campaign_ids"]})
        if cale == "ad/status/update/":
            for i in c["ad_ids"]:
                self.reclame[i]["operation_status"] = c["operation_status"]
            return self.raspuns(date={"ad_ids": c["ad_ids"]})
        if cale == "campaign/update/":
            self.campanii[c["campaign_id"]]["budget"] = c["budget"]
            return self.raspuns(date={"campaign_id": c["campaign_id"]})
        return self.raspuns(40002, "Unknown endpoint")

    def adauga_rand(self, nivel: str, id_ext: str, zi: str, cheltuiala: str, afisari: int, clicuri: int, conv: int,
                    nume: str = "Campanie", campanie: str = "") -> None:  # fmt: skip
        if nivel == "campanie":
            dim = {"campaign_id": id_ext, "stat_time_day": f"{zi} 00:00:00"}
            m = {"campaign_name": nume}
        else:
            dim = {"ad_id": id_ext, "stat_time_day": f"{zi} 00:00:00"}
            m = {"ad_name": nume, "campaign_id": campanie}
        m |= {
            "spend": cheltuiala,
            "impressions": str(afisari),
            "clicks": str(clicuri),
            "conversion": str(conv),
        }
        nivel_api = "AUCTION_CAMPAIGN" if nivel == "campanie" else "AUCTION_AD"
        self.raport.append({"data_level": nivel_api, "dimensions": dim, "metrics": m})
