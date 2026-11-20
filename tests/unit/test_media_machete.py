"""Machetele editoriale (F-editorial, decizia 5): foto_dominanta, detaliu_explicat, carusel, fără bază."""

import io
import os
from pathlib import Path

import pytest
from PIL import Image

from app.media import compozitor, sabloane, vizual
from tests.media_utile import fotografie_procedurala

IDENT = sabloane.propune_identitate("Atelierul Spița")
LOGO = sabloane.logo(IDENT)
MOSTRE = os.environ.get("AMA_MOSTRE_MACHETE")  # opțional: unde se salvează PNG-urile, pentru ochi


def _salveaza(nume: str, png: bytes) -> None:
    if MOSTRE:
        Path(MOSTRE).mkdir(parents=True, exist_ok=True)
        (Path(MOSTRE) / nume).write_bytes(png)


def test_zona_subiectului_din_generare_altfel_din_energie() -> None:
    img = Image.open(io.BytesIO(fotografie_procedurala(subiect=(0.7, 0.6))))
    assert compozitor.zona_subiect(img, {"zona_subiect": [0.1, 0.2, 0.3, 0.4]}) == (160, 240, 480, 480)
    x0, y0, x1, y1 = compozitor.zona_subiect(img)
    assert x0 < 0.7 * 1600 < x1 and y0 < 0.6 * 1200 < y1  # centrul de energie e pe pinion


def test_foto_dominanta_titlul_in_zona_linistita_fara_sa_acopere_subiectul() -> None:
    m = compozitor.foto_dominanta(fotografie_procedurala(), "Lanțul curat ține de două ori mai mult",
                                  IDENT, logo=LOGO)  # fmt: skip
    _salveaza("foto_dominanta.png", m.png)
    assert Image.open(io.BytesIO(m.png)).size == (1080, 1350)
    assert m.pozitie_titlu == "sus"  # cerul neted e zona cea mai liniștită
    assert m.subiect is not None and not any(compozitor._atinge(t, m.subiect) for t in m.texte)
    assert m.titlu_marime in range(sabloane.TITLU_MIN, sabloane.TIPOGRAFIE["titlu"] + 1)
    assert compozitor.verifica_export(m) == []
    assert vizual.probleme(m.png, m.asteptari) == []  # G5: contrastul voalului, sigla


def test_subiectul_sus_impinge_titlul_jos() -> None:
    m = compozitor.foto_dominanta(fotografie_procedurala(subiect=(0.5, 0.2)), "Revizie completă", IDENT)
    assert m.pozitie_titlu in ("mijloc", "jos") and compozitor.verifica_export(m) == []


def test_verificarea_la_360_px_respinge_litera_mica_si_textul_peste_subiect() -> None:
    m = compozitor.foto_dominanta(fotografie_procedurala(), "Revizie completă", IDENT)
    assert compozitor.inaltime_litera(sabloane.TITLU_MIN, 1080) >= sabloane.LITERA_TITLU_MIN
    mica = compozitor.Macheta(**{**m.__dict__, "titlu_marime": 40})
    assert "litera titlului" in compozitor.verifica_export(mica)[0]
    assert m.subiect is not None
    peste = compozitor.Macheta(**{**m.__dict__, "texte": (m.subiect,)})
    assert "acoperă subiectul" in compozitor.verifica_export(peste)[0]


def test_detaliu_explicat_cu_punct_si_fara() -> None:
    foto = fotografie_procedurala()
    cu = compozitor.detaliu_explicat(foto, "Pinionul uzat", IDENT, punct=(0.55, 0.62), logo=LOGO)
    _salveaza("detaliu_explicat.png", cu.png)
    assert cu.subiect is not None and compozitor.verifica_export(cu) == []
    sx = (cu.subiect[0] + cu.subiect[2]) / 2
    assert abs(sx - 540) < 200  # decupajul e centrat pe piesă
    fara = compozitor.detaliu_explicat(foto, "Pinionul uzat", IDENT, logo=LOGO, legenda="Dinții ascuțiți")
    _salveaza("detaliu_legenda.png", fara.png)
    assert fara.pozitie_titlu == "banda" and all(t[1] >= 1350 - compozitor.BANDA_LEGENDA for t in fara.texte)
    assert compozitor.verifica_export(fara) == [] and vizual.probleme(fara.png, fara.asteptari) == []


def test_caruselul_are_aceeasi_grila_si_intoarce_png_uri() -> None:
    cadre = compozitor.carusel_cadre(
        "De ce scârțâie frâna?", ["Plăcuțe uzate", "Disc murdar\nUn strat subțire de ulei ajunge"],
        "Programează o revizie de 120 lei", IDENT, logo=LOGO,
    )  # fmt: skip
    for k, m in enumerate(cadre):
        _salveaza(f"carusel-{k + 1}.png", m.png)
        assert compozitor.verifica_export(m) == [] and vizual.probleme(m.png, m.asteptari) == []
    assert len(cadre) == 4 and {m.texte[0][:2] for m in cadre} == {(94, 294)}  # titlul în același loc
    pngs = compozitor.carusel("Întrebare?", ["Idee"], "Pasul", IDENT)
    assert len(pngs) == 3 and all(p.startswith(b"\x89PNG") for p in pngs)


@pytest.mark.parametrize(
    ("brief", "foto", "asteptat"),
    [
        (
            {"ce_vede_publicul": "mecanicul ține bicicleta în atelier", "natura": "prezentare"},
            2,
            "foto_dominanta",
        ),
        ({"ce_vede_publicul": "pinionul uzat, în prim-plan", "natura": "prezentare"}, 1, "detaliu_explicat"),
        ({"ce_vede_publicul": "frâna pe roată", "natura": "educativ"}, 1, "detaliu_explicat"),
        ({"ce_vede_publicul": "atelierul cu biciclete", "natura": "prezentare"}, 0, "anunt"),
        ({"ce_vede_publicul": "pași de verificare", "format": "carusel"}, 0, "carusel"),
    ],
)
def test_alegerea_machetei(brief: dict[str, str], foto: int, asteptat: str) -> None:
    macheta, nota = sabloane.alege_macheta(brief, foto)
    assert macheta == asteptat
    assert bool(nota) == (asteptat == "anunt")
