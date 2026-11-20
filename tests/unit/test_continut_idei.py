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


def test_stockul_nu_cere_continuitate_sau_reactii_jucate() -> None:
    acelasi = concept(cadre=cadre_cu(3, subiect="același client", context="aceeași bucătărie, a doua zi"))
    p = idei.probleme_concept(acelasi, FAPTE)
    assert any("cadrul 4 cere continuitate" in x for x in p), p
    reactie = concept(cadre=cadre_cu(0, subiect="trecătorii", actiune="întorc capul spre mâna care deschide"))
    p = idei.probleme_concept(reactie, FAPTE)
    assert any("cadrul 1 cere o reacție jucată" in x for x in p), p
    # pe materialul propriu (filmat la client, regizat) continuitatea e permisă
    propriu = concept(
        cadre=cadre_cu(3, context="aceeași bucătărie, a doua zi", interogari=[]), material_propriu=[2, 4]
    )
    assert idei.probleme_concept(propriu, FAPTE) == []


def test_cadrele_de_stock_obiectate_de_critic_pica_validarea() -> None:
    ob = [
        "Cadrul 4 (toarnă apa) nu se găsește în stock cu bucătăria asta; filmează la client.",
        "Cadrele 1 și 3 sunt bune, ușor de găsit.",  # fără semn de nefezabilitate: nu contează
        "Cadrul 2 e prezentat drept prăjitoria, dar e material propriu.",  # material propriu: nu e stock
    ]
    assert idei.cadre_obiectate(ob) == {4: ob[0], 2: ob[2]}
    p = idei.probleme_concept(concept(), FAPTE, obiectii=ob)
    assert p == [f"cadrul 4 obiectat de critic: {ob[0]}"], p


def test_fezabilitatea_sub_3_elimina() -> None:
    prop = idei.PropunereIdei(concepte=[concept(), concept(titlu="Al doilea")], incredere=0.9)
    cr = _critica((1, 4, 4), (2, 4, 4))
    cr.evaluari[0].fezabilitate = 2
    a = idei.alege(prop, cr, FAPTE)
    assert a.ales is not None and a.ales.nr == 2
    assert "fezabilitate" in next(e for e in a.evaluate if e.nr == 1).eliminat


def test_varianta_imbunatatita_castiga_cand_conceptul_mai_bine_notat_e_obiectat() -> None:
    """Cazul real Spița: conceptul cu nota cea mai mare are cadre de stock obiectate (reacții jucate,
    „aceeași intersecție, a doua zi”); varianta îmbunătățită de critic a altui concept trece și câștigă."""
    jucat = concept(
        titlu="Frâna la semafor",
        cadre=cadre_cu(3, subiect="pietoni pe trecere", actiune="întorc capul spre client",
                       context="aceeași intersecție, a doua zi"),
    )  # fmt: skip
    slab = concept(titlu="Balconul", cadre=cadre_cu(0, context="același hol, a doua zi"))
    prop = idei.PropunereIdei(concepte=[jucat, slab], incredere=0.9)
    cr = idei.CriticaIdei(
        evaluari=[
            idei.EvaluareConcept(nr=1, specificitate=5, realism=5, relevanta=5, fezabilitate=3, noutate=3,
                                 onestitate=3, obiectii=["Cadrul 4 (pietonii) nu se găsește în stock."]),
            idei.EvaluareConcept(nr=2, specificitate=4, realism=4, relevanta=5, fezabilitate=3, noutate=4,
                                 onestitate=3, obiectii=["Cadrul 1 e prezentat ca același om; stockul nu poate garanta."]),
        ],
        nr_imbunatatit=2,
        imbunatatit=concept(titlu="Balconul, refăcut"),
        incredere=0.9,
    )  # fmt: skip
    a = idei.alege(prop, cr, FAPTE)
    assert (
        a.ales is not None and a.ales.sursa == "imbunatatit" and a.ales.concept.titlu == "Balconul, refăcut"
    )
    assert a.ales.scor == 23 and a.ales.probleme == []  # obiecțiile originalului nu i se mai aplică
    assert not next(e for e in a.evaluate if e.nr == 1).bun


def test_verbe_de_miscare_si_gestul_spre_cineva() -> None:
    c = concept(cadre=cadre_cu(3, subiect="autobuzul plin", actiune="trece prin stație"))
    assert not any("static" in x for x in idei.probleme_concept(c, FAPTE))
    c = concept(cadre=cadre_cu(2, subiect="mecanicul", actiune="îi arată clientului devizul"))
    assert not any("static" in x for x in idei.probleme_concept(c, FAPTE))


def test_titlul_imaginii_vine_din_concept_nu_din_hook() -> None:
    from app.continut import brief

    assert (
        brief.titlu_imagine({"titlu": "Frâna care cântă la semafor"}, "Revizia")
        == "Frâna care cântă la semafor"
    )
    lung = {"titlu": "Bicicleta scoasă de pe balcon în prima dimineață rece, înainte de iarnă"}
    t = brief.titlu_imagine(lung)
    assert t == "Bicicleta scoasă de pe balcon în prima" and len(t.split()) <= brief.TITLU_IMAGINE_CUVINTE
    assert brief.titlu_imagine(None, "Revizia Urbană") == "Revizia Urbană"


# --- inventarul: conceptul e realizabil cu ce există acum ---

GOL = idei.Inventar("Atelierul Spița")
PROPRII = [1, 2, 3]  # trei cadre care arată clientul real, din cinci


def _propriu(nr: list[int]) -> idei.Concept:
    cadre = concept_zorilor("F1")["cadre"]
    for i in nr:
        cadre[i - 1] = {**cadre[i - 1], "interogari": []}
    return concept(cadre=cadre, material_propriu=nr)


def test_material_propriu_fara_inventar_e_nerealizabil_peste_un_cadru() -> None:
    assert idei.fara_material(concept(), GOL) == [2]  # un singur cadru de filmat: realizabil
    assert idei.probleme_concept(concept(), FAPTE, inventar=GOL) == []
    p = idei.probleme_concept(_propriu(PROPRII), FAPTE, inventar=GOL)
    assert [x for x in p if x.startswith(idei.NEREALIZABIL)] == [
        f"{idei.NEREALIZABIL}: cadrele 1, 2, 3 cer material propriu pe care clientul nu îl are "
        "(0 fotografii, 0 filmări proprii); cel mult 1 se filmează, restul se arată cu stock generic, "
        "fără a numi clientul"
    ], p
    assert idei.probleme_concept(_propriu(PROPRII), FAPTE) == []  # fără inventar: regula nu se aplică


def test_inventarul_acopera_cadrele_proprii_dupa_subiect_si_tip() -> None:
    inv = idei.Inventar(
        "Atelierul Spița",
        (("filmare", "boabele de cafea în prăjitor"), ("fotografie", "mâna baristului cu pachetul")),
    )
    c = _propriu([1, 2, 3])
    # 2 (video, boabe) are filmare; 3 (foto, mâna baristului) are fotografie; 1 (video, mâna clientului) nu
    assert idei.fara_material(c, inv) == [1]
    assert not any(x.startswith(idei.NEREALIZABIL) for x in idei.probleme_concept(c, FAPTE, inventar=inv))
    doar_foto = idei.Inventar("", (("fotografie", "boabele de cafea"),))
    assert idei.fara_material(concept(), doar_foto) == [2]  # la video, o fotografie nu e o filmare
    t = inv.text()
    assert "1 fotografii și 1 filmări" in t and "boabele de cafea în prăjitor" in t and "Stock real" in t
    assert "NU are nicio filmare proprie" in GOL.text()


def test_stockul_nu_numeste_clientul() -> None:
    for camp, val in (("context", "în atelierul Spița, pe stand"), ("subiect", "mecanicul Spița")):
        c = concept(cadre=cadre_cu(0, **{camp: val}))
        p = idei.probleme_concept(c, FAPTE, inventar=GOL)
        assert any("cadrul 1 e stock, dar numește clientul" in x for x in p), p
    generic = concept(cadre=cadre_cu(0, context="un atelier de biciclete, pe stand"))
    assert idei.probleme_concept(generic, FAPTE, inventar=GOL) == []


def test_alegerea_prefera_conceptul_realizabil_apoi_cere_filmarea() -> None:
    prop = idei.PropunereIdei(concepte=[_propriu(PROPRII), concept(titlu="Din stock")], incredere=0.9)
    cr = _critica((1, 5, 5), (2, 4, 4))  # nerealizabilul are scor mai mare
    a = idei.alege(prop, cr, FAPTE, inventar=GOL)
    assert a.ales is not None and a.ales.nr == 2 and a.de_filmat == [2], a.motiv
    assert "de filmat: cadrul 2" in a.motiv
    assert not a.evaluate[0].realizabil and a.evaluate[0].bun
    # niciunul realizabil: cel mai bun, cu cererea de filmare pe cadrele proprii
    prop2 = idei.PropunereIdei(concepte=[_propriu(PROPRII), _propriu([1, 2])], incredere=0.9)
    a2 = idei.alege(prop2, cr, FAPTE, inventar=GOL)
    assert a2.ales is not None and a2.ales.nr == 1 and a2.de_filmat == PROPRII
    assert f"niciun concept {idei.NEREALIZABIL}: se cere filmarea cadrelor 1, 2, 3" in a2.motiv
