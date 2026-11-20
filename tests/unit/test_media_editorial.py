"""Verdictul editorial (F-editorial, decizia 7): nucleul pur, fără bază și fără fișiere video."""

import io

from PIL import Image

from app.media import control, sabloane
from app.media.control import EvaluareVizuala, ImagineEditoriala, ScenaEditoriala
from tests.media_utile import fotografie_procedurala


def _scene(*roluri: tuple[str | None, str | None]) -> list[ScenaEditoriala]:
    n = len(roluri)
    return [ScenaEditoriala(k, a, r, f"{r}: {a}", 0 < k < n - 1) for k, (a, r) in enumerate(roluri)]


def test_sigla_in_scenele_2_4_respinge_si_trimite_la_selectie() -> None:
    sc = _scene(("f", "fotografie"), ("f", "fotografie"), ("s", "logo"), ("s", "logo"), ("s", "logo"))
    motive = control.judeca(scene=sc, imagini=[], lipsa=[])
    assert [m.regula for m in motive] == ["sigla_singurul_subiect"]
    assert motive[0].scene == (2, 3, 4)
    assert control.mesaj(motive) == (
        "selectie",
        "Scenele 2–4 folosesc aceeași siglă. Revino la selecția materialelor.",
    )


def test_acelasi_activ_in_doua_batai_e_repetare_hook_si_apelul_pot_refolosi() -> None:
    bun = _scene(("a", "fotografie"), ("a", "fotografie"), ("b", "fotografie"), ("c", "fotografie"),
                 ("a", "fotografie"))  # fmt: skip
    assert control.judeca(scene=bun, imagini=[], lipsa=[]) == []
    rau = _scene(("a", "fotografie"), ("a", "fotografie"), ("a", "fotografie"), ("c", "fotografie"),
                 ("c", "fotografie"))  # fmt: skip
    m = control.judeca(scene=rau, imagini=[], lipsa=[])
    assert [x.regula for x in m] == ["activ_repetat"] and m[0].scene == (1, 2)


def test_material_lipsa_versiune_alta_si_text_iesit() -> None:
    im = ImagineEditoriala("feed.png", 1080, 1350, ((40, 1300, 900, 1400),), True, 1, 0.2)
    m = control.judeca(
        scene=[], imagini=[im], lipsa=[(1, "frâna"), (2, "lanțul")], ecrane=[("Revizie", (-10, 0, 300, 80))],
        versiune_livrabil=3, versiune_export=2,
    )  # fmt: skip
    assert [x.regula for x in m] == ["material_lipsa", "text_iesit", "text_iesit", "alta_versiune"]
    etapa, text = control.mesaj(m)
    assert etapa == "material" and text.startswith("Scenele 1–2 nu au material") and "Încarcă" in text


def test_imaginea_doar_cu_text_si_sigla_e_respinsa() -> None:
    ident = sabloane.propune_identitate("Atelierul Spița")
    plat = io.BytesIO()
    Image.new("RGB", (1080, 1350), ident["culori"]["fundal"]).save(plat, "PNG")
    assert control.plata(plat.getvalue()) > control.PLAT_PRAG
    assert control.plata(fotografie_procedurala()) < control.PLAT_PRAG
    im = ImagineEditoriala("anunt.png", 1080, 1350, (), True, 0, control.plata(plat.getvalue()))
    m = control.judeca(scene=[], imagini=[im], lipsa=[])
    assert m[0].regula == "sigla_singurul_subiect" and "doar text și siglă" in m[0].detalii


def test_starea_evaluarii_vizuale() -> None:
    assert control.stare_evaluare(None) == "neverificata"
    assert (
        control.stare_evaluare(EvaluareVizuala("model", cu_imagini=False, modele=("a", "b")))
        == "neverificata"
    )
    assert (
        control.stare_evaluare(EvaluareVizuala("model", cu_imagini=True, modele=("a", "a"))) == "autoevaluare"
    )
    assert control.stare_evaluare(EvaluareVizuala("model", cu_imagini=True, modele=("a", "b"))) == "evaluator"
    assert control.stare_evaluare(EvaluareVizuala("operator")) == "operator"


def test_plansa_are_o_celula_pe_cadru_cu_eticheta() -> None:
    cadre = [
        (f"Scena {k}", "fotografie: lanț", fotografie_procedurala(320, 568, samanta=k)) for k in range(5)
    ]
    img = Image.open(io.BytesIO(control.plansa(cadre)))
    assert img.size[0] == 4 * (270 + 12) + 12 and img.size[1] > 2 * 480  # 4 coloane, 2 rânduri
    assert control.interval([1, 3]) == "Scenele 1, 3" and control.interval([2]) == "Scena 2"
