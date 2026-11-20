# ruff: noqa: F811
"""Verdictul editorial (F-editorial, decizia 7) pe un export real: un MP4 care trece G6 dar are sigla în toate
scenele (defectul testului „Atelierul Spița”) e respins editorial, cu motivul, etapa de reluat și planșa. Ecranul
de aprobare arată separat G6 și verdictul editorial."""

import io
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app import productie
from app.conturi import Rol
from app.db import sesiune_tenant
from app.media import control, ffmpeg, montaj, normalizare, regizor, sabloane, transcriere
from app.media.modele import Activ, Randare
from app.productie import Stare
from tests.integration.conftest import Cont
from tests.integration.test_media_selectie_scene import SCRIPT_SPITA
from tests.integration.utile_panou import autentifica
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401
from tests.validare_utile import livrabil_in_validare

pytestmark = [pytest.mark.db, pytest.mark.skipif(not ffmpeg.disponibil(), reason="ffmpeg lipsește")]


def test_mp4_cu_g6_trecut_si_sigla_in_scene_e_respins_editorial_si_apare_la_aprobare(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float], tenant: uuid.UUID
) -> None:
    with sesiune_tenant(tenant) as db:
        sabloane.asigura_sabloane(db, tenant, "Atelierul Spița")
        sigla = db.scalars(select(Activ).where(Activ.rol_vizual == "logo")).one()
    lid = livrabil_in_validare(
        tenant, "scenariu", campuri=SCRIPT_SPITA, tip="script_video_scurt", canal="tiktok"
    )
    with sesiune_tenant(tenant) as db:
        fr = [normalizare.normalizeaza(f) for f in regizor.fraze_din_script(SCRIPT_SPITA)]
        nv = transcriere.naratiune_verificata(db, tenant, fr)
        alegeri = [regizor.AlegereScena(bataie=i, material=0, miscare="zoom_in") for i in range(len(fr))]
        # montajul vechi, de dinaintea storyboardului: sigla în fiecare scenă
        lm = regizor.construieste(format="B", canal="tiktok", fraze=fr, naratiune=nv, materiale=[sigla],
                                  alegeri=alegeri)  # fmt: skip
        r = montaj.produ(db, tenant, lm, livrabil_id=lid)
        assert r.control["G6"]["rezultat"] == "trece", r.control["G6"]
        ed = r.control["editorial"]
        assert ed["rezultat"] == "respins" and ed["etapa"] == "selectie"
        assert ed["mesaj"] == "Scenele 0–4 folosesc aceeași siglă. Revino la selecția materialelor."
        assert [c["scena"] for c in ed["cadre"]] == [0, 1, 2, 3, 4]
        assert all(c["activ_id"] == str(sigla.id) for c in ed["cadre"])
        # G6 trecut nu ajunge: un export respins editorial nu apare ca pregătit pentru publicare
        assert montaj.video_verificat(db, tenant, lid, r.masuratori["versiune_continut"]) is None
        assert ed["evaluare_vizuala"]["stare"] == "neverificata"  # niciun model cu imagini, niciun operator
        foaie = db.get(Activ, uuid.UUID(ed["plansa_activ_id"]))
        assert foaie is not None and foaie.rol_vizual == "export"
        assert Image.open(io.BytesIO((regizor.cale(foaie)).read_bytes())).size[0] == 4 * 282 + 12
        # exportul unei versiuni vechi e respins chiar dacă imaginile ar fi bune
        r.masuratori = {**r.masuratori, "versiune_continut": r.masuratori["versiune_continut"] - 1}
        v = control.verdict_editorial(db, tenant, lid, randare=r)
        assert "alta_versiune" in {m["regula"] for m in v["motive"]}
        r.masuratori = {**r.masuratori, "versiune_continut": r.masuratori["versiune_continut"] + 1}
        control.verdict_editorial(db, tenant, lid, randare=r)
        productie.muta(db, lid, Stare.IN_VALIDARE, Stare.VALIDAT, componenta="test")
        ap = productie.aprobari.cere(db, lid)
        assert db.scalars(select(Randare).where(Randare.livrabil_id == lid)).one().stare == "gata"
    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    h = client.get("/aprobari").text
    assert "Control tehnic (G6)" in h and "Verdict editorial" in h
    assert "Scenele 0–4 folosesc aceeași siglă. Revino la selecția materialelor." in h
    assert f"/aprobari-media/{ap.id}/plansa" in h and "neverificată" in h
    p = client.get(f"/aprobari-media/{ap.id}/plansa")
    assert p.status_code == 200 and p.headers["content-type"] == "image/png"
    assert client.get(f"/aprobari-media/{uuid.uuid4()}/plansa").status_code == 404
