"""Poarta F9: pe fiecare canal aprobat, o postare publică pleacă prin API, o singură dată. Canalele
neaprobate rămân pe asistat.

Clientul e brandul FICTIV „Cafeneaua Zorilor” (cont de client, nu al agenției: fără aprobare, asistat).
Aprobările Meta (pagini, Instagram), auditul YouTube și auditul TikTok sunt „aprobate”; Community Management
API (pagina de LinkedIn) NU. Drumul complet, fără om după aprobare: OAuth prin executor → versiunea aprobată
→ alegerea drumului după modul canalului → slotul (F9.7) → la minut → executorul de efecte, ca joburi
durabile pe motorul real (în proces) → conectorul → platforma. Un răspuns pierdut la Facebook nu dublează
postarea. Platformele sunt SIMULATE (contracte HTTP locale, # SIMULAT); blogul găzduit e real; modelul
articolului e FALS (ca în F7.10)."""

# ruff: noqa: F811
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app import media, productie, publicare, seo, validare
from app.config import get_settings
from app.connectors import registru
from app.connectors.contract import StarePostare
from app.connectors.publicare.blog import ConectorBlog
from app.connectors.publicare.facebook import ConectorFacebook
from app.connectors.publicare.instagram import ConectorInstagram
from app.connectors.publicare.linkedin import ConectorLinkedin
from app.connectors.publicare.tiktok import ConectorTiktok
from app.connectors.publicare.youtube import ConectorYoutube, costuri
from app.conturi import Rol
from app.db import sesiune_tenant
from app.operare import efecte
from app.operare.efecte import autorizare
from app.productie import Hotarare
from app.productie.stari import Stare
from app.publicare import blog, canale, consimtamant, linkuri, programare
from tests.integration.publicare_utile import autorizeaza, livrabil_stare, pune_aprobarea
from tests.integration.test_seo_articole import CUVINTE, SURSE, scriptat
from tests.integration.utile_productie import fabrica_clienti, livrabil, muta, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele  # noqa: F401
from tests.platforme import google, linkedin, meta, tiktok

pytestmark = pytest.mark.db
APROBATE = (("meta", "pagini"), ("meta", "instagram"), ("google", "youtube"), ("tiktok", "publicare"))


class Platforme:
    def __init__(self, client: TestClient) -> None:
        def descarca(url: str) -> int:  # platforma aduce fișierul de la linkul semnat (ruta, testată în F9.3)
            return 200 if linkuri.verifica(urlsplit(url).path.rsplit("/", 1)[1]) else 404

        self.graph, self.yt, self.li, self.tt = (
            meta.GraphSimulat(),
            google.YoutubeSimulat(),
            linkedin.LinkedinSimulat(),
            tiktok.TiktokSimulat(),
        )
        self.graph.descarca = self.tt.descarca = descarca
        self.yt.auditat = self.tt.auditat = True
        fara_pauze: dict[str, Any] = {"dormi": lambda s: None}
        conectori: list[Any] = [
            ConectorFacebook(app_id=meta.APP_ID, app_secret=meta.APP_SECRET, transport=self.graph.transport),
            ConectorInstagram(
                app_id=meta.APP_ID, app_secret=meta.APP_SECRET, transport=self.graph.transport, **fara_pauze
            ),
            ConectorYoutube(
                client_id=google.CLIENT_ID,
                client_secret=google.CLIENT_SECRET,
                transport=self.yt.transport,
                costuri_unitati=costuri("videos.insert=1600"),
            ),
            ConectorLinkedin(
                client_id=linkedin.CLIENT_ID,
                client_secret=linkedin.CLIENT_SECRET,
                transport=self.li.transport,
            ),
            ConectorLinkedin(
                client_id=linkedin.CLIENT_ID,
                client_secret=linkedin.CLIENT_SECRET,
                pagina=True,
                transport=self.li.transport,
            ),
            ConectorTiktok(
                client_key=tiktok.CLIENT_KEY,
                client_secret=tiktok.CLIENT_SECRET,
                transport=self.tt.transport,
                **fara_pauze,
            ),
            ConectorBlog(),
        ]
        for c in conectori:
            registru.inregistreaza(c.canal, c)

    def cod(self, canal: str) -> str:
        return {
            "facebook": self.graph,
            "instagram": self.graph,
            "youtube": self.yt,
            "linkedin": self.li,
            "linkedin_pagina": self.li,
            "tiktok": self.tt,
        }[canal].cod_valid()


@pytest.fixture
def platforme(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, client: TestClient) -> Iterator[Platforme]:
    monkeypatch.setenv("AMA_MEDIA_DIR", str(tmp_path / "media"))
    get_settings.cache_clear()
    registru.uita_tot()
    for a in APROBATE:
        pune_aprobarea(*a, "aprobata")
    try:
        yield Platforme(client)
    finally:
        for a in APROBATE:
            pune_aprobarea(*a, "in_test")
        registru.uita_tot()
        get_settings.cache_clear()


def aprobat(
    tenant: uuid.UUID, om: uuid.UUID, canal: str, text: str, fisier: bytes | None = None
) -> uuid.UUID:
    lid = livrabil(
        tenant, canal=canal, tip="video" if fisier and not fisier.startswith(b"\xff") else "postare"
    )
    curenta = Stare.PLANIFICAT
    for s in (Stare.BRIEFAT, Stare.IN_SCRIERE, Stare.IN_VALIDARE, Stare.VALIDAT):
        muta(tenant, lid, curenta, s)
        curenta = s
    with sesiune_tenant(tenant) as db:
        active = []
        if fisier:
            a = media.biblioteca.incarca(
                db, tenant, fisier, nume_original=f"{canal}.bin", sursa="portal", utilizator_id=om
            )
            active = [{"activ_id": str(a.id)}]
        ap = productie.aprobari.cere(db, lid)
        productie.aprobari.decide(
            db, ap.id, Hotarare.APROBAT, utilizator_id=om, rol=Rol.PROPRIETAR, versiune=1
        )
        # conținutul versiunii aprobate (validarea e a F5; aici contează doar ce pleacă)
        validare.continut.scrie(
            db,
            lid,
            text=text,
            campuri={"titlu": text[:60], "hashtaguri": ["cafea"]},
            active=active,
            autor="test",
        )
    return lid


def asteapta_publicarea(tenant: uuid.UUID, lids: list[uuid.UUID], secunde: float = 60.0) -> None:
    limita = time.monotonic() + secunde
    while time.monotonic() < limita:
        if all(livrabil_stare(tenant, lid) == "publicat" for lid in lids):
            return
        time.sleep(0.1)
    raise AssertionError({str(lid): livrabil_stare(tenant, lid) for lid in lids})


def test_poarta_f9_o_postare_publica_pe_fiecare_canal_aprobat_o_singura_data(
    client: TestClient,
    tenant: uuid.UUID,
    om: uuid.UUID,
    platforme: Platforme,
    modele: ModelFals,
    executor: None,
) -> None:
    p = platforme
    jpeg, mp4 = b"\xff\xd8\xff\xe0 Cafeneaua Zorilor", b"\x00\x00\x00\x18ftypmp42 Cafeneaua Zorilor"
    # conturile clientului, autorizate prin OAuth (prin executor); blogul: găzduit
    for canal in ("facebook", "instagram", "youtube", "linkedin", "linkedin_pagina", "tiktok"):
        autorizeaza(tenant, om, canal, p.cod(canal), agentie=False)
    with sesiune_tenant(tenant, om) as db:
        blog.configureaza_gazduit(db, tenant, utilizator_id=om)
        moduri = {
            c: canale.mod(db, tenant, c)
            for c in ("facebook", "instagram", "youtube", "linkedin", "linkedin_pagina", "tiktok", "blog")
        }
    assert all(m.automat and not m.restrans for c, m in moduri.items() if c != "linkedin_pagina"), moduri
    assert moduri["linkedin_pagina"].mod is canale.Mod.ASISTAT, "Community Management API neaprobat"
    # versiunile aprobate, câte una pe canal (inclusiv pagina de LinkedIn, neaprobată)
    lids = {
        "facebook": aprobat(tenant, om, "facebook", "Cafeneaua Zorilor: espresso la 7."),
        "instagram": aprobat(tenant, om, "instagram", "Cafeneaua Zorilor: croissant.", jpeg),
        "youtube": aprobat(tenant, om, "youtube", "Cafeneaua Zorilor: flat white.", mp4),
        "linkedin": aprobat(tenant, om, "linkedin", "Cafeneaua Zorilor angajează un barista."),
        "linkedin_pagina": aprobat(tenant, om, "linkedin_pagina", "Cafeneaua Zorilor, pagina companiei."),
        "tiktok": aprobat(tenant, om, "tiktok", "Cafeneaua Zorilor: latte art.", mp4 + b" tiktok"),
    }
    scriptat(modele)
    with sesiune_tenant(tenant, om) as db:
        r = seo.articole.scrie(db, tenant, seo.cuvinte.grupeaza(CUVINTE)[0], SURSE, publica=False)
        lids["blog"] = blog.pregateste(db, tenant, r, utilizator_id=om)
        ap = productie.aprobari.cerere_activa(db, lids["blog"])
        assert ap is not None
        productie.aprobari.decide(
            db, ap.id, Hotarare.APROBAT, utilizator_id=om, rol=Rol.PROPRIETAR, versiune=1
        )
    # TikTok direct: previzualizarea și consimțământul omului, cu vizibilitatea aleasă
    with sesiune_tenant(tenant) as db:
        consimtamant.inregistreaza(
            db,
            lids["tiktok"],
            optiuni={"vizibilitate": "PUBLIC_TO_EVERYONE"},
            creator=autorizare.previzualizare(tenant, "tiktok"),
            de_acord=True,
            utilizator_id=om,
        )
    # alegerea drumului după modul canalului: prin API sau asistat
    with sesiune_tenant(tenant) as db:
        drumuri = {
            c: programare.alege_drumul(db, lid, utilizator_id=om) for c, lid in lids.items() if c != "blog"
        }
        [p_blog] = programare.a_livrabilului(db, lids["blog"])  # blogul: programat chiar de aprobare
    assert drumuri == {c: ("asistat" if c == "linkedin_pagina" else "api") for c in drumuri}, drumuri
    api = [lid for c, lid in lids.items() if c != "linkedin_pagina"]
    with sesiune_tenant(tenant) as db:
        la = max(x.la for lid in api for x in programare.a_livrabilului(db, lid))
    assert p_blog.la <= la
    p.graph.injecteaza("pierde_raspunsul")  # Facebook: postarea se face, răspunsul se pierde
    assert programare.tic_acum(la) == {"plecat": len(api)}
    asteapta_publicarea(tenant, api)
    # o singură dată și după o nouă trecere a „tic”-urilor (programare și executor)
    assert programare.tic_acum(la) == {} and efecte.redistribuie() == 0
    assert [x["text"] for x in p.graph.postari if "_" in x["id"]] == [
        "Cafeneaua Zorilor: espresso la 7.\n\n#cafea"
    ]
    assert [x["tip"] for x in p.graph.ig_media] == ["IMAGE"]
    assert [(x["titlu"], x["vizibilitate"]) for x in p.yt.postari] == [
        ("Cafeneaua Zorilor: flat white.", "public")
    ]
    assert [x["author"] for x in p.li.postari] == [p.li.persoana], "nimic pe pagina de companie neaprobată"
    assert [x["privacy"] for x in p.tt.postari] == ["PUBLIC_TO_EVERYONE"] and p.tt.ciorne == []
    assert client.get(f"/site/blog/{r['slug']}").status_code == 200
    # publică, la platformă, cu linkul în sistem
    with sesiune_tenant(tenant) as db:
        for c, lid in lids.items():
            if c == "linkedin_pagina":
                continue
            [e] = efecte.ale_livrabilului(db, lid)
            assert (
                e.stare == "trimis" and e.id_extern and (e.link or "").startswith(("https://", "http://"))
            ), c
            assert autorizare.stare_postare(tenant, c, e.id_extern) is StarePostare.PUBLICATA, c
    # canalul neaprobat a rămas pe asistat: pachetul e pe telefon, nimic nu a plecat prin API
    with sesiune_tenant(tenant) as db:
        pachet = publicare.asistata.al_versiunii(db, lids["linkedin_pagina"], 1)
        assert pachet is not None and pachet.stare == "pregatit"
        assert efecte.ale_livrabilului(db, lids["linkedin_pagina"]) == []
    assert livrabil_stare(tenant, lids["linkedin_pagina"]) == "programat"
