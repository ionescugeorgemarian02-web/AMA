# ruff: noqa: F811
"""Regresie F-editorial (testul „Atelierul Spița”): un scenariu despre un serviciu fizic, cu sigla ca singur
activ, nu are voie să pună sigla în scene. Trece prin pregătirea folosită în producție
(`media.fluxuri.pregateste_script`)."""

import io
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app import productie
from app.conturi import Rol
from app.db import sesiune_tenant
from app.media import biblioteca, cereri, fluxuri, lista, regizor, sabloane
from app.media.modele import Activ, Randare
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401
from tests.media_utile import materiale, model_regizor
from tests.onboarding_utile import ModelFals, model_fals, modele  # noqa: F401
from tests.validare_utile import livrabil_in_validare

pytestmark = pytest.mark.db

SCRIPT_SPITA: dict[str, Any] = {
    "hook": "Frânele scârțâie și bicicleta nu mai oprește sigur?",
    "batai": [
        {"voce": "Verificăm plăcuțele de frână și reglăm etrierul pe loc.", "text_ecran": "Frâne reglate",
         "vizual": "mecanic care reglează etrierul frânei pe roata din față"},
        {"voce": "Curățăm transmisia și ungem lanțul pe fiecare pinion.", "text_ecran": "Transmisie curată",
         "vizual": "lanț uns pe pinionul transmisiei"},
        {"voce": "Primești devizul înainte să începem, fără surprize.", "text_ecran": "Deviz clar",
         "vizual": "deviz scris pe tejghea lângă bicicletă"},
    ],
    "cta": "Programează revizia pe site.",
}  # fmt: skip


def _livrabil_spita(tenant: uuid.UUID) -> tuple[uuid.UUID, int]:
    lid = livrabil_in_validare(
        tenant, "scenariu", campuri=SCRIPT_SPITA, tip="script_video_scurt", canal="tiktok"
    )
    with sesiune_tenant(tenant) as db:
        lv = productie.citeste(db, lid)
        assert lv is not None
        return lid, lv.versiune


def test_sigla_nu_e_niciodata_materialul_principal_al_unei_scene(
    tenant: uuid.UUID, modele: ModelFals
) -> None:
    model_regizor(modele)
    with sesiune_tenant(tenant) as db:
        sabloane.asigura_sabloane(db, tenant, "Atelierul Spița")
        active = list(db.query(Activ).all())
        assert [a.sursa for a in active] == ["identitate"]  # singurul activ e sigla creată de șabloane
        assert active[0].rol_vizual == "logo"
        sigla = active[0].id
    lid, versiune = _livrabil_spita(tenant)
    rid = fluxuri.pregateste_script(str(tenant), str(lid), str(versiune))
    if rid and rid != fluxuri.BLOCAT_MATERIAL:
        with sesiune_tenant(tenant) as db:
            r = db.get(Randare, uuid.UUID(rid))
            assert r is not None
            lm = lista.ListaMontaj.model_validate(r.lista)
            assert lm.scene
            assert all(s.activ_id != sigla for s in lm.scene), "sigla a ajuns material principal într-o scenă"
    # prezentarea unei afaceri reale fără fotografii: livrabil blocat, cu câte o cerere precisă pe bătaie
    assert rid == fluxuri.BLOCAT_MATERIAL
    with sesiune_tenant(tenant) as db:
        sb = regizor.storyboard(db, tenant, SCRIPT_SPITA, natura="prezentare")
        assert all(s.activ_id != sigla for s in sb.scene) and sb.semnatura == sigla
        c = cereri.deschise(db, tenant, lid)
        assert [x.scena for x in c] == [1, 2, 3]
        assert c[1].cerere == "Încarcă o fotografie verticală cu lanț uns pe pinionul transmisiei"
        assert db.scalars(select(Randare).where(Randare.livrabil_id == lid)).first() is None
    # a doua rulare nu dublează cererile
    assert fluxuri.pregateste_script(str(tenant), str(lid), str(versiune)) == fluxuri.BLOCAT_MATERIAL
    with sesiune_tenant(tenant) as db:
        assert len(cereri.deschise(db, tenant, lid)) == 3


def test_dupa_incarcarea_fotografiilor_acelasi_livrabil_se_reia(tenant: uuid.UUID, modele: ModelFals) -> None:
    model_regizor(modele)
    with sesiune_tenant(tenant) as db:
        sabloane.asigura_sabloane(db, tenant, "Atelierul Spița")
        sigla = db.scalars(select(Activ.id).where(Activ.rol_vizual == "logo")).one()
    lid, versiune = _livrabil_spita(tenant)
    assert fluxuri.pregateste_script(str(tenant), str(lid), str(versiune)) == fluxuri.BLOCAT_MATERIAL
    with sesiune_tenant(tenant) as db:
        poze = materiale(db, tenant, "foto", 3)
        for p, subiect in zip(
            poze,
            ["etrierul frânei pe roata din față", "transmisie: lanț pe pinion", "deviz pe tejghea"],
            strict=True,
        ):
            biblioteca.clasifica(db, p.id, "fotografie", subiect)
        fluxuri.reia_livrabil(db, tenant, lid, utilizator_id=None)
        assert cereri.deschise(db, tenant, lid) == []
    rid = fluxuri.pregateste_script(str(tenant), str(lid), str(versiune))
    assert rid and rid != fluxuri.BLOCAT_MATERIAL
    with sesiune_tenant(tenant) as db:
        r = db.get(Randare, uuid.UUID(rid))
        assert r is not None
        lm = lista.ListaMontaj.model_validate(r.lista)
        pe_bataie = {s.bataie: s.activ_id for s in lm.scene}
        assert pe_bataie[1] == poze[0].id and pe_bataie[2] == poze[1].id and pe_bataie[3] == poze[2].id
        assert sigla not in pe_bataie.values()


def test_panoul_arata_cererile_si_clasifica_activele_incerte(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float], tenant: uuid.UUID
) -> None:
    lid, versiune = _livrabil_spita(tenant)
    with sesiune_tenant(tenant) as db:
        sabloane.asigura_sabloane(db, tenant, "Atelierul Spița")
    assert fluxuri.pregateste_script(str(tenant), str(lid), str(versiune)) == fluxuri.BLOCAT_MATERIAL
    buf = io.BytesIO()
    Image.new("RGB", (90, 160), (120, 80, 40)).save(buf, "JPEG")
    with sesiune_tenant(tenant) as db:
        poza = biblioteca.incarca(
            db, tenant, buf.getvalue(), nume_original="lant.jpg", sursa="portal", utilizator_id=None
        )
        assert poza.rol_vizual is None  # din portal: rol incert, de clasificat
        poza_id = poza.id
    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    h = client.get(f"/materiale?client={tenant}").text
    assert "Încarcă o fotografie verticală cu lanț uns pe pinionul transmisiei" in h and "lant.jpg" in h
    jeton = csrf(client, f"/materiale?client={tenant}")
    cale = f"/materiale/{tenant}/active/{poza_id}/clasifica"
    assert client.post(cale, data={"rol": "fotografie", "subiect": "x"}).status_code == 403, (
        "fără CSRF, refuz"
    )
    r = client.post(cale, data={"csrf_token": jeton, "rol": "necunoscut", "subiect": "x"})
    assert r.status_code == 422
    r = client.post(
        cale,
        data={"csrf_token": jeton, "rol": "fotografie", "subiect": "lanț pe pinion"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with sesiune_tenant(tenant) as db:
        a = db.get(Activ, poza_id)
        assert a is not None and (a.rol_vizual, a.subiect) == ("fotografie", "lanț pe pinion")
    r = client.post(
        f"/materiale/{tenant}/livrabile/{lid}/reia", data={"csrf_token": jeton}, follow_redirects=False
    )
    assert r.status_code == 303
    with sesiune_tenant(tenant) as db:
        assert cereri.deschise(db, tenant, lid) == []
    assert client.get(f"/materiale?client={uuid.uuid4()}").status_code == 404
