"""F6.3 — nucleele pure: editorul (E8) și scorul hook-urilor (E1)."""

from app.continut import editor, scriere

BRIEF = {
    "subiect": "Data prăjirii pe pachet",
    "fapte_permise": [{"text": "Etiopia Guji, 250 g, costă 49 lei"}],
}


def test_editorul_corecteaza_sedila_ghilimele_spatii_si_sabloanele() -> None:
    t = 'În concluzie, cafeaua  e "proaspătă". Fără îndoială, o prăjim aici. Ştii de ce?'
    assert editor.editeaza(t) == "Cafeaua e „proaspătă”. O prăjim aici. Știi de ce?"


def test_editorul_nu_schimba_faptele() -> None:
    t = "Etiopia Guji, 250 g, costă 49 lei. Livrarea e gratuită peste 150 lei."
    assert editor.editeaza(t) == t
    assert editor.editeaza("Costă   49 lei.") == "Costă 49 lei."


def test_scorul_hook_ului() -> None:
    bun, p_bun = scriere.scor_hook("Știi ce înseamnă data prăjirii?", BRIEF)
    cifra, p_cifra = scriere.scor_hook("În 10 zile, totul se schimbă.", BRIEF)
    slab, p_slab = scriere.scor_hook("Bună ziua, azi vă spunem o poveste.", BRIEF)
    _, p_pret = scriere.scor_hook("Etiopia Guji costă 49 lei: știi de ce?", BRIEF)
    assert p_bun == [] and "cifra_fara_fapt" in p_cifra and "G8.hook_deschidere_slaba" in p_slab
    assert p_pret == []  # cifra vine dintr-un fapt permis
    assert bun > slab and bun > cifra
    hookuri = [
        scriere.HookPropus(text=t, tipar="intrebare")
        for t in ("În 10 zile, totul se schimbă.", "Știi ce înseamnă data prăjirii?")
    ]
    assert scriere.alege(hookuri, BRIEF) == 1
