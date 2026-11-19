"""Testul live orchestrat (nu rulează în CI): lanțul real, cu agenți în locul modelelor gratuite.

Pornește doar cu `AMA_PUNTE_DIR` setat. Fundația brandului FICTIV „Cafeneaua Zorilor” (brief, ghid, strategie, calendar,
briefuri) vine din lanțul de test (modelul FALS). Sarcinile de creație — deschiderile (E1), postările Facebook (E4) și
reparațiile lor, scriptul video (E2) și regizorul — trec prin gateway la puntea orchestratorului, unde le scrie un agent.
Reale: gateway-ul, cascada de validare, vocea în română (espeak-ng + MBROLA ro1), alinierea subtitrărilor pe semnal,
montajul FFmpeg ca job durabil, controlul G6 pe fișier, coperta G5, pașaportul G11. Simulate: stock-ul vizual, muzica.

    AMA_PUNTE_DIR=/cale AMA_TEST_PLAFON_SEC=7200 uv run pytest tests/integration/test_live_orchestrat.py -o faulthandler_timeout=0
"""

# ruff: noqa: F811
import json
import os
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest

from app import continut, productie, validare
from app.config import get_settings
from app.continut import pipeline
from app.db import sesiune_tenant
from app.media import (
    compozitor,
    control,
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
    voce,
)  # fmt: skip
from app.media.modele import Activ, Randare
from app.operare import motor
from app.productie import Stare
from tests.integration.lant_continut import cu_briefuri
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele  # noqa: F401
from tests.punte_orchestrator import Punte

DIR = os.environ.get("AMA_PUNTE_DIR")
pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not DIR, reason="testul live cere AMA_PUNTE_DIR"),
    pytest.mark.skipif(not voce.MotorEspeak.disponibil(), reason="espeak-ng / mbrola-ro1 lipsesc"),
]
SARCINI = (
    "Propune deschideri pentru materialul",
    "Scrie postarea pentru",
    "Corectează materialul de mai jos",
    "Scrie scriptul video scurt",
    "Ești regizorul video",
)


def _copie(db: object, tenant: uuid.UUID, sursa: uuid.UUID, tip: str) -> uuid.UUID:
    """Un livrabil nou pe Facebook, cu brieful unui slot din calendar."""
    lid = productie.creeaza(db, tenant_id=tenant, tip=tip, canal="facebook").id  # type: ignore[arg-type]
    b = continut.brief.al_livrabilului(db, sursa)  # type: ignore[arg-type]
    assert b is not None
    db.add(continut.Brief(tenant_id=tenant, livrabil_id=lid, pachet_id=b.pachet_id, continut=b.continut))  # type: ignore[attr-defined]
    productie.muta(db, lid, Stare.PLANIFICAT, Stare.BRIEFAT, componenta="test-live")  # type: ignore[arg-type]
    return lid


def test_live_postari_facebook_si_video_in_romana(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, porneste_executor: Callable[..., None]
) -> None:
    assert DIR
    iesire = Path(DIR) / "rezultat"
    iesire.mkdir(parents=True, exist_ok=True)
    porneste_executor(culoare_greu=2)
    cal, _ = cu_briefuri(tenant, om, modele)
    punte = Punte(Path(DIR))
    for s in SARCINI:
        modele.handlere[s] = punte.handler(s)
    voce.seteaza_motor(voce.MotorEspeak())
    try:
        with sesiune_tenant(tenant) as db:
            intrari = list(continut.calendar.intrari(db, cal))
        sursa_post = [i.livrabil_id for i in intrari if i.tip == "postare" and i.livrabil_id][:3]
        sursa_script = next(i.livrabil_id for i in intrari if i.tip == "script_video_scurt" and i.livrabil_id)
        with sesiune_tenant(tenant, om) as db:
            posturi = [_copie(db, tenant, s, "postare") for s in sursa_post]
            script_id = _copie(db, tenant, sursa_script, "script_video_scurt")

        # --- 1. Trei postări Facebook, prin cascada reală de validare
        raport: dict[str, object] = {"postari": [], "video": {}}
        md = ["# Postări Facebook — Cafeneaua Zorilor (brand fictiv)\n"]
        for k, lid in enumerate(posturi, 1):
            stare = pipeline.produ(tenant, lid)
            with sesiune_tenant(tenant) as db:
                lv = productie.citeste(db, lid)
                c = validare.continut.citeste(db, lid)
                ultima = validare.ultima_rulare(db, lid)
                assert lv is not None
                rap = {"nr": k, "stare": stare, "decizie": ultima.decizie if ultima else None,
                       "runde_reparatie": lv.runde_reparatie, "hook": c.campuri.get("hook")}  # fmt: skip
                raport["postari"].append(rap)  # type: ignore[attr-defined]
                md += [f"\n## Postarea {k}  ·  validare: {rap['decizie']}, reparații: {lv.runde_reparatie}\n",
                       c.text, ""]  # fmt: skip
        (iesire / "postari_facebook.md").write_text("\n".join(md))

        # --- 2. Scriptul video (E2), validat, apoi vocea, regizorul și montajul
        assert pipeline.produ(tenant, script_id) == Stare.ASTEAPTA_APROBARE.value
        with sesiune_tenant(tenant) as db:
            sc = validare.continut.citeste(db, script_id).campuri
            (iesire / "script_video.json").write_text(json.dumps(sc, ensure_ascii=False, indent=1))
            fr = [normalizare.normalizeaza(f) for f in regizor.fraze_din_script(sc)]
            nv = transcriere.naratiune_verificata(db, tenant, fr)
            mat = [
                furnizori.aduce_stock(db, tenant, r) for r in furnizori.cauta_stock("cafea", tip="video", n=5)
            ]
            muzica = furnizori.aduce_muzica(db, tenant, "calm", 40.0)
            lm = regizor.regizeaza(db, tenant, fraze=fr, naratiune=nv, materiale=mat, format="A",
                                   canal="facebook", muzica=muzica)  # fmt: skip
            rid = montaj.pregateste(db, tenant, lm).id
            [cop] = [
                s
                for s in sabloane.asigura_sabloane(db, tenant, "Cafeneaua Zorilor")
                if s.tip == "coperta_video"
            ]
        job = fluxuri.trimite(tenant, rid)
        assert motor.asteapta_flux(job, timeout_sec=600).stare == motor.StareJob.TERMINAT
        with sesiune_tenant(tenant) as db:
            r = db.get(Randare, rid)
            assert r is not None
            a = db.get(Activ, r.activ_id)
            assert a is not None
            cale = Path(get_settings().media_dir) / a.cale
            shutil.copy(cale, iesire / "video_cafeneaua_zorilor.mp4")
            lm = lista.ListaMontaj.model_validate(r.lista)
            vd, masuri = control.verdict(
                cale, control.Asteptari(canal=lm.canal, ecrane=tuple(subtitrari.grupeaza(lm)))
            )
            _, cv = compozitor.creeaza(db, tenant, cop, {"titlu": lm.coperta.text if lm.coperta else "Cafea"})
            (iesire / "coperta.png").write_bytes(cv.png)
            raport["video"] = {
                "stare_randare": r.stare, "G6_job": r.control.get("G6", {}).get("rezultat"),
                "G6_independent": vd.rezultat.value, "lufs": masuri.get("lufs"), "durata_sec": masuri.get("durata"),
                "G5_coperta": vizual.verdict(cv.png, cv.asteptari).rezultat.value,
                "G11_pasaport": provenienta.verdict(db, a).rezultat.value,
            }  # fmt: skip
        (iesire / "raport.json").write_text(json.dumps(raport, ensure_ascii=False, indent=1, default=str))
        assert r.stare == "gata", r.control
    finally:
        voce.seteaza_motor(None)
        punte.inchide()
