"""Cititorul de metrici TikTok (F10.1): `POST /v2/video/query/` (Display API, permisiunea `video.list`).

Identificatorul ținut de noi este cel al publicării (`publish_id`, F9.6), nu al clipului: întâi se citește
starea publicării (`status/fetch`) ca să aflăm identificatorul clipului public, apoi cifrele lui
(vizualizări, aprecieri, comentarii, distribuiri). O ciornă nepublicată încă de om sau o publicare eșuată nu
are clip public → `EroareDefinitiva`: intervalul acesta rămâne fără cifre, iar colectorul întreabă din nou la
intervalul următor (o întrebare pe interval, nu una la fiecare rulare).

# NEVERIFICAT: câmpurile `video/query` pe un cont real și numele câmpului cu identificatorul public
(`publicaly_available_post_id`, scris așa în documentația TikTok). Testat pe API simulat.
"""

import uuid
from typing import Any

import httpx

from app.connectors.contract import Metrici, Token
from app.connectors.publicare.baza import ClientHttp, DepozitBaza, DepozitTokenuri, token_sau_autentificare
from app.connectors.publicare.tiktok import API, clasifica_tiktok
from app.operare.motor import EroareDefinitiva

CAMPURI: dict[str, str] = {
    "view_count": "vizualizari",
    "like_count": "aprecieri",
    "comment_count": "comentarii",
    "share_count": "distribuiri",
}


class CititorTiktok:
    canal = "tiktok"

    def __init__(
        self, *, depozit: DepozitTokenuri | None = None, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.depozit = depozit or DepozitBaza()
        self.http = ClientHttp(API, transport, clasificator=clasifica_tiktok)

    @classmethod
    def din_setari(cls) -> "CititorTiktok":
        return cls()

    def _post(self, cale: str, token: Token, corp: dict[str, Any], **params: str) -> dict[str, Any]:
        r = self.http.cere("POST", cale, token=token, json=corp, params=params or None)
        return dict(r.json().get("data") or {})

    def metrici(self, tenant_id: uuid.UUID, id_extern: str) -> Metrici:
        token = token_sau_autentificare(self.depozit, tenant_id, self.canal)
        stare = self._post("v2/post/publish/status/fetch/", token, {"publish_id": id_extern})
        if stare.get("status") == "FAILED":
            raise EroareDefinitiva("publicarea TikTok a eșuat; nu există clip de măsurat")
        ids = stare.get("publicaly_available_post_id") or []
        if not ids:
            raise EroareDefinitiva("clipul TikTok nu e încă public (ciornă sau în procesare)")
        d = self._post(
            "v2/video/query/",
            token,
            {"filters": {"video_ids": [str(ids[0])]}},
            fields="id," + ",".join(CAMPURI),
        )
        clipuri = d.get("videos") or []
        if not clipuri:
            raise EroareDefinitiva("clipul TikTok nu mai există")
        cifre = {
            camp: int(v)
            for nume, camp in CAMPURI.items()
            if isinstance(v := clipuri[0].get(nume), int) and not isinstance(v, bool)
        }
        return Metrici(**cifre)
