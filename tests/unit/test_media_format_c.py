"""F16.1 — formatul C, nucleul pur: validarea scenelor, numărătoarea cifrei, cadrele deterministe, HTML-ul scenei."""

from app.media import formatul_c as fc

CULORI = {"primara": "#1F4E79", "fundal": "#F2F6FA", "accent": "#E8A317", "alb": "#FFFFFF", "text": "#111111"}
SCENE = [fc.ScenaC("oferta", "Oferta săptămânii", "-20%", "la toate prăjiturile"),
         fc.ScenaC("cifra", "Clienți mulțumiți", "1200", "în Brașov"),
         fc.ScenaC("anunt", "Deschidem sâmbătă", "", "<b>strada Lungă 5</b>")]  # fmt: skip


def test_scene_valide_si_invalide() -> None:
    assert fc.probleme_scene(SCENE, ["a", "b", "c"]) == []
    assert fc.probleme_scene(SCENE, ["a"])  # o scenă pe frază
    rele = [fc.ScenaC("cifra", "Fără cifră", "multe"), fc.ScenaC("oferta", "x" * 41)]
    pr = fc.probleme_scene(rele, ["a", "b"])
    assert any("numerică" in p for p in pr) and any("titlul" in p for p in pr)


def test_cifra_numara_pana_la_valoare() -> None:
    assert fc.valoare_la("1200", 0) == "0"
    assert fc.valoare_la("1200", 1) == "1200"
    assert fc.valoare_la("-20%", 1) == "-20%" and fc.valoare_la("-20%", 0) == "-0%"
    assert fc.valoare_la("49 lei", 0.5).endswith(" lei")
    assert fc.valoare_la("fără", 0.3) == "fără"


def test_cadrele_sunt_deterministe_si_animate() -> None:
    a, b = fc.cadru(SCENE[1], 0.2, CULORI), fc.cadru(SCENE[1], 0.2, CULORI)
    assert a.tobytes() == b.tobytes()
    assert fc.cadru(SCENE[1], 0.0, CULORI).tobytes() != fc.cadru(SCENE[1], 1.5, CULORI).tobytes()
    # la final fundalul e culoarea principală a brandului
    assert fc.cadru(SCENE[0], 2.0, CULORI).getpixel((5, 5)) == (0x1F, 0x4E, 0x79)


def test_html_scenei_escapeaza_si_poarta_culorile() -> None:
    h = fc.html_scene(SCENE, [2.0, 2.0, 2.0], CULORI)
    assert h.count("<section") == 3 and "#1F4E79" in h and "&lt;b&gt;" in h and "<b>" not in h
    assert 'data-start="4.000"' in h
