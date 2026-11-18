"""F16.1 — formatul C, grafică animată. „Gata când”: trei scene (ofertă, cifră, anunț), în culorile brandului,
devin un video vertical publicabil (G6 trece), randat local; pașaportul spune doar „voce sintetică”, nu
„imagine generată”. Vocea e cea SIMULATĂ (D-007); HyperFrames e înlocuit de randarea locală (D-026)."""

# ruff: noqa: F811
import uuid
from pathlib import Path

import pytest

from app import validare
from app.config import get_settings
from app.db import sesiune_tenant
from app.media import control, ffmpeg, formatul_c, lista, provenienta, sabloane, subtitrari
from app.media.modele import Activ
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401

pytestmark = [pytest.mark.db, pytest.mark.skipif(not ffmpeg.disponibil(), reason="ffmpeg lipsește")]

FRAZE = ["Oferta săptămânii la Cofetăria Zorilor.", "Peste o mie două sute de clienți mulțumiți.",
         "Vă așteptăm sâmbătă pe strada Lungă."]  # fmt: skip
SCENE = [formatul_c.ScenaC("oferta", "Oferta săptămânii", "-20%", "la toate prăjiturile"),
         formatul_c.ScenaC("cifra", "Clienți mulțumiți", "1200", "în Brașov"),
         formatul_c.ScenaC("anunt", "Sâmbătă, la noi", "10:00", "strada Lungă 5")]  # fmt: skip


def test_trei_scene_devin_video_publicabil_in_culorile_brandului(tenant: uuid.UUID) -> None:
    with sesiune_tenant(tenant) as db:
        r = formatul_c.proceseaza(db, tenant, SCENE, FRAZE, nume_brand="Cofetăria Zorilor", canal="instagram")
        assert r.stare == "gata", r.control
        lm = lista.ListaMontaj.model_validate(r.lista)
        assert lm.format == "C" and r.masuratori["scene_c"] == 3
        v = db.get(Activ, r.activ_id)
        assert v is not None
        cale = Path(get_settings().media_dir) / v.cale
        vd, _ = control.verdict(
            cale, control.Asteptari(canal=lm.canal, ecrane=tuple(subtitrari.grupeaza(lm)))
        )
        assert vd.rezultat == validare.Rezultat.TRECE, vd.dovezi
        p = provenienta.al_activului(db, v.id)
        assert p is not None and p.continut["ai"]["imagine_generata"] is False
        assert p.continut["ai"]["voce_sintetica"] is True
        # culorile vin din identitatea brandului (aceeași propunere din Creier)
        ident, propusa = sabloane.identitate(db, tenant, "Cofetăria Zorilor")
        assert not propusa and ident["culori"]["primara"].startswith("#")
        sursa = db.get(Activ, lm.scene[0].activ_id)
        assert sursa is not None and sursa.sursa == "format_c" and sursa.generare["format"] == "C"


def test_scenele_gresite_sunt_refuzate_inainte_de_randare(tenant: uuid.UUID) -> None:
    with sesiune_tenant(tenant) as db, pytest.raises(formatul_c.ScenaInvalida):
        formatul_c.proceseaza(db, tenant, SCENE[:2], FRAZE, nume_brand="Cofetăria Zorilor")
