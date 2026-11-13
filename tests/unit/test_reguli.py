"""F5.4 — pachetele de reguli: schema, încărcarea, exemplele fiecărei reguli (blocat / trece) rulate automat, evaluarea.
„Gata când”: fiecare regulă are un exemplu blocat și unul care trece."""

import datetime as dt
from pathlib import Path

import pytest

from app.validare import reguli
from app.validare.reguli import Context, Regula, ReguliInvalide

TOATE = reguli.toate_regulile()
IDS = [r.id for _, r in TOATE]
ASTAZI_FIX = dt.date(2026, 11, 13)  # data scrierii pachetelor de început; nu ceasul real


def canal_pachet(p: reguli.PachetIncarcat) -> str:
    c = p.pachet.canale
    return c[0] if c and c[0] != "*" else ""


def regula_minima(**kw: object) -> dict[str, object]:
    baza = {
        "id": "test-regula-1",
        "text": "O regulă de probă cu text suficient de lung.",
        "potrivire": "lista",
        "tipare": ["cuvânt interzis"],
        "severitate": "majora",
        "marcaj": "[I]",
        "verificat_la": ASTAZI_FIX,
        "sursa": {"tip": "lege", "titlu": "Un act normativ de probă", "url": "https://exemplu.test/act"},
        "exemple_blocate": ["Acesta e un cuvânt interzis aici."],
        "exemple_trece": ["Acesta e un text curat."],
    }
    return {**baza, **kw}


# --- setul de pachete de început -----------------------------------------------------------------------------------------


def test_pachetele_de_inceput_acopera_platformele_si_nisele_cerute() -> None:
    nume = {p.nume for p in reguli.incarca()}
    assert {"general", "meta", "tiktok", "linkedin", "email"} <= nume
    assert {"jocuri-de-noroc", "adulti", "politica", "finante", "sanatate"} <= nume
    canale = {c for p in reguli.incarca() for c in p.pachet.canale}
    assert {"facebook", "instagram", "tiktok", "linkedin", "email", "*"} <= canale
    assert len(TOATE) >= 20
    assert len(set(IDS)) == len(IDS), "identificatori unici în tot setul"


@pytest.mark.parametrize("pachet_regula", TOATE, ids=IDS)
def test_fiecare_regula_are_un_exemplu_blocat_si_unul_care_trece(
    pachet_regula: tuple[reguli.PachetIncarcat, Regula],
) -> None:
    p, r = pachet_regula
    assert r.exemple_blocate and r.exemple_trece
    assert reguli.verifica_exemple(r, canal_pachet(p)) == [], "exemplele se comportă ca în declarație"


@pytest.mark.parametrize("pachet_regula", TOATE, ids=IDS)
def test_fiecare_regula_are_sursa_marcaj_si_data_de_verificare(
    pachet_regula: tuple[reguli.PachetIncarcat, Regula],
) -> None:
    _, r = pachet_regula
    assert r.sursa.url.startswith("https://") and r.sursa.titlu
    assert r.marcaj == "[I]", "nicio sursă nu a fost verificată de un om: toate rămân [I]"
    assert r.verificat_la <= ASTAZI_FIX
    assert r.severitate in ("minora", "majora", "critica")


def test_nisele_refuzate_sunt_critice_si_se_aplica_mereu() -> None:
    for p in reguli.incarca():
        if p.nume in ("jocuri-de-noroc", "adulti", "politica", "finante"):
            assert p.pachet.se_aplica == "mereu" and all(r.severitate == "critica" for r in p.pachet.reguli)
    sanatate = next(p for p in reguli.incarca() if p.nume == "sanatate")
    assert sanatate.pachet.se_aplica == "nisa" and sanatate.pachet.nisa == "sanatate"


def test_fisierele_cu_pachete_au_amprenta_stabila() -> None:
    a = {p.nume: p.amprenta for p in reguli.incarca()}
    assert all(len(v) == 64 for v in a.values())
    assert a == {p.nume: p.amprenta for p in reguli.incarca()}


# --- schema ----------------------------------------------------------------------------------------------------------------------


def test_o_regula_valida_trece_schema() -> None:
    r = Regula.model_validate(regula_minima())
    assert reguli.verifica_exemple(r) == []


@pytest.mark.parametrize(
    "stricat",
    [
        {"exemple_blocate": []},
        {"exemple_trece": []},
        {"potrivire": "calcul", "tipare": []},
        {"potrivire": "calcul", "calcul": "inexistent", "tipare": []},
        {"tipare": []},
        {"potrivire": "regex", "tipare": ["(neinchisa"]},
        {"severitate": "grava"},
        {"marcaj": "verificat?"},
        {"id": "Id Prost"},
        {"sursa": {"tip": "blog", "titlu": "Un blog oarecare", "url": "https://exemplu.test"}},
        {"sursa": {"tip": "lege", "titlu": "Act de probă", "url": "nu-e-url"}},
        {"campuri_in_plus": 1},
        {"daca_text": ["x"]},
    ],
)
def test_schema_refuza_regulile_incomplete_sau_gresite(stricat: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        Regula.model_validate(regula_minima(**stricat))


def test_exemplele_care_nu_se_comporta_ca_in_declaratie_sunt_semnalate() -> None:
    r = Regula.model_validate(
        regula_minima(exemple_blocate=["Text curat, fără nimic."], exemple_trece=["Un cuvânt interzis."])
    )
    probleme = reguli.verifica_exemple(r)
    assert len(probleme) == 2 and "nu a fost blocat" in probleme[0] and "a fost blocat" in probleme[1]


def test_incarcarea_refuza_fisiere_prost_formate_si_dubluri(tmp_path: Path) -> None:
    (tmp_path / "a.toml").write_text("nu e toml valid [[[", encoding="utf-8")
    with pytest.raises(ReguliInvalide, match=r"a\.toml"):
        reguli.incarca(tmp_path)
    (tmp_path / "a.toml").unlink()

    def pachet(nume: str, rid: str) -> str:
        return (
            f'pachet = "{nume}"\ntip = "general"\ntitlu = "Pachet de probă"\nversiune = 1\ncanale = ["*"]\n\n'
            f'[[reguli]]\nid = "{rid}"\ntext = "O regulă de probă cu text suficient."\npotrivire = "lista"\n'
            'tipare = ["interzis"]\nseveritate = "majora"\nmarcaj = "[I]"\nverificat_la = 2026-11-13\n'
            'sursa = { tip = "lege", titlu = "Act de probă", url = "https://exemplu.test" }\n'
            'exemple_blocate = ["e interzis"]\nexemple_trece = ["e permis"]\n'
        )

    (tmp_path / "unu.toml").write_text(pachet("unu", "regula-unu"), encoding="utf-8")
    (tmp_path / "doi.toml").write_text(pachet("doi", "regula-unu"), encoding="utf-8")
    with pytest.raises(ReguliInvalide, match="dublați"):
        reguli.incarca(tmp_path)


def test_pachetul_cere_canale_sau_nisa(tmp_path: Path) -> None:
    (tmp_path / "x.toml").write_text(
        'pachet = "x"\ntip = "nisa"\ntitlu = "Nișă fără nume"\nversiune = 1\n', encoding="utf-8"
    )
    with pytest.raises(ReguliInvalide):
        reguli.incarca(tmp_path)


# --- evaluare --------------------------------------------------------------------------------------------------------------------


def regula(**kw: object) -> Regula:
    return Regula.model_validate(regula_minima(**kw))


def fragmente(r: Regula, text: str, ctx: Context | None = None) -> list[str]:
    return [p.fragment for p in reguli.potriviri(r, text, ctx)]


def test_cuvant_si_lista_se_potrivesc_fara_diacritice_si_fara_majuscule_dar_pe_cuvinte_intregi() -> None:
    r = regula(
        potrivire="cuvant",
        tipare=["garanție", "miraculos"],
        exemple_blocate=["Garanție totală"],
        exemple_trece=["garantat"],
    )
    assert fragmente(r, "O GARANTIE totală, miraculos!") == ["GARANTIE", "miraculos"]
    assert fragmente(r, "Garanția nu se potrivește") == [], "doar cuvântul întreg"
    lista = regula(
        tipare=["nu o să-ți vină să crezi"],
        exemple_blocate=["Nu o sa-ti vina sa crezi"],
        exemple_trece=["altceva"],
    )
    assert fragmente(lista, "Nu o să-ți vină să crezi!") == ["Nu o să-ți vină să crezi"], (
        "fragmentul e exact din text"
    )


def test_regex_pe_textul_fara_diacritice_cu_fragment_exact_din_original() -> None:
    r = regula(
        potrivire="regex",
        tipare=[r"\bvindec\w+"],
        exemple_blocate=["Vindecă totul"],
        exemple_trece=["Alinare"],
    )
    text = "Această cafea VINDECĂ orice."
    assert fragmente(r, text) == ["VINDECĂ"]
    assert text[text.index("VINDEC") :].startswith("VINDECĂ")


def test_calculele_cu_parametri() -> None:
    maj = regula(potrivire="calcul", calcul="raport_majuscule", tipare=[], parametri={"prag": 0.5, "minim_litere": 10},
                 exemple_blocate=["TOT CE STRIGĂ ACUM"], exemple_trece=["Un text normal aici"])  # fmt: skip
    assert fragmente(maj, "OFERTA ZILEI ACUM LA TOATE") and not fragmente(maj, "Oferta zilei acum la toate")
    assert not fragmente(maj, "SCURT"), "sub numărul minim de litere nu se judecă"
    tag = regula(potrivire="calcul", calcul="hashtaguri", tipare=[], parametri={"maxim": 2},
                 exemple_blocate=["#a #b #c"], exemple_trece=["#a #b"])  # fmt: skip
    assert fragmente(tag, "#a #b #c") and not fragmente(tag, "#a #b")
    ex = regula(potrivire="calcul", calcul="semne_exclamare", tipare=[], parametri={"maxim": 2},
                exemple_blocate=["Vai!!!"], exemple_trece=["Vai!"])  # fmt: skip
    assert fragmente(ex, "Vai!!!") and not fragmente(ex, "Vai!")


def test_obligatoriu_cu_si_fara_conditie_de_text() -> None:
    r = regula(
        potrivire="obligatoriu",
        tipare=["dezabon\\w+"],
        exemple_blocate=["Salut!"],
        exemple_trece=["Dezabonare aici"],
    )
    assert fragmente(r, "Salut, vezi oferta.") == [""] and fragmente(r, "Salut. Dezabonare: link") == []
    cond = regula(potrivire="obligatoriu", tipare=["mentiune"], daca_text=["supliment\\w*"], exemple_blocate=["Supliment fără"],
                  exemple_trece=["Mențiune"])  # fmt: skip
    assert fragmente(cond, "Cafea bună.") == [], "fără suplimente, mențiunea nu e cerută"
    assert fragmente(cond, "Supliment nou.") == [""]
    assert fragmente(cond, "Supliment nou. Mențiune: ok.") == []


def test_conditia_pe_camp_si_restrictia_pe_canal_si_tip() -> None:
    r = regula(conditie={"camp": "sponsorizat", "este": True}, tipare=["interzis"])
    assert fragmente(r, "e interzis", Context(campuri={"sponsorizat": True})) == ["interzis"]
    assert fragmente(r, "e interzis", Context(campuri={"sponsorizat": False})) == []
    assert fragmente(r, "e interzis", Context()) == []
    c = regula(canale=["tiktok"], tipuri=["video"], tipare=["interzis"])
    assert fragmente(c, "interzis", Context(canal="tiktok", tip="video")) == ["interzis"]
    assert fragmente(c, "interzis", Context(canal="facebook", tip="video")) == []
    assert fragmente(c, "interzis", Context(canal="tiktok", tip="postare")) == []


def test_selectia_pachetelor_pe_canal_si_nisa() -> None:
    def nume(canal: str, nise: tuple[str, ...] = ()) -> set[str]:
        return {p.nume for p in reguli.selecteaza(canal, nise)}

    fixe = {"general", "jocuri-de-noroc", "adulti", "politica", "finante"}
    assert nume("facebook") == fixe | {"meta"}
    assert nume("instagram") == fixe | {"meta"}
    assert nume("tiktok") == fixe | {"tiktok"}
    assert nume("linkedin") == fixe | {"linkedin"}
    assert nume("email") == fixe | {"email"}
    assert nume("site") == fixe, "un canal fără pachet propriu primește doar regulile comune"
    assert nume("facebook", ("sanatate",)) == fixe | {"meta", "sanatate"}


def test_o_regula_se_raporteaza_o_singura_data_pe_fragment() -> None:
    r = regula(tipare=["interzis"])
    assert fragmente(r, "interzis și iar interzis") == ["interzis"]
