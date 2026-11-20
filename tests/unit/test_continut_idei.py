"""F-idee — validarea deterministă a conceptelor (`probleme_concept`) și alegerea (`alege`), fără bază și fără model."""

from typing import Any

from app.continut import idei
from tests.onboarding_utile import concept_zorilor

FAPTE: dict[str, dict[str, Any]] = {"F1": {"tip": "fapt", "text": "Prăjim cafeaua în fiecare săptămână."}}


def concept(**kw: Any) -> idei.Concept:
    return idei.Concept.model_validate(concept_zorilor(**{"dovada": "F1", **kw}))


def cadre_cu(i: int, **cadru: Any) -> list[dict[str, Any]]:
    cadre = concept_zorilor("F1")["cadre"]
    cadre[i] = {**cadre[i], **cadru}
    return cadre  # type: ignore[no-any-return]


def test_conceptul_bun_trece_si_la_video() -> None:
    assert idei.probleme_concept(concept(), FAPTE) == []
    assert idei.probleme_concept(concept(), FAPTE, video=True) == []


def test_cadrul_static_e_respins() -> None:
    c = concept(cadre=cadre_cu(2, subiect="pachetul de cafea", actiune="stă pe masă lângă râșniță"))
    p = idei.probleme_concept(c, FAPTE)
    assert any("cadrul 3 e static" in x and "descrie o stare" in x for x in p), p


def test_cadrul_vag_e_respins() -> None:
    c = concept(cadre=cadre_cu(0, subiect="atmosferă premium și dinamică"))
    p = idei.probleme_concept(c, FAPTE)
    assert any("cadrul 1 e vag" in x for x in p), p
    c = concept(cadre=cadre_cu(0, subiect="calitatea și încrederea"))
    assert any("cadrul 1 e vag" in x for x in idei.probleme_concept(c, FAPTE))


def test_video_cu_sub_60_la_suta_miscare_e_respins() -> None:
    cadre = concept_zorilor("F1")["cadre"]
    for i in (0, 1):
        cadre[i] = {**cadre[i], "tip": "foto"}
    c = concept(cadre=cadre)  # 1 din 4 cadre cu imagine e filmare
    assert any("la video" in x for x in idei.probleme_concept(c, FAPTE, video=True))
    assert not any("la video" in x for x in idei.probleme_concept(c, FAPTE, video=False))


def test_stock_pe_material_propriu_e_respins() -> None:
    c = concept(cadre=cadre_cu(1, interogari=["coffee roaster beans"]))  # cadrul 2 e material propriu
    p = idei.probleme_concept(c, FAPTE)
    assert any("cadrul 2" in x and "nu se acoperă cu stock" in x for x in p), p


def test_dovada_text_si_obiecte_si_interogari() -> None:
    assert any("dovada" in x for x in idei.probleme_concept(concept(dovada="F9"), FAPTE))
    cadre = cadre_cu(0, tip="text")
    assert any("cadre doar cu text" in x for x in idei.probleme_concept(concept(cadre=cadre), FAPTE))
    obiecte = [
        {"subiect": s, "actiune": "se rotește încet", "context": "atelier", "tip": "video", "incadrare": "detaliu",
         "interogari": ["bicycle wheel spinning", "bike chain close up"]}
        for s in ("roata bicicletei", "lanțul", "pinionul", "pedala")
    ]  # fmt: skip
    p = idei.probleme_concept(concept(cadre=obiecte, material_propriu=[]), FAPTE)
    assert any("arată doar obiecte" in x for x in p), p
    ro = cadre_cu(0, interogari=["mână deschide pachet", "cafea"])
    assert any("în engleză" in x for x in idei.probleme_concept(concept(cadre=ro), FAPTE))


def _critica(*note: tuple[int, int, int]) -> idei.CriticaIdei:
    """(nr, realism, onestitate) pe concepte, restul notelor 4."""
    return idei.CriticaIdei(
        evaluari=[
            idei.EvaluareConcept(nr=n, specificitate=4, realism=r, relevanta=4, fezabilitate=4, noutate=4,
                                 onestitate=o, obiectii=[f"obiecția {n}"])
            for n, r, o in note
        ],
        incredere=0.9,
    )  # fmt: skip


def test_alegerea_elimina_realismul_slab_si_conceptele_invalide() -> None:
    static = concept(cadre=cadre_cu(2, actiune="stă pe masă"))
    prop = idei.PropunereIdei(concepte=[concept(), static, concept(titlu="Al treilea")], incredere=0.9)
    cr = _critica((1, 2, 5), (2, 5, 5), (3, 4, 4))
    a = idei.alege(prop, cr, FAPTE)
    assert a.ales is not None and a.ales.nr == 3, a.motiv  # 1 eliminat la realism, 2 static
    assert next(e for e in a.evaluate if e.nr == 1).eliminat.startswith("eliminat la realism")
    # varianta îmbunătățită a criticului moștenește notele și, la egalitate, câștigă
    cr2 = cr.model_copy(update={"nr_imbunatatit": 3, "imbunatatit": concept(titlu="Al treilea, mai bun")})
    a2 = idei.alege(prop, cr2, FAPTE)
    assert a2.ales is not None and a2.ales.sursa == "imbunatatit"
    # nimic bun: de rescris cel mai bun nereușit
    a3 = idei.alege(prop, _critica((1, 2, 5), (2, 5, 5), (3, 1, 1)), FAPTE)
    assert a3.ales is None and a3.de_rescris is not None and a3.de_rescris.nr == 2


def test_storyboardul_foloseste_cadrele_conceptului_ca_indicatii() -> None:
    import uuid

    from app.media import regizor, selectie

    cadre = concept_zorilor("F1")["cadre"]
    script = {
        "hook": "Ce gust are cafeaua proaspătă?",
        "batai": [{"voce": "Deschizi pachetul.", "text_ecran": "", "vizual": ""}],
        "cta": "Comandă acum.",
        "cadre": cadre,
    }
    scene = regizor.scene_script(script)
    assert scene[1].obligatorie and scene[1].video and "hands opening coffee bag" in scene[1].alternative
    assert regizor.scene_script({k: v for k, v in script.items() if k != "cadre"})[1].alternative == ()
    foto = selectie.Candidat(uuid.UUID(int=1), "fotografie", "foto", subiect="hands opening coffee bag")
    film = selectie.Candidat(uuid.UUID(int=2), "filmare", "video", subiect="hands opening coffee bag")
    ales = selectie.alege(scene, [foto, film])[1]
    assert ales.activ_id == film.id and ales.scor == 1.0  # potrivire pe interogare, filmarea la scor egal
