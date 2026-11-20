# ruff: noqa: F811
"""Demonstrația A/B „Atelierul Spița” (F-editorial, decizia 8). Rulează doar cu `AMA_EDITORIAL_DIR` (jobul
`editorial` din CI), unde scrie artefactele, copiate exact din biblioteca aplicației (fără retușare).

Același dosar (`tests/pilot_clienti.py`, cazul „servicii”), oferta de 120 lei și aceleași texte fixe. Nu se
apelează niciun model: regizorul primește modelul fals determinist din teste (alege doar mișcarea; materialul
vine din storyboard).

- A: doar sigla -> livrabilul se blochează cu câte o cerere precisă pe scenă; nimic pregătit pentru publicare.
- B: sigla + trei fotografii (din `AMA_FOTOGRAFII_DIR`, cu `LICENTE.json` scris de
  `scripts/foto_test_commons.py`; fără ele, trei imagini procedurale, marcate ca atare) -> imagine de feed,
  carusel, MP4 vertical cu voce și subtitrări, storyboard, planșă, G6, verdict editorial și mostra audio.
"""

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text

from app import productie
from app.db import sesiune_tenant
from app.ids import new_id
from app.media import (
    biblioteca,
    cereri,
    compozitor,
    control,
    ffmpeg,
    fluxuri,
    licente,
    montaj,
    regizor,
    sabloane,
    voce,
)
from app.media.modele import Activ, Randare
from app.productie import Stare
from tests.integration.utile_productie import om  # noqa: F401
from tests.media_utile import fotografie_procedurala, model_regizor
from tests.onboarding_utile import ModelFals, model_fals, modele  # noqa: F401
from tests.pilot_clienti import CAZURI
from tests.validare_utile import fapt_aprobat, livrabil_in_validare, oferta_aprobata

DIR = os.getenv("AMA_EDITORIAL_DIR")
pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not DIR, reason="demonstrația A/B rulează doar cu AMA_EDITORIAL_DIR (jobul editorial)"
    ),
    pytest.mark.skipif(not ffmpeg.disponibil(), reason="ffmpeg lipsește"),
]
DOSAR = CAZURI["servicii"]

# textele FIXE ale materialului (fără model): hook, trei bătăi cu indicații vizuale observabile, apel
SCRIPT: dict[str, Any] = {
    "hook": "Frâna scârțâie și lanțul sare de pe pinion?",
    "batai": [
        {"voce": "La Revizia Urbană curățăm transmisia și ungem lanțul pe fiecare pinion.",
         "text_ecran": "Transmisie curată", "vizual": "lanțul pe pinionul casetei, transmisia de aproape"},
        {"voce": "Reglăm frâna, ca etrierul să prindă discul egal, fără scârțâit.",
         "text_ecran": "Frână reglată", "vizual": "etrierul frânei pe discul roții"},
        {"voce": "Revizia costă 120 de lei, iar devizul îl vezi înainte să începem.",
         "text_ecran": "120 lei, deviz clar", "vizual": "devizul scris pe bancul de lucru al mecanicului"},
    ],
    "cta": "Programează revizia din formularul de pe site.",
    "natura": "prezentare",
}  # fmt: skip
BRIEF: dict[str, Any] = {
    "idee_editoriala": "Revizia Urbană arată ce se verifică, cu prețul spus dinainte.",
    "ce_vede_publicul": "etrierul frânei pe discul roții bicicletei",
    "informatie_in_plus": "Devizul se explică înainte de intervenție.",
    "natura": "prezentare",
}
TITLU_FEED = "Revizia Urbană: frâne și transmisie, 120 lei"
CARUSEL = {
    "intrebare": "Ce verificăm la Revizia Urbană?",
    "idei": [
        "Transmisia\nLanțul uns pe fiecare pinion al casetei",
        "Frâna\nEtrierul prinde discul egal",
        "Devizul\nÎl vezi înainte să începem",
    ],
    "pas": "Programează revizia: 120 lei",
}
# subiectele imaginilor procedurale (când fotografiile reale lipsesc)
PROCEDURALE = {
    "transmisie": "transmisie: lanț pe pinionul casetei",
    "frana": "frâna bicicletei: etrierul pe discul roții",
    "deviz": "bancul de lucru al mecanicului de biciclete",
}


def _iesire(sub: str) -> Path:
    assert DIR
    d = Path(DIR) / sub
    d.mkdir(parents=True, exist_ok=True)
    return d


def _json(d: Path, nume: str, date: object) -> None:
    (d / nume).write_text(json.dumps(date, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _copiaza(a: Activ, dest: Path) -> None:
    """Fișierul exact din biblioteca aplicației, fără nicio prelucrare."""
    shutil.copyfile(regizor.cale(a), dest)


def _client(admin_engine: Engine, om: uuid.UUID) -> uuid.UUID:
    """Clientul „Atelierul Spița” cu prețul (fapt aprobat) și oferta de 120 lei."""
    t = new_id()
    with admin_engine.begin() as c:
        c.execute(text("INSERT INTO clienti (id, nume) VALUES (:i, :n)"), {"i": t, "n": DOSAR.marca})
    fid = fapt_aprobat(
        t, om, "pret", DOSAR.produs, DOSAR.raspunsuri["preturi"],
        valoare={"numar": DOSAR.pret, "moneda": "RON", "unitate": DOSAR.unitate},
    )  # fmt: skip
    oferta_aprobata(t, om, DOSAR.produs, DOSAR.pret, destinatie="/programare", fapte=[str(fid)])
    with sesiune_tenant(t) as db:
        sabloane.asigura_sabloane(db, t, DOSAR.marca)
    return t


def _livrabil(t: uuid.UUID) -> tuple[uuid.UUID, int]:
    lid = livrabil_in_validare(t, "scenariu", campuri=SCRIPT, tip="script_video_scurt", canal="tiktok")
    with sesiune_tenant(t) as db:
        lv = productie.citeste(db, lid)
        assert lv is not None
        return lid, lv.versiune


def _fotografii() -> tuple[list[tuple[str, bytes, str, dict[str, Any]]], bool]:
    """(cheie, corp, subiect, licență) pentru cele trei fotografii și dacă sunt reale."""
    sursa = os.getenv("AMA_FOTOGRAFII_DIR")
    fisier = Path(sursa) / "LICENTE.json" if sursa else None
    if fisier is not None and fisier.is_file():
        lic = json.loads(fisier.read_text(encoding="utf-8"))
        if set(lic) >= set(PROCEDURALE):
            out = []
            for k in PROCEDURALE:
                x = lic[k]
                out.append((k, (Path(sursa) / x["fisier"]).read_bytes(), x["subiect"], {  # type: ignore[arg-type]
                    "tip": "stock", "furnizor": "wikimedia_commons", "identificator": x["titlu"],
                    "autor": x["autor"], "url": x["url_pagina"], "copie": x["licenta"],
                    "url_licenta": x.get("url_licenta", ""), "descarcat_la": "CI", "sha256": x["sha256"],
                }))  # fmt: skip
            return out, True
    # SIMULAT: fără fotografii reale, trei imagini procedurale (deterministe), marcate în raport
    return [
        (k, fotografie_procedurala(samanta=11 + i, subiect=(0.45 + 0.1 * i, 0.6)), s, {
            "tip": "generat", "furnizor": "test", "model": "procedural", "prompt": s, "samanta": 11 + i,
            "conditii": "imagine procedurală de test, nu o fotografie reală",
        })
        for i, (k, s) in enumerate(PROCEDURALE.items())
    ], False  # fmt: skip


def _storyboard_json(db: Any, sb: dict[str, Any]) -> dict[str, Any]:
    """Storyboardul cu activul pe scenă (rol, subiect, licență), pentru artefact."""
    out = dict(sb)
    scene = []
    for s in sb.get("scene", []):
        a = db.get(Activ, uuid.UUID(s["activ_id"])) if s.get("activ_id") else None
        scene.append({**s, "activ": None if a is None else {
            "rol": a.rol_vizual, "subiect": a.subiect, "nume": a.nume_original,
            "licenta": {k: (a.licenta or {}).get(k) for k in ("tip", "identificator", "autor", "copie", "url")},
        }})  # fmt: skip
    out["scene"] = scene
    return out


def test_a_doar_sigla_livrabil_blocat_cu_cereri_pe_scena(
    admin_engine: Engine, om: uuid.UUID, modele: ModelFals
) -> None:
    model_regizor(modele)
    d = _iesire("A")
    t = _client(admin_engine, om)
    lid, versiune = _livrabil(t)
    raport: dict[str, Any] = {"caz": "A: doar sigla", "client": DOSAR.marca, "oferta": f"{DOSAR.pret} lei"}
    rez = fluxuri.pregateste_script(str(t), str(lid), str(versiune))
    with sesiune_tenant(t) as db:
        deschise = cereri.deschise(db, t, lid)
        sb = regizor.storyboard(db, t, SCRIPT, natura="prezentare")
        feed = compozitor.exporta(db, t, DOSAR.marca, BRIEF, {"titlu": TITLU_FEED})
        v = control.verdict_editorial(db, t, lid, imagini=feed.active)
        _copiaza(feed.active[0], d / f"imagine-feed-{feed.macheta}.png")
        if v["plansa_activ_id"]:
            _copiaza(biblioteca.citeste_activ(db, uuid.UUID(v["plansa_activ_id"])), d / "plansa.png")  # type: ignore[arg-type]
        _json(d, "storyboard.json", _storyboard_json(db, sb.model_dump(mode="json")))
        _json(d, "verdict.json", {"G6": None, "editorial": v})
        lv = productie.citeste(db, lid)
        assert lv is not None
        raport.update({
            "rezultat": rez,
            "cereri": [{"scena": c.scena, "subiect": c.subiect, "cerere": c.cerere} for c in deschise],
            "motiv": v["mesaj"],
            "stare_livrabil": lv.stare,
            "pregatit_pentru_publicare": montaj.video_verificat(db, t, lid, versiune) is not None,
            "imagine_feed": {"macheta": feed.macheta, "nota": feed.nota},
        })  # fmt: skip
        _json(d, "raport.json", raport)
        assert rez == fluxuri.BLOCAT_MATERIAL
        assert [c.scena for c in deschise] == [1, 2, 3]
        assert [c.cerere for c in deschise] == [regizor.cerere_material(b["vizual"]) for b in SCRIPT["batai"]]
        assert v["rezultat"] == "respins" and v["etapa"] == "material"
        assert (
            v["mesaj"].startswith("Scenele 1–3 nu au material") and "Încarcă materialul cerut" in v["mesaj"]
        )
        assert "sigla_singurul_subiect" in {m["regula"] for m in v["motive"]}  # feedul: doar text și siglă
        # nimic pregătit pentru publicare: nicio randare, niciun export verificat, livrabilul rămâne în validare
        assert raport["pregatit_pentru_publicare"] is False and lv.stare == Stare.IN_VALIDARE.value
        assert db.query(Randare).filter(Randare.livrabil_id == lid).count() == 0
        assert productie.aprobari.cerere_activa(db, lid) is None


def test_b_sigla_si_trei_fotografii_produc_materialul_complet(
    admin_engine: Engine, om: uuid.UUID, modele: ModelFals
) -> None:
    model_regizor(modele)
    d = _iesire("B")
    t = _client(admin_engine, om)
    poze, reale = _fotografii()
    raport: dict[str, Any] = {
        "caz": "B: sigla + trei fotografii",
        "client": DOSAR.marca,
        "oferta": f"{DOSAR.pret} lei",
        "fotografii": "reale (Wikimedia Commons, vezi LICENTE.json)" if reale else "fotografii procedurale, nu reale",
        "simulate": ["regizorul (modelul fals determinist alege doar mișcarea)", "alinierea subtitrărilor"]
        + ([] if reale else ["fotografiile: imagini procedurale"]),
    }  # fmt: skip
    with sesiune_tenant(t) as db:
        for k, corp, subiect, lic in poze:
            a = biblioteca.incarca(
                db, t, corp, nume_original=f"{k}.jpg", sursa="stock", utilizator_id=None, rol_vizual="fotografie",
                subiect=subiect, licenta={"statut": licente.STATUT_OK, **lic},
            )  # fmt: skip
            assert not licente.probleme(a.licenta), licente.probleme(a.licenta)
    if reale:
        shutil.copyfile(Path(os.environ["AMA_FOTOGRAFII_DIR"]) / "LICENTE.json", d / "LICENTE.json")
    lid, versiune = _livrabil(t)
    rid = fluxuri.pregateste_script(str(t), str(lid), str(versiune))
    assert rid and rid != fluxuri.BLOCAT_MATERIAL, rid
    with sesiune_tenant(t) as db:
        r = db.get(Randare, uuid.UUID(rid))
        assert r is not None
        r = montaj.executa(db, r)
        video = db.get(Activ, r.activ_id)
        assert video is not None
        feed = compozitor.exporta(db, t, DOSAR.marca, BRIEF, {"titlu": TITLU_FEED})
        car = compozitor.exporta(db, t, DOSAR.marca, {**BRIEF, "format": "carusel"}, CARUSEL)
        v = control.verdict_editorial(db, t, lid, randare=r, imagini=[*feed.active, *car.active])
        _, wav = voce.mostra(db, t, DOSAR.marca, f"{DOSAR.pret} lei", SCRIPT["cta"], voce.PROFIL_RANDARE)
        # artefactele, copiate exact din biblioteca aplicației
        _copiaza(video, d / "video.mp4")
        _copiaza(feed.active[0], d / f"imagine-feed-{feed.macheta}.png")
        for k, a in enumerate(car.active):
            _copiaza(a, d / f"carusel-{k + 1}.png")
        _copiaza(biblioteca.citeste_activ(db, uuid.UUID(v["plansa_activ_id"])), d / "plansa.png")  # type: ignore[arg-type]
        (d / "mostra.wav").write_bytes(wav)
        (d / "subtitrari.srt").write_text(r.masuratori.get("subtitrari_srt", ""), encoding="utf-8")
        _json(d, "storyboard.json", _storyboard_json(db, r.masuratori["storyboard"]))
        _json(d, "verdict.json", {"G6": r.control["G6"], "editorial": v})
        info = ffmpeg.probe(regizor.cale(video))
        vs = next(s for s in info["streams"] if s["codec_type"] == "video")
        raport.update({
            "G6": r.control["G6"]["rezultat"],
            "editorial": v["rezultat"],
            "motiv": v["mesaj"],
            "evaluare_vizuala": v["evaluare_vizuala"]["eticheta"],
            "video": {"latime": vs["width"], "inaltime": vs["height"], "durata": float(info["format"]["duration"]),
                      "pista_audio": any(s["codec_type"] == "audio" for s in info["streams"]),
                      "subtitrari_sus": r.lista["stil"].get("pozitie") == "sus"},
            "imagine_feed": {"macheta": feed.macheta, "nota": feed.nota},
            "carusel": [a.generare.get("pozitie_titlu") for a in car.active],
            "scene": [{"scena": s["scena"], "activ": s.get("activ_id"), "motiv": s["motiv"]}
                      for s in r.masuratori["storyboard"]["scene"]],
        })  # fmt: skip
        if v["rezultat"] != "trece":  # primul rezultat respins rămâne în artefacte, cu motivul
            raport["respins_editorial"] = v["motive"]
        _json(d, "raport.json", raport)
        sb = r.masuratori["storyboard"]
        poze_ids = {str(a.id) for a in db.query(Activ).filter(Activ.rol_vizual == "fotografie")}
        assert [s["activ_id"] in poze_ids for s in sb["scene"][1:4]] == [True, True, True]
        assert len({s["activ_id"] for s in sb["scene"][1:4]}) == 3  # fiecare bătaie, fotografia ei
        assert r.control["G6"]["rezultat"] == "trece", r.control["G6"]
        assert (vs["width"], vs["height"]) == (1080, 1920) and raport["video"]["pista_audio"]
        assert feed.macheta == "foto_dominanta" and len(car.imagini) == 5
        assert "banda" in raport["carusel"]  # cadrele cu fotografie potrivită folosesc fotografia
        assert len(v["cadre"]) == 5 and wav.startswith(b"RIFF")
        assert v["rezultat"] == "trece", v["motive"]
