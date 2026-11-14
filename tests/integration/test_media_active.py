"""F8.4 — furnizorul de imagini și biblioteca de active. „Gata când”: niciun activ nu poate fi folosit fără licență
înregistrată. Stock și generare SIMULATE (D-007); furnizorii reali: la migrare."""

# ruff: noqa: F811
import io
import uuid
from collections.abc import Callable

import pytest
from PIL import Image
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app import media
from app.db import sesiune_tenant
from app.media import furnizori, licente
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401

pytestmark = pytest.mark.db


def _jpeg_cu_exif() -> bytes:
    img = Image.new("RGB", (64, 64), (200, 120, 40))
    exif = Image.Exif()
    exif[0x010F] = "Telefonul cuiva"  # Make
    exif[0x8825] = {2: (45.0, 39.0, 0.0)}  # GPS
    out = io.BytesIO()
    img.save(out, "JPEG", exif=exif)
    return out.getvalue()


def test_niciun_activ_nu_se_foloseste_fara_licenta(
    tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    with sesiune_tenant(tenant, om) as db:
        # 1. materialul clientului din portal: licența „material_client”, declarată la încărcare; EXIF eliminat
        poza = media.biblioteca.incarca(db, tenant, _jpeg_cu_exif(), nume_original="vitrina.jpg", sursa="portal",
                                        utilizator_id=om)  # fmt: skip
        assert poza.licenta and poza.licenta["tip"] == "material_client"
        assert not Image.open(io.BytesIO(media.biblioteca.citeste_fisier(poza))).getexif()
        # 2. stock: identificatorul, autorul și copia licenței de la data descărcării
        [r, *_] = furnizori.cauta_stock("boabe de cafea prăjite", tip="foto")
        stock = furnizori.aduce_stock(db, tenant, r)
        assert stock.licenta and {"identificator", "autor", "copie", "descarcat_la"} <= set(stock.licenta)
        [rv, *_] = furnizori.cauta_stock("barista toarnă lapte", tip="video")
        clip = furnizori.aduce_stock(db, tenant, rv)
        assert clip.categorie == "video" and clip.licenta and clip.licenta["tip"] == "stock"
        # 3. generat: promptul, modelul și sămânța; eticheta AI obligatorie
        gen = furnizori.genereaza_imagine(db, tenant, "fundal cald, boabe de cafea pe lemn", samanta=7)
        assert gen.generare == {"furnizor": "generator-simulat", "model": "simulat-imagine-1",
                                "prompt": "fundal cald, boabe de cafea pe lemn", "samanta": 7}  # fmt: skip
        assert gen.licenta and gen.licenta["eticheta_ai"] is True
        with pytest.raises(furnizori.PromptRefuzat):
            furnizori.genereaza_imagine(db, tenant, "cafea cu logo Starbucks și text mare", samanta=1)
        # 4. un activ fără licență (de ex. importat) nu se poate folosi, nici o licență incompletă sau refuzată
        fara = media.biblioteca.incarca(db, tenant, b"%PDF-1.4 meniu", nume_original="meniu.pdf", sursa="import",
                                        utilizator_id=om)  # fmt: skip
        for a in (poza, stock, clip, gen):
            licente.foloseste(db, a.id, scop="test")
        with pytest.raises(licente.FaraLicenta):
            licente.foloseste(db, fara.id, scop="test")
        with pytest.raises(licente.FaraLicenta):
            licente.inregistreaza(db, fara, {"tip": "stock", "furnizor": "x", "identificator": "1"})
        assert fara.licenta is None
        stock.licenta = {**stock.licenta, "statut": "refuzata"}
        db.flush()
        with pytest.raises(licente.FaraLicenta):
            licente.foloseste(db, stock.id, scop="test")
        licente.inregistreaza(
            db, fara, {"tip": "material_client", "declarat_de": str(om), "conditii": "contract"}
        )
        licente.foloseste(db, fara.id, scop="test")
        fara_id, poza_id = fara.id, poza.id
        neinregistrat = media.biblioteca.incarca(db, tenant, b"%PDF-1.4 altul", nume_original="x.pdf",
                                                 sursa="import", utilizator_id=om).id  # fmt: skip
    # 5. baza refuză și ea folosirea, chiar dacă cineva ocolește aplicația
    with pytest.raises(DBAPIError, match="licență"), admin_engine.begin() as c:
        c.execute(text("INSERT INTO folosiri_active (id, tenant_id, activ_id, scop) VALUES (gen_random_uuid(), :t, "
                       ":a, 'ocolire')"), {"t": tenant, "a": neinregistrat})  # fmt: skip
    with sesiune_tenant(tenant) as db:
        assert len(licente.folosiri(db, fara_id)) == 1 and len(licente.folosiri(db, poza_id)) == 1


def test_altul_nu_poate_folosi_activul_clientului(
    tenant: uuid.UUID, fabrica_clienti: Callable[[], uuid.UUID]
) -> None:
    altul = fabrica_clienti()
    with sesiune_tenant(tenant) as db:
        a = furnizori.genereaza_imagine(db, tenant, "fundal verde", samanta=1).id
    with sesiune_tenant(altul) as db, pytest.raises(licente.FaraLicenta):
        licente.foloseste(db, a, scop="test")
