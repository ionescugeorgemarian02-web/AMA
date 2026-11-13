"""F5.7 — îmbunătățirile validatorilor după prima rulare a bancului (seturile NU s-au schimbat). Fiecare caz
de aici este
scris separat de seturile de aur (texte diferite), ca regula să fie generală, nu potrivită pe un exemplu
anume."""

from app.validare import afirmatii, conversie, juridic, text_ro, ton
from app.validare.ton import Ghid


def _ghid(descriere: str = "Cald și simplu, ca un prieten care știe meserie.") -> Ghid:
    return Ghid("Prietenos", descriere, ("Vorbește pe înțeles",), (), (), (), (("facebook", "Salut!"),))


def test_registru_birocratic_argou_si_jignitor_sunt_semnalate() -> None:
    birocratic = "În conformitate cu normele interne, solicitările clienților se procesează în termenul legal aplicabil."
    argou = "Bro, prăjeala de azi e beton, nebunie totală la tejghea!!!"
    jignitor = "Nu ne interesează dacă îți place, ia-o sau las-o."
    for text, cod in (
        (birocratic, "G4.registru_birocratic"),
        (argou, "G4.registru_argou"),
        (jignitor, "G4.registru_jignitor"),
    ):
        coduri = [p.regula for p in ton.probleme_registru(text, _ghid())]
        assert cod in coduri, (text, coduri)
        assert all(p.fragment in text for p in ton.probleme_registru(text, _ghid()))


def test_registrul_declarat_in_ghid_nu_se_semnaleaza_si_un_text_cald_trece() -> None:
    birocratic = "În conformitate cu normele interne, solicitările clienților se procesează în termenul legal aplicabil."
    assert ton.probleme_registru(birocratic, _ghid("Ton formal, de birou de avocatură.")) == []
    assert ton.probleme_registru("Vino sâmbătă la o cafea caldă și o poveste bună.", _ghid()) == []
    assert (
        ton.probleme_registru("Un singur „aplicabil” într-un text altfel firesc nu e birocrație.", _ghid())
        == []
    )


def test_etichetele_de_ordine_nu_sunt_afirmatii() -> None:
    tipuri = [
        (a.tip, a.fragment)
        for a in afirmatii.extrage("Pasul 3: măcinăm. Slide-ul 7: servim. Avem 12 sortimente.")
    ]
    assert ("cifra", "12") in tipuri
    assert not any(f in ("3", "7") for _, f in tipuri)


def test_apelul_la_incercare_se_numara() -> None:
    grupe = {a.grupa for a in conversie.apeluri("Încearcă rețeta de azi și scrie-ne cum ți-a ieșit.")}
    assert grupe == {"incercare", "contact"}


def test_promisiunea_negata_tot_promisiune_e() -> None:
    assert juridic.probleme_promisiuni("Garantăm că nu vei mai avea nevoie de alt ceai.")
    assert not juridic.probleme_promisiuni("Garanția produsului este de doi ani.")


def test_limba_straina_si_schema_gresita_de_link() -> None:
    assert (
        text_ro.detecteaza_limba(
            "Nous avons une nouvelle carte pour vous et pour votre famille dans notre café."
        ).cod
        == "strain"
    )
    assert (
        text_ro.detecteaza_limba("Avem o cafea nouă pentru tine și pentru familia ta, la noi în cafenea.").cod
        == "ro"
    )
    assert text_ro.linkuri_stricate_in_text("Detalii pe htpps://exemplu.test/meniu azi.") == [
        "htpps://exemplu.test/meniu"
    ]
    assert text_ro.linkuri_stricate_in_text("Detalii pe https://exemplu.test/meniu azi.") == []
    assert text_ro.linkuri_stricate_in_text("Scrie-ne pe ftp://exemplu.test.") == []
