"""# SIMULAT: Meta Marketing API (contul de reclame), ca server HTTP local. Forma urmează documentația publică:
`/act_<id>/insights` (cheltuiala ca text zecimal, `actions`, paginare `paging.next`), `/act_<id>/campaigns`,
`/act_<id>/adsets`, `/act_<id>/ads` (creare), `POST /<id>` (actualizare), `GET /<id>` (citire), erorile Graph.

Platforma „cheltuie” singură când testul cere `zi(…)`: fiecare campanie ACTIVĂ cheltuie cel mult bugetul zilnic,
cu ritmul dat de `ritm` (1.0 = tot bugetul). Ce ar arăta managerul de reclame se calculează separat, din
evidența proprie (`manager`), ca testele să compare panoul cu „adevărul” platformei."""

import datetime as dt
import json
import secrets
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import httpx

from tests.platforme.baza import PlatformaHttp

VERSIUNE = "v23.0"
BAZA = f"https://graph.facebook.com/{VERSIUNE}"


class MarketingSimulat(PlatformaHttp):
    def __init__(self, cont: str = "act_1001") -> None:
        super().__init__()
        self.cont = cont
        self.stare_cont = 1
        self.obiecte: dict[str, dict[str, Any]] = {}  # id → campanie / set de reclame / reclamă
        self.zile: dict[tuple[str, dt.date], dict[str, int]] = {}  # (id reclamă, zi) → cifre
        self.pe_pagina = 2  # rânduri pe pagina de insights (paginarea se vede repede)
        self.scrieri: list[dict[str, Any]] = []

    # --- controlul testului ---------------------------------------------------------------------------------
    def campanii(self) -> list[dict[str, Any]]:
        return [o for o in self.obiecte.values() if o["tip"] == "campaign"]

    def reclame(self, campanie: str | None = None) -> list[dict[str, Any]]:
        return [o for o in self.obiecte.values() if o["tip"] == "ad" and campanie in (None, o["campaign_id"])]

    def adauga_campanie(self, nume: str, buget_bani: int, stare: str = "ACTIVE") -> str:
        cid = self._id()
        self.obiecte[cid] = {
            "tip": "campaign",
            "id": cid,
            "name": nume,
            "status": stare,
            "daily_budget": buget_bani,
            "objective": "OUTCOME_LEADS",
        }
        aid = self._id()
        self.obiecte[aid] = {
            "tip": "ad",
            "id": aid,
            "name": f"{nume} · reclama",
            "status": "ACTIVE",
            "campaign_id": cid,
        }
        return cid

    def inregistreaza(
        self, ad_id: str, zi: dt.date, *, bani: int, afisari: int, clicuri: int, rezultate: int
    ) -> None:
        z = self.zile.setdefault((ad_id, zi), {"bani": 0, "afisari": 0, "clicuri": 0, "rezultate": 0})
        for k, v in (("bani", bani), ("afisari", afisari), ("clicuri", clicuri), ("rezultate", rezultate)):
            z[k] += v

    def zi(
        self,
        zi: dt.date,
        *,
        ritm: float = 1.0,
        cpm_bani: int = 2000,
        ctr: float = 0.015,
        conversie: float = 0.08,
        fractiune: float = 1.0,
    ) -> None:
        """Cheltuiala unei zile (sau a unei fracțiuni de zi) pe campaniile active, împărțită egal pe reclame."""
        for c in self.campanii():
            ads = [a for a in self.reclame(c["id"]) if a["status"] == "ACTIVE"]
            if c["status"] != "ACTIVE" or not ads:
                continue
            total = int(c["daily_budget"] * ritm * fractiune)
            for a in ads:
                bani = total // len(ads)
                afis = bani * 1000 // max(1, int(a.get("cpm_bani", cpm_bani)))
                clic = int(afis * float(a.get("ctr", ctr)))
                self.inregistreaza(
                    a["id"],
                    zi,
                    bani=bani,
                    afisari=afis,
                    clicuri=clic,
                    rezultate=int(clic * float(a.get("conversie", conversie))),
                )

    def manager(self, de_la: dt.date, pana_la: dt.date) -> dict[str, int]:
        """Totalul contului, cum îl arată managerul de reclame (din evidența platformei)."""
        t = {"bani": 0, "afisari": 0, "clicuri": 0, "rezultate": 0}
        for (_, zi), v in self.zile.items():
            if de_la <= zi <= pana_la:
                for k in t:
                    t[k] += v[k]
        return t

    def cheltuit_pe_zi(self, zi: dt.date) -> dict[str, int]:
        """Cheltuiala pe campanie într-o zi."""
        out: dict[str, int] = {}
        for (aid, z), v in self.zile.items():
            if z == zi:
                c = self.obiecte[aid]["campaign_id"]
                out[c] = out.get(c, 0) + v["bani"]
        return out

    # --- erori ----------------------------------------------------------------------------------------------
    @staticmethod
    def eroare(cod_http: int, cod: int, mesaj: str, **extra: Any) -> httpx.Response:
        return httpx.Response(
            cod_http, json={"error": {"message": mesaj, "type": "OAuthException", "code": cod, **extra}}
        )

    @staticmethod
    def _id() -> str:
        return str(23850000000000000 + secrets.randbelow(10**12))

    # --- rute -----------------------------------------------------------------------------------------------
    def trateaza(self, req: httpx.Request) -> httpx.Response:
        if not self.autorizat(req):
            return self.eroare(400, 190, "Invalid OAuth access token.")
        d = self.defect()
        if d == "temporar":
            return self.eroare(500, 2, "Service temporarily unavailable", is_transient=True)
        if d == "timeout":
            return self.timeout(req)
        cale = req.url.path.removeprefix(f"/{VERSIUNE}/")
        p = dict(req.url.params) | self.corp(req)
        if cale == f"{self.cont}/insights":
            return self._insights(p)
        if cale == self.cont:
            return self.json(200, {"id": self.cont, "account_status": self.stare_cont, "disable_reason": 0})
        if req.method == "GET" and cale == f"{self.cont}/campaigns":
            return self.json(200, {"data": [self._public(o) for o in self.campanii()]})
        if req.method == "POST" and cale.startswith(f"{self.cont}/"):
            return self._creeaza(cale.split("/")[1], p, d)
        parti = cale.split("/")
        if (
            req.method == "GET"
            and len(parti) == 2
            and parti[0] in self.obiecte
            and parti[1] in ("adsets", "ads")
        ):
            tip = parti[1].removesuffix("s")
            copii = [
                self._public(o)
                for o in self.obiecte.values()
                if o["tip"] == tip and o.get("campaign_id") == parti[0]
            ]
            return self.json(200, {"data": copii})
        if cale in self.obiecte:
            o = self.obiecte[cale]
            if req.method == "GET":
                return self.json(200, self._public(o))
            return self._actualizeaza(o, p, d)
        if cale.startswith("act_"):
            return self.eroare(400, 100, "Unsupported request: ad account does not exist")
        return self.eroare(400, 100, "Unsupported get request. Object does not exist")

    @staticmethod
    def _public(o: dict[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in o.items() if k not in ("tip", "cpm_bani", "ctr", "conversie")}
        if "daily_budget" in out:
            out["daily_budget"] = str(out["daily_budget"])
        return out

    def _creeaza(self, colectie: str, p: dict[str, Any], d: str) -> httpx.Response:
        tip = {"campaigns": "campaign", "adsets": "adset", "ads": "ad"}.get(colectie)
        if tip is None:
            return self.eroare(400, 100, "Unsupported post request")
        if tip == "campaign" and "special_ad_categories" not in p:
            return self.eroare(400, 100, "Invalid parameter: special_ad_categories is required")
        if p.get("status") not in ("PAUSED", "ACTIVE"):
            return self.eroare(400, 100, "Invalid parameter: status")
        oid = self._id()
        o: dict[str, Any] = {"tip": tip, "id": oid, "name": str(p.get("name", "")), "status": p["status"]}
        if tip == "campaign":
            o |= {"daily_budget": int(p.get("daily_budget", 0)), "objective": p.get("objective", "")}
        elif tip == "adset":
            o |= {"campaign_id": str(p["campaign_id"])}
        else:
            parinte = self.obiecte.get(str(p.get("adset_id")))
            if parinte is None:
                return self.eroare(400, 100, "Invalid parameter: adset_id")
            creativ = p.get("creative")
            o |= {
                "adset_id": parinte["id"],
                "campaign_id": parinte["campaign_id"],
                "creative": json.loads(creativ) if isinstance(creativ, str) else creativ,
            }
        self.obiecte[oid] = o
        self.scrieri.append({"creat": tip, "id": oid, **p})
        if d == "pierde_raspunsul":
            raise httpx.ReadTimeout("simulat: răspuns pierdut")
        return self.json(200, {"id": oid})

    def _actualizeaza(self, o: dict[str, Any], p: dict[str, Any], d: str) -> httpx.Response:
        if "status" in p:
            if p["status"] not in ("PAUSED", "ACTIVE", "ARCHIVED"):
                return self.eroare(400, 100, "Invalid parameter: status")
            o["status"] = p["status"]
        if "daily_budget" in p:
            o["daily_budget"] = int(p["daily_budget"])
        self.scrieri.append({"actualizat": o["id"], **dict(p)})
        if d == "pierde_raspunsul":
            raise httpx.ReadTimeout("simulat: răspuns pierdut")
        return self.json(200, {"success": True})

    def _insights(self, p: dict[str, Any]) -> httpx.Response:
        interval = json.loads(p["time_range"])
        de_la, pana_la = dt.date.fromisoformat(interval["since"]), dt.date.fromisoformat(interval["until"])
        pe_reclama = p.get("level") == "ad"
        grup: dict[tuple[str, dt.date], dict[str, int]] = {}
        for (aid, zi), v in sorted(self.zile.items(), key=lambda x: (x[0][1], x[0][0])):
            if not de_la <= zi <= pana_la:
                continue
            cheie = (aid if pe_reclama else self.obiecte[aid]["campaign_id"], zi)
            g = grup.setdefault(cheie, {"bani": 0, "afisari": 0, "clicuri": 0, "rezultate": 0})
            for k in g:
                g[k] += v[k]
        randuri = []
        for (oid, zi), v in grup.items():
            o = self.obiecte[oid]
            c = self.obiecte[o["campaign_id"]] if pe_reclama else o
            r: dict[str, Any] = {
                "campaign_id": c["id"],
                "campaign_name": c["name"],
                "date_start": zi.isoformat(),
                "date_stop": zi.isoformat(),
                "spend": str(Decimal(v["bani"]) / 100),
                "impressions": str(v["afisari"]),
                "clicks": str(v["clicuri"]),
            }
            r["inline_link_clicks"] = str(v["clicuri"])
            r["actions"] = [
                {"action_type": "link_click", "value": str(v["clicuri"])},
                {"action_type": "lead", "value": str(v["rezultate"])},
            ]
            if pe_reclama:
                r |= {"ad_id": oid, "ad_name": o["name"]}
            randuri.append(r)
        start = int(p.get("after", 0))
        pagina = randuri[start : start + self.pe_pagina]
        corp: dict[str, Any] = {"data": pagina, "paging": {}}
        if start + self.pe_pagina < len(randuri):
            q = {k: v for k, v in p.items() if k != "after"} | {"after": str(start + self.pe_pagina)}
            corp["paging"]["next"] = f"{BAZA}/{self.cont}/insights?{urlencode(q)}"
        return self.json(200, corp)
