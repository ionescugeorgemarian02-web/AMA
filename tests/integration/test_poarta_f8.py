"""Poarta F8 — „zece video consecutive trec controlul media fără intervenție”.

Cap-coadă, fără niciun om: scriptul pe bătăi (E2) -> normalizare -> voce verificată prin transcriere inversă ->
Regizorul (modelul FALS, prin gateway) -> lista validată -> montajul ca job durabil pe două culoare grele
(subtitrări, muzică atenuată, nivel) -> G6 pe fișier -> coperta din șablon (G5) -> pașaport și etichetă (G11).
Simulate (D-007): vocea, transcriptorul, stock-ul, generarea, muzica, modelul. Reale: FFmpeg, libass, Postgres,
motorul durabil, validatorii G5 / G6 / G11."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest

from app import validare
from app.config import get_settings
from app.db import sesiune_tenant
from app.media import (
    compozitor,
    control,
    ffmpeg,
    fluxuri,
    furnizori,
    lista,
    montaj,
    normalizare,
    provenienta,
    regizor,
    sabloane,
    subtitrari,
    transcriere,
    vizual,
)  # fmt: skip
from app.media.modele import Activ, Randare
from app.operare import motor
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401
from tests.media_utile import SCRIPT, materiale, model_regizor
from tests.onboarding_utile import ModelFals, model_fals, modele  # noqa: F401

pytestmark = [pytest.mark.db, pytest.mark.skipif(not ffmpeg.disponibil(), reason="ffmpeg lipsește")]
HOOKURI = [
    "Știi de ce cafeaua ta e amară?", "Trei greșeli la râșnița de acasă.", "Cât de proaspătă e cafeaua ta?",
    "De ce prăjim doar marțea?", "Ce înseamnă o cafea de specialitate?", "Apa contează mai mult decât crezi.",
    "Espresso sau filtru, pentru dimineață?", "Unde ții boabele după ce deschizi punga?",
    "Cum citești eticheta unui pachet de cafea?", "De ce plătim fermierilor cu 20% mai mult?",
]  # fmt: skip


def test_poarta_f8_zece_video_consecutive_trec_controlul_fara_interventie(
    tenant: uuid.UUID, modele: ModelFals, porneste_executor: Callable[..., None]
) -> None:
    porneste_executor(culoare_greu=2)
    model_regizor(modele)
    randari: list[uuid.UUID] = []
    with sesiune_tenant(tenant) as db:
        video = materiale(db, tenant, "video", 4)
        foto = [furnizori.genereaza_imagine(db, tenant, f"cafea, cadru {i}", samanta=i) for i in range(3)]
        muzica = furnizori.aduce_muzica(db, tenant, "calm", 20.0)
        [cop] = [
            s for s in sabloane.asigura_sabloane(db, tenant, "Cafeneaua Zorilor") if s.tip == "coperta_video"
        ]
        for i, hook in enumerate(HOOKURI):
            script = {**SCRIPT, "hook": hook}
            fr = [normalizare.normalizeaza(f) for f in regizor.fraze_din_script(script)]
            nv = transcriere.naratiune_verificata(db, tenant, fr)
            assert not nv.semnalate
            fmt = "AB"[i % 2]
            lm = regizor.regizeaza(db, tenant, fraze=fr, naratiune=nv, materiale=video if fmt == "A" else foto,
                                   format=fmt, canal=("tiktok", "instagram", "youtube")[i % 3],
                                   muzica=muzica if i % 3 else None)  # fmt: skip
            randari.append(montaj.pregateste(db, tenant, lm).id)
    joburi = [fluxuri.trimite(tenant, r) for r in randari]
    for j in joburi:
        assert motor.asteapta_flux(j, timeout_sec=110).stare == motor.StareJob.TERMINAT
    with sesiune_tenant(tenant) as db:
        for rid in randari:
            r = db.get(Randare, rid)
            assert r is not None and r.stare == "gata", (rid, r and r.control)
            assert r.control["G6"]["rezultat"] == "trece"
            a = db.get(Activ, r.activ_id)
            assert a is not None
            lm = lista.ListaMontaj.model_validate(r.lista)
            # controlul independent, pe fișierul final: G6 (format, imagine, sunet, sincronizare, subtitrări)
            vd, masuri = control.verdict(Path(get_settings().media_dir) / a.cale,
                                         control.Asteptari(canal=lm.canal, ecrane=tuple(subtitrari.grupeaza(lm))))  # fmt: skip
            assert vd.rezultat == validare.Rezultat.TRECE, (rid, vd.dovezi)
            assert abs(masuri["lufs"] + 14) <= 1
            # coperta (G5) și pașaportul cu eticheta pe canal (G11)
            _, c = compozitor.creeaza(db, tenant, cop, {"titlu": lm.coperta.text if lm.coperta else "Cafea"})
            assert vizual.verdict(c.png, c.asteptari).rezultat == validare.Rezultat.TRECE
            assert provenienta.verdict(db, a).rezultat == validare.Rezultat.TRECE
