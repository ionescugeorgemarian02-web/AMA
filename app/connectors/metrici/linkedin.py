"""Cititorul de metrici LinkedIn (F10.1).

- Profilul (`linkedin`): `GET /rest/socialActions/{urn}` dă doar aprecierile și comentariile. LinkedIn nu
  dă afișările unei postări de profil aplicațiilor self-serve: câmpul rămâne `None` (cifra se poate
  introduce de om, din aplicație).
- Pagina de companie (`linkedin_pagina`): `GET /rest/organizationalEntityShareStatistics` (afișări,
  afișări unice, clicuri, aprecieri, comentarii, distribuiri), cu Community Management API aprobat.

# NEVERIFICAT: forma exactă a răspunsurilor și parametrii Rest.li pe versiunea `AMA_LINKEDIN_VERSIUNE`;
accesul la statistici cere review. Testat pe API simulat (contract HTTP local).
"""

import uuid
from typing import Any
from urllib.parse import quote

import httpx

from app.config import get_settings
from app.connectors.contract import Metrici, Token
from app.connectors.publicare.baza import ClientHttp, DepozitBaza, DepozitTokenuri, token_sau_autentificare
from app.connectors.publicare.linkedin import API
from app.operare.motor import EroareDefinitiva

STATISTICI_PAGINA: dict[str, str] = {
    "impressionCount": "afisari",
    "uniqueImpressionsCount": "acoperire",
    "clickCount": "clicuri",
    "likeCount": "aprecieri",
    "commentCount": "comentarii",
    "shareCount": "distribuiri",
}


def _numar(v: Any) -> int | None:
    return int(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


class CititorLinkedin:
    def __init__(
        self,
        *,
        versiune: str,
        pagina: bool = False,
        depozit: DepozitTokenuri | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.versiune, self.pagina = versiune, pagina
        self.canal = "linkedin_pagina" if pagina else "linkedin"
        self.depozit = depozit or DepozitBaza()
        self.http = ClientHttp(API, transport)

    @classmethod
    def din_setari(cls, pagina: bool = False) -> "CititorLinkedin":
        return cls(versiune=get_settings().linkedin_versiune, pagina=pagina)

    @classmethod
    def pagina_din_setari(cls) -> "CititorLinkedin":
        return cls.din_setari(pagina=True)

    def _get(self, cale: str, token: Token, params: dict[str, str] | None = None) -> dict[str, Any]:
        r = self.http.cere(
            "GET",
            cale,
            token=token,
            params=params,
            headers={"LinkedIn-Version": self.versiune, "X-Restli-Protocol-Version": "2.0.0"},
        )
        return dict(r.json())

    def metrici(self, tenant_id: uuid.UUID, id_extern: str) -> Metrici:
        token = token_sau_autentificare(self.depozit, tenant_id, self.canal)
        if not self.pagina:
            r = self._get(f"rest/socialActions/{quote(id_extern, safe='')}", token)
            cifre = {
                "aprecieri": _numar((r.get("likesSummary") or {}).get("totalLikes")),
                "comentarii": _numar((r.get("commentsSummary") or {}).get("aggregatedTotalComments")),
            }
            return Metrici(**{k: v for k, v in cifre.items() if v is not None})
        r = self._get(
            "rest/organizationalEntityShareStatistics",
            token,
            {"q": "organizationalEntity", "organizationalEntity": token.cont_extern, "shares": id_extern},
        )
        elemente = r.get("elements") or []
        if not elemente:
            raise EroareDefinitiva("LinkedIn nu are statistici pentru această postare")
        st = elemente[0].get("totalShareStatistics") or {}
        valori = ((camp, _numar(st.get(nume))) for nume, camp in STATISTICI_PAGINA.items())
        return Metrici(**{camp: v for camp, v in valori if v is not None})
