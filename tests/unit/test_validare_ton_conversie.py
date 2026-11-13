"""F5.5 — G4 Ton și G8 Lizibilitate și conversie: nucleele pure (vocabular, similaritate, apeluri la acțiune, hook, lizibilitate)."""

import datetime as dt
import uuid

import pytest

from app.validare import conversie, ton
from app.validare.date_validare import incarca
from app.validare.intrare import Continut, Intrare, SituatieLivrabil
from app.validare.verdict import Rezultat, Severitate

# --- G4: ghid și vocabular -------------------------------------------------------------------------------------------------------

GHID = ton.Ghid(
    nume="Barista prietenos",
    descriere="Cald și simplu.",
    reguli_da=("Spune pe nume ce e în pachet",),
    reguli_nu=("Nu promite efecte medicale",),
    vocabular_preferat=("proaspăt", "degustare", "prăjit în loturi mici"),
    vocabular_interzis=("ieftin", "miraculos", "revoluționar", "top"),
    exemple=(
        ("facebook", "Sâmbătă facem degustare."),
        ("email", "Pachetul pleacă marți."),
        ("site", "Prăjim în loturi mici."),
    ),
)


def test_ghidul_se_citeste_din_continutul_intrarii_si_refuza_ce_nu_arata_a_ghid() -> None:
    g = ton.ghid_din(
        {
            "nume": "X", "descriere": "d", "reguli_da": ["a"], "reguli_nu": ["b"], "vocabular_preferat": ["c"],
            "vocabular_interzis": ["d"], "exemple": [{"canal": "email", "text": "Salut!"}, {"canal": "x"}, "nu"],
        },
        3,
    )  # fmt: skip
    assert g is not None and g.exemple == (("email", "Salut!"),) and g.versiune == 3
    assert ton.ghid_din({"pozitionare": "Prăjitorie"}) is None
    assert ton.ghid_din({"exemple": []}) is None


def test_exemplele_se_aleg_dupa_canal_iar_daca_nu_exista_toate() -> None:
    assert GHID.exemple_pentru("email") == ["Pachetul pleacă marți."]
    assert GHID.exemple_pentru("tiktok") == [t for _, t in GHID.exemple]


def test_cuvantul_interzis_se_gaseste_cu_formele_lui_fara_diacritice_si_majuscule() -> None:
    assert ton.gaseste_in_text("Cea mai ieftină cafea, ieftin și IEFTINE!", "ieftin") == [
        "ieftină",
        "ieftin",
        "IEFTINE",
    ]
    assert ton.gaseste_in_text("Un efect miraculos", "miraculos") == ["miraculos"]
    assert ton.gaseste_in_text("O soluție revoluționară", "revoluționar") == ["revoluționară"]


def test_cuvintele_scurte_se_potrivesc_exact_nu_ca_prefix() -> None:
    assert ton.gaseste_in_text("Un top al cafelelor", "top") == ["top"]
    assert ton.gaseste_in_text("Topul și topirea, stop!", "top") == []


def test_expresiile_se_potrivesc_ca_atare() -> None:
    assert ton.gaseste_in_text("Banii înapoi, garantat", "banii înapoi") == ["Banii înapoi"]
    assert ton.gaseste_in_text("Banii nu se întorc", "banii înapoi") == []
    assert ton.gaseste_in_text("orice", "  ") == []


def test_vocabularul_interzis_blocheaza_iar_lipsa_celui_preferat_doar_avertizeaza() -> None:
    p = ton.probleme_vocabular("Cea mai ieftină cafea din oraș.", GHID)
    assert [x.regula for x in p] == ["G4.vocabular_interzis"] and p[0].blocant and p[0].fragment == "ieftină"
    lung = "Cafeaua noastră ajunge la tine în fiecare lună, pentru ca dimineața să înceapă bine și fără grabă pentru nimeni, oricând. Vă așteptăm cu drag în fiecare zi a săptămânii, de dimineață până seara."
    pref = ton.probleme_vocabular(lung, GHID)
    assert [x.regula for x in pref] == ["G4.fara_vocabular_preferat"] and not pref[0].blocant
    assert ton.probleme_vocabular(lung + " Cafea proaspătă.", GHID) == []
    assert ton.probleme_vocabular("Scurt.", GHID) == [], (
        "textele scurte nu primesc avertismentul de vocabular preferat"
    )


def test_datele_g4_sunt_valide() -> None:
    d = incarca("ton")
    assert 0 < d["similaritate"]["prag"] < 1 and d["similaritate"]["exemple_maxim"] >= 3


# --- G4: similaritate ---------------------------------------------------------------------------------------------------------------


def test_cosinusul_este_in_zero_unu_si_gestioneaza_vectorii_nuli() -> None:
    assert ton.cosinus([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert ton.cosinus([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert ton.cosinus([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert ton.cosinus([1.0, 0.0], [-1.0, 0.0]) == 0.0, "anti-corelarea nu dă scor negativ"


def test_cel_mai_apropiat_exemplu() -> None:
    scor, i = ton.cea_mai_apropiata([1.0, 0.0], [[0.0, 1.0], [0.9, 0.1], [0.5, 0.5]])
    assert i == 1 and scor > 0.99


# --- G8: apeluri la acțiune ------------------------------------------------------------------------------------------------------------


def grupe(text: str, **campuri: object) -> list[str]:
    return [a.grupa for a in conversie.grupe_distincte(Continut(1, text, dict(campuri)))]


def test_doua_apeluri_din_grupe_diferite_sunt_respinse() -> None:
    assert grupe("Comandă acum pe site și urmărește-ne pe Instagram.") == ["cumparare", "social"]
    p = conversie.probleme_apeluri(
        "postare", Continut(1, "Comandă acum pe site și urmărește-ne pe Instagram.")
    )
    assert (
        [x.regula for x in p] == ["G8.apeluri_multiple"] and p[0].blocant and "2 apeluri" in p[0].instructiune
    )
    assert p[0].fragment == "urmărește-ne"
    assert grupe("Vino sâmbătă la degustare și înscrie-te.") == ["vizita", "inscriere"]


def test_mai_multe_forme_din_aceeasi_grupa_sunt_un_singur_apel() -> None:
    assert grupe("Comandă acum. Comandă azi pe site și profită de reducere.") == ["cumparare"]
    assert conversie.probleme_apeluri("postare", Continut(1, "Cumpără azi și profită de reducere.")) == []


def test_fara_apel_avertizeaza_doar_la_tipurile_care_il_cer() -> None:
    p = conversie.probleme_apeluri("postare", Continut(1, "Cafea bună în fiecare dimineață."))
    assert [x.regula for x in p] == ["G8.fara_apel_la_actiune"] and not p[0].blocant
    assert conversie.probleme_apeluri("raspuns_inbox", Continut(1, "Cafea bună în fiecare dimineață.")) == []


def test_campul_cta_se_numara_o_data_cu_textul() -> None:
    assert grupe("Pachetul pleacă marți. Comandă acum!", cta="Comandă acum") == ["cumparare"]
    assert grupe("Pachetul pleacă marți.", cta="Fii parte din poveste") == ["cta_camp"], (
        "câmpul însuși e apelul"
    )
    assert grupe("Comandă acum!", cta="Urmărește-ne") == ["cumparare", "social"]


def test_formele_ambigue_cu_substantive_nu_sunt_apeluri() -> None:
    assert grupe("Comanda ta ajunge marți. Rezerva de boabe e mare. Cum sună? Foarte bine, vezi tu.") == []


# --- G8: hook și lizibilitate ----------------------------------------------------------------------------------------------------------


def test_hook_slab_si_hook_lung() -> None:
    assert [
        p.regula for p in conversie.probleme_hook(Continut(1, "Salut dragi prieteni! Avem cafea nouă."))
    ] == ["G8.hook_deschidere_slaba"]
    lung = " ".join(["cuvânt"] * 30) + ". Apoi continuăm."
    assert [p.regula for p in conversie.probleme_hook(Continut(1, lung))] == ["G8.hook_lung"]
    assert (
        conversie.probleme_hook(
            Continut(1, "De ce are cafeaua noastră aromă de ciocolată? Pentru că o prăjim lent.")
        )
        == []
    )
    assert conversie.probleme_hook(Continut(1, "Text oarecare.", {"hook": "Bună ziua, vă informăm"})), (
        "câmpul `hook` are prioritate"
    )
    assert conversie.probleme_hook(Continut(1, "")) == []


def test_propozitiile_nu_rup_adresele() -> None:
    p = conversie.propozitii(
        "Vezi https://zorilor.ro/abonament.html pentru detalii. Apoi ne scrii!\nO linie nouă."
    )
    assert p == ["Vezi https://zorilor.ro/abonament.html pentru detalii.", "Apoi ne scrii!", "O linie nouă."]


def test_indicele_de_lizibilitate_urca_cu_frazele_scurte_si_scade_cu_cele_lungi_si_cuvintele_lungi() -> None:
    usor = conversie.lizibilitate(
        "Cafeaua ajunge la tine în zece zile. Dacă nu îți place, o schimbăm. Fără întrebări."
    )
    greu = conversie.lizibilitate(
        "Implementarea corespunzătoare a procedurilor de optimizare a experienței consumatorilor determină îmbunătățirea "
        "semnificativă a percepției generale asupra produselor comercializate de către organizația noastră, potrivit "
        "evaluărilor interdisciplinare realizate recent la nivel național și european, conform raportărilor anterioare."
    )
    assert usor.indice > 80 and greu.indice < 25 and usor.indice > greu.indice
    assert (usor.cuvinte, usor.propozitii) == (15, 3)
    assert conversie.lizibilitate("").indice == 100.0
    # formula documentată: 100 − 2 × medie − 0,8 × procent de cuvinte lungi
    assert greu.indice == pytest.approx(max(0.0, 100 - 2 * greu.medie - 0.8 * greu.procent_lungi), abs=0.2)


def test_probleme_de_lizibilitate_au_prag_minim_de_cuvinte() -> None:
    p, _ = conversie.probleme_lizibilitate("Implementarea corespunzătoare a procedurilor interdisciplinare.")
    assert p == [], "sub 20 de cuvinte nu se judecă"
    lung = ("Implementarea corespunzătoare a procedurilor de optimizare a experienței consumatorilor determină îmbunătățirea "
            "semnificativă a percepției generale asupra produselor comercializate de către organizația noastră, potrivit "
            "evaluărilor interdisciplinare realizate recent la nivel național și european, conform raportărilor anterioare.")  # fmt: skip
    p, liz = conversie.probleme_lizibilitate(lung)
    assert {x.regula for x in p} == {"G8.fraza_prea_lunga", "G8.text_greu_de_citit"} and liz.indice < 40


def test_datele_g8_sunt_valide_si_au_toate_grupele() -> None:
    d = incarca("conversie")
    assert set(d["cta"]["grupe"]) == {
        "cumparare",
        "contact",
        "navigare",
        "inscriere",
        "vizita",
        "social",
        "incercare",
    }
    assert d["lizibilitate"]["indice_minim"] < 100 and d["hook"]["cuvinte_maxim"] > 5


def intrare(text: str, tip: str = "postare", **campuri: object) -> Intrare:
    sit = SituatieLivrabil(uuid.uuid4(), uuid.uuid4(), tip, "facebook", 1, 0)
    return Intrare(sit, Continut(1, text, dict(campuri)), dt.datetime(2026, 11, 13, tzinfo=dt.UTC))


def test_verdictul_g8_spune_indicele_si_blocheaza_doar_pe_apeluri_multiple() -> None:
    v = conversie.g8_reguli(intrare("Comandă acum pe site și urmărește-ne pe Instagram."))
    assert v.rezultat is Rezultat.ESEC and v.severitate is Severitate.MAJORA and "ila" in v.detalii
    bun = conversie.g8_reguli(
        intrare("Cafeaua ajunge la tine în zece zile. Comandă acum și o primești proaspătă.")
    )
    assert bun.rezultat is Rezultat.TRECE
    slab = conversie.g8_reguli(intrare("Salut dragi prieteni! Avem cafea nouă. Comandă acum."))
    assert slab.rezultat is Rezultat.AVERTISMENT and slab.detalii["hook_slab"] is True
