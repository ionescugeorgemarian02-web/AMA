"""F5.2 — G1 Structură: nucleul pur (câmpuri obligatorii pe tip, lungimi pe canal, limba, linkuri) și datele lui."""

import datetime as dt
import uuid
from typing import Any

import pytest

from app.validare import structura, text_ro
from app.validare.date_validare import DIRECTOR, incarca
from app.validare.intrare import Continut, Intrare, SituatieLivrabil
from app.validare.verdict import Rezultat, Severitate

TEXT_RO = (
    "Cafeaua proaspătă ajunge la tine în cel mult zece zile de la prăjire, iar dacă nu îți place o schimbăm "
    "fără alte întrebări."
)


def c(text: str = TEXT_RO, **campuri: Any) -> Continut:
    return Continut(1, text, campuri)


def reguli(tip: str, canal: str, continut: Continut) -> list[str]:
    return [p.regula for p in structura.probleme_structura(tip, canal, continut)]


def verdict(tip: str, canal: str, continut: Continut):  # type: ignore[no-untyped-def]
    sit = SituatieLivrabil(uuid.uuid4(), uuid.uuid4(), tip, canal, 1, 0)
    return structura.g1(Intrare(sit, continut, dt.datetime(2026, 11, 13, tzinfo=dt.UTC)))


# --- datele
# ----------------------------------------------------------------------------------------------------


def test_datele_g1_sunt_valide_si_lungimile_sunt_marcate_neverificate() -> None:
    d = incarca("structura")
    assert {"postare", "email", "carusel", "script_video_scurt", "articol_seo"} <= set(d["tipuri"])
    for tip, r in d["tipuri"].items():
        assert r["obligatorii"], tip
        for camp in r.get("liste", {}):
            assert camp in r["obligatorii"] or camp in ("batai", "cadre", "titluri"), (tip, camp)
    for canal, campuri in d["limite"].items():
        for camp, lim in campuri.items():
            assert set(lim) <= {"maxim", "recomandat"} and lim, (canal, camp)
            if {"maxim", "recomandat"} <= set(lim):
                assert lim["recomandat"] <= lim["maxim"], (canal, camp)
    # docs/15 nu dă lungimi de caractere: orice valoare de aici e [I], iar fișierul o spune
    text = (DIRECTOR / "structura.toml").read_text(encoding="utf-8")
    assert "[I]" in text and "neverificate" in text


# --- câmpuri obligatorii
# ------------------------------------------------------------------------------------------


def test_campurile_obligatorii_pe_tip_lipsa_blocheaza() -> None:
    assert reguli("postare", "facebook", c()) == []
    assert reguli("postare", "facebook", Continut(1, "")) == ["G1.camp_lipsa"]
    r = reguli("email", "email", c(subiect="Salut"))
    assert r.count("G1.camp_lipsa") == 2, "preantet și link_dezabonare lipsesc"
    v = verdict("email", "email", c(subiect="Salut"))
    assert (
        v.rezultat is Rezultat.ESEC and "preantet" in v.instructiune and "link_dezabonare" in v.instructiune
    )


def test_campurile_goale_sau_cu_spatii_conteaza_ca_lipsa() -> None:
    cont = c(subiect="  ", preantet="Ceva scurt aici", link_dezabonare="https://zorilor.ro/dezabonare")
    assert reguli("email", "email", cont) == ["G1.camp_lipsa"]
    assert (
        reguli("carusel", "instagram", Continut(1, "", {"cadre": [], "cta": "x"})).count("G1.camp_lipsa") == 1
    )


def test_listele_au_limite_de_elemente() -> None:
    cadre = [f"Cadrul {i}" for i in range(4)]
    assert "G1.lista_in_afara_limitelor" in reguli(
        "carusel", "instagram", Continut(1, "", {"cadre": cadre, "cta": "x"})
    )
    bun = Continut(1, "", {"cadre": [*cadre, "Cadrul 5"], "cta": "Comandă azi"})
    assert reguli("carusel", "instagram", bun) == []
    prea_multe = Continut(1, "", {"cadre": [f"c{i}" for i in range(11)], "cta": "x"})
    assert "G1.lista_in_afara_limitelor" in reguli("carusel", "instagram", prea_multe)


def test_tip_necunoscut_nu_inventeaza_campuri_obligatorii() -> None:
    v = verdict("tip_nou", "facebook", c())
    assert v.rezultat is Rezultat.TRECE and v.detalii["tip_cunoscut"] is False


# --- lungimi pe canal
# -------------------------------------------------------------------------------------------------


def test_textul_peste_limita_canalului_este_respins_cu_fragmentul_si_instructiunea() -> None:
    lung = ("Cafea bună în fiecare dimineață pentru tine și familia ta. " * 50)[:2300]
    v = verdict("postare", "instagram", c(lung))
    assert v.rezultat is Rezultat.ESEC and v.severitate is Severitate.MAJORA
    assert (
        v.dovezi[0].regula == "G1.peste_limita_canal"
        and "2300" in v.instructiune
        and "2200" in v.instructiune
    )
    assert verdict("postare", "instagram", c(lung[:2200])).rezultat is Rezultat.TRECE
    pe_facebook = verdict("postare", "facebook", c(lung))
    assert not pe_facebook.blocheaza, "limita e a canalului, nu una generală (aici doar recomandarea)"


def test_hashtagurile_se_numara_pe_canal() -> None:
    tags = [f"#cafea{i}" for i in range(31)]
    assert reguli("postare", "instagram", c(hashtaguri=tags)) == ["G1.peste_limita_canal"]
    assert reguli("postare", "instagram", c(hashtaguri=tags[:30])) == []
    assert reguli("postare", "tiktok", c(hashtaguri=tags[:6])) == ["G1.peste_recomandarea_canalului"]


def test_recomandarea_canalului_este_doar_avertisment() -> None:
    subiect = "Un subiect de email care este mult prea lung pentru ecranul unui telefon obișnuit"
    cont = c(subiect=subiect, preantet="Scurt preantet aici", link_dezabonare="https://zorilor.ro/d")
    assert len(subiect) > 60
    v = verdict("email", "email", cont)
    assert v.rezultat is Rezultat.AVERTISMENT and v.severitate is Severitate.MINORA


def test_titlurile_unei_reclame_se_verifica_fiecare() -> None:
    cont = c(titluri=["Cafea proaspătă", "x" * 41], descriere="Descriere scurtă")
    assert reguli("reclama_text", "reclama", cont) == ["G1.peste_limita_canal"]


# --- limba ------------------------------------------------------------------------------------------------
# ---------------


def test_un_text_in_engleza_este_respins() -> None:
    en = "Our fresh coffee reaches you within ten days of roasting and we will replace it if you do not like it."
    assert text_ro.detecteaza_limba(en).cod == "en"
    assert reguli("postare", "facebook", c(en)) == ["G1.limba"]


def test_romana_fara_diacritice_este_tot_romana_iar_textul_scurt_nu_se_judeca() -> None:
    fara = "Cafeaua proaspata ajunge la tine in cel mult zece zile de la prajire, iar daca nu iti place o schimbam."
    assert text_ro.detecteaza_limba(fara).cod == "ro"
    assert text_ro.detecteaza_limba("Hello world").cod == "prea_scurt"
    assert reguli("postare", "facebook", c("Cafea bună!!!!")) == [] or reguli(
        "postare", "facebook", c("Cafea bună!!!!")
    ) == ["G1.text_prea_scurt"]


def test_o_limba_straina_neidentificata_este_semnalata() -> None:
    hu = "Friss kávénk tíz napon belül megérkezik hozzád a pörkölés után és szívesen kicseréljük ha nem ízlik"
    assert text_ro.detecteaza_limba(hu).cod == "necunoscuta"
    assert reguli("postare", "facebook", c(hu)) == ["G1.limba"]
    # F5.7: germana (ca franceza, spaniola, italiana) este recunoscută ca limbă străină
    de = "Unser frischer Kaffee kommt innerhalb von zehn Tagen nach der Röstung bei Ihnen an und wir tauschen ihn um"
    assert text_ro.detecteaza_limba(de).cod == "strain"
    assert reguli("postare", "facebook", c(de)) == ["G1.limba"]


def test_adresele_si_hashtagurile_nu_conteaza_la_limba() -> None:
    cuvinte = text_ro.cuvinte("Vezi https://zorilor.ro/abonament #cafea @cafeneaua office@zorilor.ro gata")
    assert cuvinte == ["Vezi", "gata"]


# --- linkuri ----------------------------------------------------------------------------------------------
# -------------------


@pytest.mark.parametrize(
    "link",
    [
        "https://cafeneauazorilor.ro",
        "http://zorilor.ro/a-b?x=1#y",
        "www.zorilor.ro",
        "https://sub.zorilor.ro:8080/p",
    ],
)
def test_linkuri_bune(link: str) -> None:
    assert text_ro.motiv_link_invalid(link) is None


@pytest.mark.parametrize(
    "link",
    ["https://cafeneaua", "ftp://zorilor.ro", "https://zorilor..ro", "https://zorilor.r0", "https://zorilor.ro:99999",
     "https://-zorilor.ro", "https://u:p@zorilor.ro", "https://zor ilor.ro"],
)  # fmt: skip
def test_linkuri_rele(link: str) -> None:
    assert text_ro.motiv_link_invalid(link)


def test_linkurile_prost_formate_din_text_si_din_campuri_sunt_respinse() -> None:
    assert reguli("postare", "facebook", c(TEXT_RO + " Vezi https://zorilor.ro/abonament.")) == []
    assert reguli("postare", "facebook", c(TEXT_RO + " Vezi http:/zorilor.ro")) == ["G1.link_prost_format"]
    assert reguli("postare", "facebook", c(TEXT_RO + " Vezi https//zorilor.ro")) == ["G1.link_prost_format"]
    assert reguli("postare", "facebook", c(TEXT_RO + " Vezi https://zorilor")) == ["G1.link_prost_format"]
    assert reguli("postare", "facebook", c(link="https://zor ilor.ro")) == ["G1.link_prost_format"]
    v = verdict("postare", "facebook", c(TEXT_RO + " Vezi https://zorilor"))
    assert v.dovezi[0].fragment == "https://zorilor" and "bine format" in v.instructiune


def test_un_text_bun_trece_si_mai_multe_probleme_devin_un_singur_verdict() -> None:
    assert verdict("postare", "facebook", c()).rezultat is Rezultat.TRECE
    rau = Continut(1, "Scurt", {"hashtaguri": [f"#t{i}" for i in range(40)]})
    v = verdict("postare", "instagram", rau)
    assert v.rezultat is Rezultat.ESEC and {d.regula for d in v.dovezi} == {
        "G1.text_prea_scurt",
        "G1.peste_limita_canal",
    }
