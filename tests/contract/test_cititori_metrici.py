"""F10.1 — cititorii de metrici ai platformelor, pe API-uri simulate (# SIMULAT: `httpx.MockTransport`,
fără rețea). Fiecare cititor: traduce răspunsul platformei în `Metrici`, lasă `None` ce platforma nu dă,
trimite tokenul doar în antetul `Authorization` și clasifică erorile după 7.5."""

import datetime as dt
import json
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.connectors.contract import CititorMetrici, Metrici, Token
from app.connectors.metrici.linkedin import CititorLinkedin
from app.connectors.metrici.meta import CititorFacebook, CititorInstagram, din_insights
from app.connectors.metrici.tiktok import CititorTiktok
from app.connectors.metrici.youtube import CititorYoutube
from app.connectors.publicare import DepozitInMemorie
from app.ids import new_id
from app.operare.motor import EroareAutentificare, EroareDefinitiva, EroareTemporara

ACCES = "token-de-test-metrici"
Raspuns = Callable[[httpx.Request], httpx.Response]


class Platforma:
    """Înregistrează cererile și răspunde după cale."""

    def __init__(self, rute: dict[str, Any]) -> None:
        self.rute, self.cereri = rute, []  # type: ignore[var-annotated]

    def __call__(self, cerere: httpx.Request) -> httpx.Response:
        self.cereri.append(cerere)
        assert cerere.headers.get("authorization") == f"Bearer {ACCES}"
        assert ACCES not in str(cerere.url), "tokenul nu are voie în adresă"
        for fragment, raspuns in self.rute.items():
            if fragment in cerere.url.path:
                if callable(raspuns):
                    return raspuns(cerere)  # type: ignore[no-any-return]
                cod, corp = raspuns
                return httpx.Response(cod, json=corp)
        return httpx.Response(404, json={"error": {"message": "rută necunoscută", "code": 100}})

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def depozit(tenant: uuid.UUID, canal: str, cont: str = "cont-1") -> DepozitInMemorie:
    d = DepozitInMemorie()
    d.pune(tenant, canal, Token(ACCES, dt.datetime.now(dt.UTC) + dt.timedelta(days=30), "", cont))
    return d


def insights(**valori: int) -> dict[str, Any]:
    return {"data": [{"name": k, "values": [{"value": v}]} for k, v in valori.items()]}


# --- Facebook ---------------------------------------------------------------------------------------------
def test_facebook_afisari_acoperire_clicuri_si_interactiuni() -> None:
    t = new_id()
    p = Platforma(
        {
            "/123_456/insights": (
                200,
                insights(post_impressions=900, post_impressions_unique=640, post_clicks=31),
            ),
            "/123_456": (
                200,
                {
                    "shares": {"count": 7},
                    "comments": {"summary": {"total_count": 12}},
                    "reactions": {"summary": {"total_count": 88}},
                },
            ),
        }
    )
    c = CititorFacebook(depozit=depozit(t, "facebook"), transport=p.transport)
    assert isinstance(c, CititorMetrici)
    m = c.metrici(t, "123_456")
    assert m == Metrici(afisari=900, acoperire=640, clicuri=31, aprecieri=88, comentarii=12, distribuiri=7)
    assert m.vizualizari is None, "postare fără video: platforma nu dă cifra, deci nu apare"
    assert "post_impressions" in p.cereri[0].url.params["metric"]


def test_facebook_postare_stearsa_si_erori_clasificate() -> None:
    t = new_id()
    sters = Platforma({"/9_9": (400, {"error": {"code": 100, "message": "Object does not exist"}})})
    with pytest.raises(EroareDefinitiva):
        CititorFacebook(depozit=depozit(t, "facebook"), transport=sters.transport).metrici(t, "9_9")
    expirat = Platforma({"/9_9": (400, {"error": {"code": 190, "message": "token expirat"}})})
    with pytest.raises(EroareAutentificare):
        CititorFacebook(depozit=depozit(t, "facebook"), transport=expirat.transport).metrici(t, "9_9")
    limita = Platforma({"/9_9": (400, {"error": {"code": 4, "message": "limită de rată"}})})
    with pytest.raises(EroareTemporara):
        CititorFacebook(depozit=depozit(t, "facebook"), transport=limita.transport).metrici(t, "9_9")
    with pytest.raises(EroareAutentificare):  # cont neautorizat: nici nu se ajunge la platformă
        CititorFacebook(depozit=DepozitInMemorie(), transport=sters.transport).metrici(t, "9_9")


def test_insights_ignora_valorile_care_nu_sunt_numere() -> None:
    corp = {
        "data": [
            {"name": "reach", "total_value": {"value": 50}},
            {"name": "likes", "values": [{"value": {"like": 3}}]},
            {"name": "necunoscuta", "values": [{"value": 9}]},
            {"name": "saved", "values": []},
        ]
    }
    assert din_insights(corp, {"reach": "acoperire", "likes": "aprecieri", "saved": "salvari"}) == {
        "acoperire": 50
    }


# --- Instagram --------------------------------------------------------------------------------------------
def test_instagram_cifrele_unei_postari() -> None:
    t = new_id()
    p = Platforma(
        {
            "/1789/insights": (
                200,
                insights(views=2100, reach=1500, likes=140, comments=9, shares=22, saved=31),
            )
        }
    )
    m = CititorInstagram(depozit=depozit(t, "instagram"), transport=p.transport).metrici(t, "1789")
    assert m == Metrici(
        vizualizari=2100, acoperire=1500, aprecieri=140, comentarii=9, distribuiri=22, salvari=31
    )
    assert len(p.cereri) == 1


# --- YouTube ----------------------------------------------------------------------------------------------
class Contor:
    def __init__(self) -> None:
        self.n = 0

    def consumat(self, platforma: str, zi: dt.date) -> int:
        return self.n

    def adauga(self, platforma: str, zi: dt.date, unitati: int) -> None:
        self.n += unitati


def test_youtube_statistici_si_cota_in_unitati() -> None:
    t = new_id()
    stat = {"items": [{"statistics": {"viewCount": "3400", "likeCount": "210", "commentCount": "18"}}]}
    p = Platforma({"/youtube/v3/videos": (200, stat)})
    contor = Contor()
    c = CititorYoutube(
        costuri_unitati={"videos.list": 1},
        cota_zi=2,
        depozit=depozit(t, "youtube"),
        contor=contor,
        transport=p.transport,
    )
    assert c.metrici(t, "vid1") == Metrici(vizualizari=3400, aprecieri=210, comentarii=18)
    assert p.cereri[0].url.params["part"] == "statistics" and p.cereri[0].url.params["id"] == "vid1"
    c.metrici(t, "vid1")
    assert contor.n == 2
    with pytest.raises(EroareTemporara):  # cota zilei e epuizată: nu se mai face cererea
        c.metrici(t, "vid1")
    assert len(p.cereri) == 2


def test_youtube_clip_sters_si_aprecieri_ascunse() -> None:
    t = new_id()
    gol = Platforma({"/youtube/v3/videos": (200, {"items": []})})
    with pytest.raises(EroareDefinitiva):
        CititorYoutube(depozit=depozit(t, "youtube"), contor=Contor(), transport=gol.transport).metrici(
            t, "x"
        )
    ascuns = Platforma({"/youtube/v3/videos": (200, {"items": [{"statistics": {"viewCount": "10"}}]})})
    m = CititorYoutube(depozit=depozit(t, "youtube"), contor=Contor(), transport=ascuns.transport).metrici(
        t, "x"
    )
    assert m == Metrici(vizualizari=10) and m.aprecieri is None


# --- LinkedIn ---------------------------------------------------------------------------------------------
def test_linkedin_profil_da_doar_aprecieri_si_comentarii() -> None:
    t = new_id()
    p = Platforma(
        {
            "/rest/socialActions/": (
                200,
                {"likesSummary": {"totalLikes": 41}, "commentsSummary": {"aggregatedTotalComments": 6}},
            )
        }
    )
    c = CititorLinkedin(versiune="202510", depozit=depozit(t, "linkedin"), transport=p.transport)
    m = c.metrici(t, "urn:li:share:77")
    assert m == Metrici(aprecieri=41, comentarii=6) and m.afisari is None
    assert p.cereri[0].headers["linkedin-version"] == "202510"
    assert "urn%3Ali%3Ashare%3A77" in p.cereri[0].url.raw_path.decode()


def test_linkedin_pagina_statistici_complete() -> None:
    t = new_id()
    st = {
        "impressionCount": 1200,
        "uniqueImpressionsCount": 800,
        "clickCount": 45,
        "likeCount": 30,
        "commentCount": 4,
        "shareCount": 3,
        "engagement": 0.07,
    }
    p = Platforma(
        {"/rest/organizationalEntityShareStatistics": (200, {"elements": [{"totalShareStatistics": st}]})}
    )
    c = CititorLinkedin(
        versiune="202510",
        pagina=True,
        depozit=depozit(t, "linkedin_pagina", "urn:li:organization:5"),
        transport=p.transport,
    )
    assert c.canal == "linkedin_pagina"
    assert c.metrici(t, "urn:li:share:77") == Metrici(
        afisari=1200, acoperire=800, clicuri=45, aprecieri=30, comentarii=4, distribuiri=3
    )
    assert p.cereri[0].url.params["organizationalEntity"] == "urn:li:organization:5"
    fara = Platforma({"/rest/organizationalEntityShareStatistics": (200, {"elements": []})})
    c2 = CititorLinkedin(
        versiune="202510", pagina=True, depozit=depozit(t, "linkedin_pagina"), transport=fara.transport
    )
    with pytest.raises(EroareDefinitiva):
        c2.metrici(t, "urn:li:share:77")


# --- TikTok -----------------------------------------------------------------------------------------------
def ok(date: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    return 200, {"data": date, "error": {"code": "ok"}}


def test_tiktok_de_la_publicare_la_cifrele_clipului() -> None:
    t = new_id()
    clip = {"id": "7001", "view_count": 5200, "like_count": 310, "comment_count": 14, "share_count": 25}
    p = Platforma(
        {
            "/v2/post/publish/status/fetch/": ok(
                {"status": "PUBLISH_COMPLETE", "publicaly_available_post_id": [7001]}
            ),
            "/v2/video/query/": ok({"videos": [clip]}),
        }
    )
    m = CititorTiktok(depozit=depozit(t, "tiktok"), transport=p.transport).metrici(t, "pub-1")
    assert m == Metrici(vizualizari=5200, aprecieri=310, comentarii=14, distribuiri=25)
    assert json.loads(p.cereri[0].content) == {"publish_id": "pub-1"}
    assert json.loads(p.cereri[1].content) == {"filters": {"video_ids": ["7001"]}}
    assert "view_count" in p.cereri[1].url.params["fields"]


def test_tiktok_ciorna_si_publicare_esuata_nu_au_cifre() -> None:
    t = new_id()
    for stare in ("SEND_TO_USER_INBOX", "FAILED", "PROCESSING_DOWNLOAD"):
        p = Platforma({"/v2/post/publish/status/fetch/": ok({"status": stare})})
        with pytest.raises(EroareDefinitiva):
            CititorTiktok(depozit=depozit(t, "tiktok"), transport=p.transport).metrici(t, "pub-1")
        assert len(p.cereri) == 1, "fără clip public nu se cer cifre"
    expirat = Platforma(
        {"/v2/post/publish/status/fetch/": (401, {"error": {"code": "access_token_invalid", "message": "x"}})}
    )
    with pytest.raises(EroareAutentificare):
        CititorTiktok(depozit=depozit(t, "tiktok"), transport=expirat.transport).metrici(t, "pub-1")
