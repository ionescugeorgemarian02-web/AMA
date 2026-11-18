"""Poarta F16 — extensiile, cap-coadă pe simulare (D-026): un client care publică în engleză primește un video
format C, cu vocea proprie a vorbitorului care și-a dat acordul și un insert generat în buget; postarea trece
validarea pe engleză și pleacă pe Pinterest, Google Business Profile și Threads prin executorul de efecte; o
campanie TikTok se construiește oprită și pornește doar prin gardianul de buget. Fiecare pas lasă urmă (FT)."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import Engine, text

from app import localizare
from app.config import get_settings
from app.connectors import reclame as registru_reclame
from app.connectors import registru
from app.connectors.contract import Token
from app.connectors.publicare.baza import DepozitInMemorie
from app.connectors.publicare.google_business import ConectorGoogleBusiness
from app.connectors.publicare.pinterest import ConectorPinterest
from app.connectors.publicare.threads import ConectorThreads
from app.connectors.reclame.tiktok import CANAL_TOKEN, ContTiktok
from app.db import sesiune_agentie, sesiune_tenant
from app.media import ffmpeg, formatul_c, licente, video_extern, voce_proprie
from app.operare import efecte
from app.reclame import Campanie, propuneri
from app.validare import limba, structura
from app.validare.intrare import Continut, Intrare, SituatieLivrabil
from app.validare.verdict import Rezultat
from tests.integration.publicare_utile import autorizeaza, cere, pune_aprobarea
from tests.integration.utile_productie import fabrica_clienti, livrabil_in_publicare, om, tenant  # noqa: F401
from tests.integration.utile_reclame import construieste, cont_agentie, depozit, executa_efecte  # noqa: F401
from tests.platforme import google_business as gb
from tests.platforme import pinterest as pi
from tests.platforme import threads as th
from tests.platforme.tiktok_ads import TiktokAdsSimulat

pytestmark = [pytest.mark.db, pytest.mark.skipif(not ffmpeg.disponibil(), reason="ffmpeg lipsește")]
TEXT_EN = ("Our weekend offer is here: every cake is twenty percent off, and you can order online today with "
           "delivery anywhere in the city.")  # fmt: skip
FRAZE = ["Our weekend offer is here.", "Over one thousand happy customers.", "Order online today."]
SCENE = [formatul_c.ScenaC("oferta", "Weekend offer", "-20%", "on every cake"),
         formatul_c.ScenaC("cifra", "Happy customers", "1200", "in Brasov"),
         formatul_c.ScenaC("anunt", "Order today", "online", "delivery in the city")]  # fmt: skip


@pytest.fixture
def mediu(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, object]]:
    monkeypatch.setenv("AMA_VIDEO_EXTERN_ACTIV", "true")
    monkeypatch.setenv("AMA_VIDEO_EXTERN_PLAFON_LUNAR_BANI", "300")
    get_settings.cache_clear()
    registru.uita_tot()
    p, g, t = pi.PinterestSimulat(), gb.GoogleBusinessSimulat(), th.ThreadsSimulat()
    for c in (
        ConectorPinterest(client_id=pi.CLIENT_ID, client_secret=pi.CLIENT_SECRET, transport=p.transport),
        ConectorGoogleBusiness(client_id=gb.CLIENT_ID, client_secret=gb.CLIENT_SECRET, transport=g.transport),
        ConectorThreads(app_id=th.APP_ID, app_secret=th.APP_SECRET, transport=t.transport),
    ):
        registru.inregistreaza(c.canal, c)
    yield {"pinterest": p, "google_business": g, "threads": t}
    registru.uita_tot()
    video_extern.seteaza(None)
    get_settings.cache_clear()


def test_poarta_f16(
    tenant: uuid.UUID, om: uuid.UUID, mediu: dict[str, object], depozit: DepozitInMemorie,
    cont_agentie: Callable[..., tuple[uuid.UUID, uuid.UUID]], admin_engine: Engine,
) -> None:  # fmt: skip
    inceput = dt.datetime.now(dt.UTC)
    # F16.3: clientul publică în engleză; textul trece validarea pe engleză, cel românesc nu
    with sesiune_agentie() as db:
        localizare.seteaza_limba_client(db, tenant, "en")
    with sesiune_tenant(tenant) as db:
        sit, la = SituatieLivrabil(tenant, tenant, "postare", "facebook", 1, 0), dt.datetime.now(dt.UTC)
        en = Intrare(sit, Continut(1, TEXT_EN), la, db=db)
        assert (
            structura.g1(en).rezultat is not Rezultat.ESEC
            and limba.g10_reguli(en).rezultat is not Rezultat.ESEC
        )
        # F16.4: vocea proprie, cu acord scris, antrenată o dată
        c = voce_proprie.inregistreaza_consimtamant(db, tenant, vorbitor="Ana Pop", document=b"acord semnat",
                                                    scopuri=["continut_organic"], utilizator_id=om)  # fmt: skip
        model = voce_proprie.antreneaza(db, tenant, c.id, [voce_proprie.Inregistrare("a" * 64, 6000.0)])
        n = voce_proprie.sintetizeaza(db, tenant, model.id, FRAZE)
        assert licente.probleme(n.activ.licenta) == []
        # F16.1: video format C în culorile brandului; F16.5: un insert generat în buget, al doilea refuzat
        r = formatul_c.proceseaza(db, tenant, SCENE, FRAZE, nume_brand="Zorilor Bakery", canal="tiktok")
        assert r.stare == "gata", r.control
        g1, a1 = video_extern.genereaza_insert(db, tenant, "steam rising from a warm cup, soft morning light")
        g2, _ = video_extern.genereaza_insert(db, tenant, "flour falling slowly onto a wooden table")
        assert (g1.stare, g2.stare) == ("gata", "refuzat") and a1 is not None
    # F16.2: aceeași ofertă pe cele trei canale noi, prin executor, o singură dată pe canal
    payload = {
        "text": TEXT_EN,
        "titlu": "Weekend offer",
        "imagine_url": "https://media.exemplu.test/cake.jpg",
    }
    for canal, aprobare in (("pinterest", ("pinterest", "publicare")), ("google_business", ("google", "business")),
                            ("threads", ("meta", "threads"))):  # fmt: skip
        pl = mediu[canal]
        autorizeaza(tenant, om, canal, pl.cod_valid(), agentie=False)  # type: ignore[attr-defined]
        pune_aprobarea(*aprobare, "aprobata")
        try:
            lid = livrabil_in_publicare(tenant, om, canal=canal)
            assert efecte.incearca_efect(tenant, cere(tenant, lid, payload)) == "trimis"
            assert len(pl.postari) == 1  # type: ignore[attr-defined]
        finally:
            pune_aprobarea(*aprobare, "in_test")
    # F16.6: TikTok Ads, prin constructor, gardian și executor
    sim = TiktokAdsSimulat()
    registru_reclame.inregistreaza("tiktok", ContTiktok(depozit=depozit, transport=sim.transport))
    try:
        t_ads, cont_id = cont_agentie("tiktok", "7000123")
        depozit.pune(t_ads, CANAL_TOKEN, Token(acces=sim.token_nou("act")))
        scalare, _ = construieste(cont_id, om)
        with sesiune_agentie() as db:
            camp = db.get(Campanie, scalare)
            assert camp is not None and sim.campanii[str(camp.id_extern)]["operation_status"] == "DISABLE"
            p = propuneri.propune(db, scalare, "stare", {"stare": "activa"}, motiv="Pornire", sursa="om",
                                  utilizator_id=om)  # fmt: skip
            propuneri.aproba(db, p.id, utilizator_id=om)
            ext = str(camp.id_extern)
        executa_efecte()
        assert sim.campanii[ext]["operation_status"] == "ENABLE"
    finally:
        registru_reclame.uita_tot()
    # FT: fiecare extensie a lăsat urme
    with admin_engine.connect() as cx:
        actiuni = set(cx.execute(text("SELECT actiune FROM urme WHERE la >= :i"), {"i": inceput}).scalars())
    assert {"formatul_c", "video_extern.genereaza", "voce_proprie.antrenare"} <= actiuni
