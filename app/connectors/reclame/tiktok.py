"""Contul de reclame TikTok prin TikTok API for Business (Marketing API v1.3) (F16.6).

Citirea: `GET /report/integrated/get/` (`report_type=BASIC`, nivel campanie și reclamă, pe zi), cu paginare
(`page_info.total_page`); starea contului: `GET /advertiser/info/`. Scrierea (doar prin executantul efectelor
`reclama`, după gardianul de buget F13.5): campania se creează OPRITĂ (`operation_status=DISABLE`), apoi
grupul de
reclame și reclamele; schimbările de stare și buget prin `campaign/status/update`, `ad/status/update`,
`campaign/update`. Crearea e idempotentă pe nume (se caută întâi, ca la Meta).

API-ul răspunde mereu HTTP 200, cu `code` în corp: 0 = reușită; tokenul invalid sau expirat = autentificare;
limita de rată și erorile serverului = temporare; restul = definitive. Tokenul pleacă în antetul
`Access-Token`.
Bugetul e în unități ale monedei contului (lei, zecimal): se trimite și se citește în bani.

# NEVERIFICAT: codurile de eroare exacte, bugetul minim pe zi, creativul video obligatoriu (`video_id`), id-ul
locației România; accesul (aplicație aprobată în TikTok for Business). Testat pe API simulat (contract
HTTP local).
"""

import datetime as dt
import json
import uuid
from decimal import Decimal
from typing import Any

import httpx

from app.connectors.contract import RandReclame, RezultatPlatforma, StareCont, Token
from app.connectors.publicare.baza import ClientHttp, DepozitBaza, DepozitTokenuri, token_sau_autentificare
from app.connectors.reclame.google import numar_masurat
from app.connectors.reclame.meta import bani
from app.operare.motor import EroareAutentificare, EroareDefinitiva, EroareTemporara

BAZA = "https://business-api.tiktok.com/open_api/v1.3"
CANAL_TOKEN = "tiktok_ads"  # noqa: S105  (numele canalului din depozit, nu un secret)
COD_AUTENTIFICARE = {40001, 40104, 40105}  # [I]
COD_TEMPORAR = {40100, 40200, 50000, 50002}  # [I]
OBIECTIVE = {"lead": "LEAD_GENERATION", "trafic": "TRAFFIC"}
STARI = {"pauza": "DISABLE", "activa": "ENABLE"}
LOCATIE_RO = "798549"  # [I] id-ul geografic al României
METRICI = ["campaign_name", "spend", "impressions", "clicks", "conversion"]
PAGINI_MAXIME = 50


def clasifica_tiktok(r: httpx.Response) -> None:
    """Clasificarea pe `code` din corp (HTTP e 200 și la erori); HTTP ≥ 400 = clasificarea obișnuită."""
    if r.status_code >= 500 or r.status_code == 429:
        raise EroareTemporara(f"{r.status_code}")
    if r.status_code >= 400:
        raise EroareDefinitiva(f"{r.status_code}")
    try:
        corp = r.json()
    except ValueError:
        raise EroareTemporara("răspuns fără JSON") from None
    cod = int(corp.get("code", 0))
    if cod == 0:
        return
    m = f"{cod}: {str(corp.get('message', ''))[:200]}"
    if cod in COD_AUTENTIFICARE:
        raise EroareAutentificare(m)
    if cod in COD_TEMPORAR:
        raise EroareTemporara(m)
    raise EroareDefinitiva(m)


def lei(bani_: int) -> float:
    return float(Decimal(int(bani_)) / 100)


def rand_din_raport(r: dict[str, Any], nivel: str) -> RandReclame:
    """Nucleu pur: un rând din `report/integrated/get` -> `RandReclame`."""
    d, m = r.get("dimensions", {}), r.get("metrics", {})
    zi = dt.date.fromisoformat(str(d.get("stat_time_day", ""))[:10])
    id_ext = str(d.get("ad_id") if nivel == "reclama" else d.get("campaign_id"))
    return RandReclame(
        nivel=nivel,
        id_extern=id_ext,
        nume=str(m.get("ad_name") if nivel == "reclama" else m.get("campaign_name", "")) or "",
        zi=zi,
        cheltuiala_bani=bani(m.get("spend", "0")),
        afisari=int(float(m.get("impressions", 0) or 0)),
        clicuri=int(float(m.get("clicks", 0) or 0)),
        rezultate=numar_masurat(m.get("conversion")),
        clicuri_trafic=int(m["clicks"]) if str(m.get("clicks")).isdigit() else None,
        parinte_extern=str(m.get("campaign_id", "")) if nivel == "reclama" else "",
    )


class ContTiktok:
    platforma = "tiktok"

    def __init__(
        self, *, depozit: DepozitTokenuri | None = None, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.depozit = depozit or DepozitBaza()
        self.http = ClientHttp(BAZA, transport, clasificator=clasifica_tiktok)

    @classmethod
    def din_setari(cls) -> "ContTiktok":
        return cls()

    def _token(self, tenant_id: uuid.UUID) -> Token:
        return token_sau_autentificare(self.depozit, tenant_id, CANAL_TOKEN)

    def _cere(self, t: Token, metoda: str, cale: str, **kw: Any) -> dict[str, Any]:
        r = self.http.cere(metoda, cale, headers={"Access-Token": t.acces}, **kw)
        return dict(r.json().get("data") or {})

    # --- citire ---------------------------------------------------------------------------------------------
    def _raport(self, t: Token, cont: str, de_la: dt.date, pana_la: dt.date, nivel: str) -> list[RandReclame]:
        dim = ["ad_id" if nivel == "reclama" else "campaign_id", "stat_time_day"]
        metrici = METRICI + (["ad_name", "campaign_id"] if nivel == "reclama" else [])
        out: list[RandReclame] = []
        for pagina in range(1, PAGINI_MAXIME + 1):
            p = {
                "advertiser_id": cont,
                "report_type": "BASIC",
                "data_level": "AUCTION_AD" if nivel == "reclama" else "AUCTION_CAMPAIGN",
                "dimensions": json.dumps(dim),
                "metrics": json.dumps(metrici),
                "start_date": de_la.isoformat(),
                "end_date": pana_la.isoformat(),
                "page": str(pagina),
                "page_size": "200",
            }
            d = self._cere(t, "GET", "report/integrated/get/", params=p)
            out.extend(rand_din_raport(r, nivel) for r in d.get("list", []))
            if pagina >= int((d.get("page_info") or {}).get("total_page", 1)):
                return out
        raise EroareDefinitiva("prea multe pagini de rezultate")

    def rezultate(
        self, tenant_id: uuid.UUID, cont_extern: str, de_la: dt.date, pana_la: dt.date
    ) -> list[RandReclame]:
        t = self._token(tenant_id)
        return [
            *self._raport(t, cont_extern, de_la, pana_la, "campanie"),
            *self._raport(t, cont_extern, de_la, pana_la, "reclama"),
        ]

    def stare_cont(self, tenant_id: uuid.UUID, cont_extern: str) -> StareCont:
        d = self._cere(
            self._token(tenant_id),
            "GET",
            "advertiser/info/",
            params={"advertiser_ids": json.dumps([cont_extern])},
        )
        info = (d.get("list") or [{}])[0]
        s = str(info.get("status", ""))
        return StareCont(
            activ=s == "STATUS_ENABLE", motiv="" if s == "STATUS_ENABLE" else f"stare {s or 'necunoscută'}"
        )

    # --- scriere --------------------------------------------------------------------------------------------
    def _gaseste(
        self, t: Token, cont: str, colectie: str, camp: str, filtru: dict[str, Any]
    ) -> dict[str, str]:
        d = self._cere(
            t,
            "GET",
            f"{colectie}/get/",
            params={"advertiser_id": cont, "filtering": json.dumps(filtru), "page_size": "1000"},
        )
        return {str(o.get(f"{camp}_name")): str(o[f"{camp}_id"]) for o in d.get("list", [])}

    def scrie(self, tenant_id: uuid.UUID, payload: dict[str, Any]) -> RezultatPlatforma:
        t, cont, actiune = self._token(tenant_id), str(payload["cont_extern"]), payload["actiune"]
        if actiune == "creeaza_campanie":
            nume = str(payload["nume"])
            cid = self._gaseste(t, cont, "campaign", "campaign", {"campaign_name": nume}).get(nume) or str(
                self._cere(
                    t,
                    "POST",
                    "campaign/create/",
                    json={
                        "advertiser_id": cont,
                        "campaign_name": nume,
                        "objective_type": OBIECTIVE[str(payload["obiectiv"])],
                        "budget_mode": "BUDGET_MODE_DAY",
                        "budget": lei(payload["buget_zilnic_bani"]),
                        "operation_status": "DISABLE",
                    },
                )["campaign_id"]
            )
            grup = f"{nume} · grup"
            gid = self._gaseste(t, cont, "adgroup", "adgroup", {"campaign_ids": [cid]}).get(grup) or str(
                self._cere(
                    t,
                    "POST",
                    "adgroup/create/",
                    json={
                        "advertiser_id": cont,
                        "campaign_id": cid,
                        "adgroup_name": grup,
                        "placement_type": "PLACEMENT_TYPE_NORMAL",
                        "placements": ["PLACEMENT_TIKTOK"],
                        "location_ids": [LOCATIE_RO],
                        "budget_mode": "BUDGET_MODE_INFINITE",
                        "optimization_goal": "CLICK"
                        if payload["obiectiv"] == "trafic"
                        else "LEAD_GENERATION",
                        "billing_event": "CPC" if payload["obiectiv"] == "trafic" else "OCPM",
                        "schedule_type": "SCHEDULE_FROM_NOW",
                        "operation_status": "ENABLE",
                    },
                )["adgroup_id"]
            )

            harta = self._reclame(t, cont, gid, payload.get("reclame", []))
            return RezultatPlatforma(id_extern=cid, link=json.dumps({"reclame": harta}))
        obiect = str(payload["obiect_extern"])
        if actiune == "creeaza_anunt":
            grupuri = list(self._gaseste(t, cont, "adgroup", "adgroup", {"campaign_ids": [obiect]}).values())
            if not grupuri:
                raise EroareDefinitiva("campania nu are grup de reclame")
            return RezultatPlatforma(
                id_extern=self._reclame(t, cont, grupuri[0], [payload])[str(payload["nume"])]
            )
        if actiune == "stare_campanie":
            self._cere(
                t,
                "POST",
                "campaign/status/update/",
                json={
                    "advertiser_id": cont,
                    "campaign_ids": [obiect],
                    "operation_status": STARI[str(payload["stare"])],
                },
            )
        elif actiune == "stare_anunt":
            self._cere(
                t,
                "POST",
                "ad/status/update/",
                json={
                    "advertiser_id": cont,
                    "ad_ids": [obiect],
                    "operation_status": STARI[str(payload["stare"])],
                },
            )
        elif actiune == "buget_campanie":
            self._cere(
                t,
                "POST",
                "campaign/update/",
                json={
                    "advertiser_id": cont,
                    "campaign_id": obiect,
                    "budget": lei(payload["buget_zilnic_bani"]),
                },
            )
        else:
            raise EroareDefinitiva(f"acțiune necunoscută: {actiune}")
        return RezultatPlatforma(id_extern=obiect)

    def _reclame(self, t: Token, cont: str, gid: str, reclame: list[dict[str, Any]]) -> dict[str, str]:
        existente = self._gaseste(t, cont, "ad", "ad", {"adgroup_ids": [gid]})
        harta: dict[str, str] = {}
        for r in reclame:
            nume = str(r["nume"])
            if nume in existente:
                harta[nume] = existente[nume]
                continue
            d = self._cere(
                t,
                "POST",
                "ad/create/",
                json={
                    "advertiser_id": cont,
                    "adgroup_id": gid,
                    "creatives": [
                        {
                            "ad_name": nume,
                            "ad_text": f"{r['titlu']} {r['text']}"[:100],
                            "landing_page_url": r["link"],
                            "ad_format": "SINGLE_VIDEO",
                            "video_id": r.get("video_id", ""),
                        }
                    ],
                },
            )
            harta[nume] = str(d["ad_ids"][0])
        return harta
