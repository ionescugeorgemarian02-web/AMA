"""F5.5 — G4 Ton și G8 Lizibilitate și conversie, cu Postgres real. „Gata când”: un text în ton greșit este semnalat și un text cu
două apeluri la acțiune este respins. Vectorii sunt SIMULAȚI (sac de cuvinte cu hashing, ca la F4.3), judecătorii sunt un model FALS."""

# ruff: noqa: F811
import uuid

import pytest

from app import validare
from app.productie import Stare
from tests.gateway_utile import cheie_proba, fabrica_modele, fals  # noqa: F401
from tests.integration.test_creier_cautare import Model, _mediu, model  # noqa: F401
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.validare_utile import (  # noqa: F401
    LA,
    JudecatorFals,
    judecator,
    livrabil_in_validare,
    profil_aprobat,
    raspuns,
    registru_doar,
    rubrica,
    ruleaza,
)

pytestmark = pytest.mark.db

GHID = {
    "nume": "Barista prietenos",
    "descriere": "Brandul sună cald și simplu, ca un barista care explică pe îndelete.",
    "reguli_da": ["Spune pe nume ce e în pachet", "Dă data prăjirii"],
    "reguli_nu": ["Nu promite efecte medicale", "Nu compara cu alte firme"],
    "vocabular_preferat": ["proaspăt", "degustare", "prăjit în loturi mici"],
    "vocabular_interzis": ["ieftin", "miraculos"],
    "exemple": [
        {
            "canal": "facebook",
            "text": "Sâmbătă la 11:00 facem degustare gratuită la cafenea, vino să guști cafea proaspăt prăjită.",
        },
        {
            "canal": "email",
            "text": "Salut! Pachetul tău de cafea pleacă marți, proaspăt prăjit, direct de la cafenea.",
        },
        {
            "canal": "site",
            "text": "Prăjim cafeaua în loturi mici, ca fiecare pachet să ajungă proaspăt la tine acasă.",
        },
    ],
}
IN_TON = "Sâmbătă facem degustare de cafea proaspăt prăjită la cafenea, vino să guști și să afli cum o prepari acasă."
# F5.7: textul nu are markeri de registru (aceia blochează deja în V1), ca semnalul să vină din similaritate (V2)
IN_AFARA_TONULUI = (
    "Raportul trimestrial al societății arată indicatori financiari stabili pentru exercițiul curent și "
    "pentru perioada următoare."
)


@pytest.fixture
def ghid(tenant: uuid.UUID, om: uuid.UUID) -> None:
    profil_aprobat(tenant, om, GHID, cheie="ghid")


def g(rez: validare.RezultatRunda, cod: str, treapta: str | None = None) -> list[validare.Verdict]:
    return [v for v in rez.verdicte if v.validator == cod and (treapta is None or v.treapta.value == treapta)]


def ruleaza_doar(tenant: uuid.UUID, text_: str, *coduri: str, **kw: object) -> validare.RezultatRunda:
    jud = bool(kw.pop("judecatori", False))
    with registru_doar(*coduri):
        lid = livrabil_in_validare(tenant, text_, **kw)  # type: ignore[arg-type]
        return ruleaza(tenant, lid, la=LA, judecatori=jud)


# --- G4 --------------------------------------------------------------------------------------------------------------------------


def test_un_text_in_tonul_brandului_trece(tenant: uuid.UUID, ghid: None, model: Model) -> None:
    r = ruleaza_doar(tenant, IN_TON, "G4")
    assert r.stare is Stare.VALIDAT
    assert [(v.treapta.value, v.rezultat.value) for v in g(r, "G4")] == [("V1", "trece"), ("V2", "trece")]
    v2 = g(r, "G4", "V2")[0]
    assert v2.detalii["scor_similaritate"] > v2.detalii["prag"] and v2.detalii["ghid_versiune"] == 1


def test_un_text_in_ton_gresit_este_semnalat_cu_cel_mai_apropiat_exemplu(
    tenant: uuid.UUID, ghid: None, model: Model
) -> None:
    r = ruleaza_doar(tenant, IN_AFARA_TONULUI, "G4")
    [v2] = g(r, "G4", "V2")
    assert v2.rezultat.value == "avertisment" and v2.severitate is validare.Severitate.MAJORA
    assert v2.dovezi[0].regula == "G4.ton_departe_de_exemple" and "exemplele aprobate" in v2.instructiune
    assert v2.detalii["scor_similaritate"] < v2.detalii["prag"]
    assert "[G4]" in r.instructiune
    assert r.stare is Stare.VALIDAT, "un singur avertisment nu blochează; se adună pentru om"


def test_vocabularul_interzis_al_ghidului_blocheaza(tenant: uuid.UUID, ghid: None, model: Model) -> None:
    r = ruleaza_doar(tenant, "Cea mai ieftină cafea proaspătă din oraș, vino la degustare.", "G4")
    assert r.stare is Stare.IN_REPARATIE
    [v1] = g(r, "G4", "V1")
    assert v1.blocheaza and v1.dovezi[0].fragment == "ieftină" and "ghidul de brand" in v1.instructiune
    assert g(r, "G4", "V2") == [], "eșecul din V1 oprește cascada: vectorii nu se mai calculează"


def test_exemplele_ghidului_sunt_alese_dupa_canalul_livrabilului(
    tenant: uuid.UUID, ghid: None, model: Model, fals
) -> None:  # type: ignore[no-untyped-def]
    ruleaza_doar(tenant, IN_TON, "G4", canal="email")
    cereri = [c for c in fals.cereri if c.cale.endswith("/embeddings")]
    [texte] = [c.corp["input"] for c in cereri]
    assert len(texte) == 2 and "Pachetul tău de cafea pleacă marți" in texte[1], (
        "textul + exemplul de pe canalul email"
    )


def test_fara_ghid_aprobat_tonul_nu_se_verifica_dar_nu_trece_tacit(tenant: uuid.UUID, model: Model) -> None:
    r = ruleaza_doar(tenant, IN_TON, "G4")
    assert [(v.treapta.value, v.rezultat.value) for v in g(r, "G4")] == [("V1", "avertisment")]
    assert g(r, "G4")[0].dovezi[0].regula == "G4.fara_ghid_aprobat"


def test_un_ghid_neaprobat_sau_viitor_nu_se_foloseste(tenant: uuid.UUID, om: uuid.UUID, model: Model) -> None:
    import datetime as dt

    profil_aprobat(tenant, om, GHID, cheie="ghid", aprobat_la=LA + dt.timedelta(days=1))
    r = ruleaza_doar(tenant, IN_TON, "G4")
    assert g(r, "G4")[0].dovezi[0].regula == "G4.fara_ghid_aprobat"


def test_cand_vectorii_nu_sunt_disponibili_similaritatea_e_necalculata_nu_trecuta(
    tenant: uuid.UUID, ghid: None, model: Model
) -> None:
    model.opreste()
    r = ruleaza_doar(tenant, IN_TON, "G4")
    [v2] = g(r, "G4", "V2")
    assert v2.rezultat.value == "avertisment" and v2.dovezi[0].regula == "G4.similaritate_necalculata"
    assert v2.severitate is validare.Severitate.MINORA and r.stare is Stare.VALIDAT


def test_rubrica_de_ton_ruleaza_doar_cand_similaritatea_a_semnalat(
    tenant: uuid.UUID, ghid: None, model: Model, judecator: JudecatorFals
) -> None:
    judecator.raspunde("Ești un redactor atent la tonul unui brand", rubrica(raspuns("ton_potrivit", True)))
    r = ruleaza_doar(tenant, IN_TON, "G4", judecatori=True, model_autor=judecator.cod_autor)
    assert judecator.cereri == [] and r.stare is Stare.VALIDAT, (
        "ton apropiat: nu se consumă cotă de judecător"
    )


def test_rubrica_confirma_tonul_gresit_cu_fragment_literal_si_textul_e_respins(
    tenant: uuid.UUID, ghid: None, model: Model, judecator: JudecatorFals
) -> None:
    judecator.raspunde(
        "Ești un redactor atent la tonul unui brand",
        rubrica(raspuns("ton_potrivit", False, "indicatori financiari stabili pentru exercițiul curent")),
    )
    r = ruleaza_doar(tenant, IN_AFARA_TONULUI, "G4", judecatori=True, model_autor=judecator.cod_autor)
    assert r.stare is Stare.IN_REPARATIE
    [v3] = g(r, "G4", "V3")
    assert (
        v3.blocheaza and v3.dovezi[0].regula == "G4.ton_potrivit" and "ghidului de brand" in v3.instructiune
    )
    [prompt] = judecator.prompturi()
    assert (
        "Barista prietenos" in prompt
        and "Exemple aprobate" in prompt
        and "<<<DATE_EXTERNE sursa=livrabil" in prompt
    )
    assert [v.treapta.value for v in g(r, "G4")] == ["V1", "V2", "V3"]


def test_rubrica_care_nu_confirma_lasa_doar_avertismentul_de_similaritate(
    tenant: uuid.UUID, ghid: None, model: Model, judecator: JudecatorFals
) -> None:
    judecator.raspunde("Ești un redactor atent la tonul unui brand", rubrica(raspuns("ton_potrivit", True)))
    r = ruleaza_doar(tenant, IN_AFARA_TONULUI, "G4", judecatori=True, model_autor=judecator.cod_autor)
    assert r.stare is Stare.VALIDAT
    assert [v.rezultat.value for v in g(r, "G4")] == ["trece", "avertisment", "trece"]


# --- G8 --------------------------------------------------------------------------------------------------------------------------


def test_un_text_cu_doua_apeluri_la_actiune_este_respins(tenant: uuid.UUID) -> None:
    r = ruleaza_doar(
        tenant,
        "Cafeaua proaspătă ajunge la tine în două zile. Comandă acum pe site și urmărește-ne pe Instagram.",
        "G8",
    )
    assert r.stare is Stare.IN_REPARATIE
    [v] = g(r, "G8")
    assert (
        v.blocheaza
        and v.dovezi[0].regula == "G8.apeluri_multiple"
        and "un singur apel" in v.instructiune.lower()
    )
    assert v.detalii["ila"] > 0


def test_un_text_cu_un_singur_apel_trece(tenant: uuid.UUID) -> None:
    r = ruleaza_doar(
        tenant,
        "Cafeaua proaspătă ajunge la tine în două zile. Comandă acum pe site și o primești marți.",
        "G8",
    )
    assert r.stare is Stare.VALIDAT and g(r, "G8")[0].rezultat.value == "trece"


def test_apelul_din_campul_cta_se_numara_cu_cel_din_text(tenant: uuid.UUID) -> None:
    r = ruleaza_doar(
        tenant, "Cafeaua proaspătă ajunge la tine în două zile. Comandă acum!", "G8", tip="script_video_scurt",
        campuri={"cta": "Urmărește-ne pe Instagram", "hook": "Cafea proaspătă în două zile?", "batai": ["a", "b", "c"]},
    )  # fmt: skip
    assert r.stare is Stare.IN_REPARATIE and g(r, "G8")[0].dovezi[0].regula == "G8.apeluri_multiple"


def test_textul_greu_de_citit_este_semnalat(tenant: uuid.UUID) -> None:
    greu = (
        "Implementarea corespunzătoare a procedurilor de optimizare a experienței consumatorilor determină îmbunătățirea "
        "semnificativă a percepției generale asupra produselor comercializate de către organizația noastră, potrivit "
        "evaluărilor interdisciplinare realizate recent la nivel național și european, conform raportărilor anterioare. Comandă acum."
    )
    r = ruleaza_doar(tenant, greu, "G8")
    [v] = g(r, "G8")
    assert v.rezultat.value == "avertisment"
    assert {"G8.fraza_prea_lunga", "G8.text_greu_de_citit"} <= {d.regula for d in v.dovezi}
    assert v.detalii["ila"] < 40


def test_hook_slab_se_semnaleaza_iar_rubrica_ruleaza_doar_atunci(
    tenant: uuid.UUID, judecator: JudecatorFals
) -> None:
    judecator.raspunde(
        "Ești un redactor de marketing din România",
        rubrica(
            raspuns("hook_clar", False, "Salut dragi prieteni!", "salut fără conținut"),
            raspuns("un_singur_mesaj", True),
        ),
    )
    bun = ruleaza_doar(
        tenant,
        "De ce are cafeaua noastră aromă de ciocolată? O prăjim lent. Comandă acum.",
        "G8",
        judecatori=True,
        model_autor=judecator.cod_autor,
    )
    assert bun.stare is Stare.VALIDAT and judecator.cereri == [], "hook bun: rubrica nu se cheamă"
    slab = ruleaza_doar(
        tenant,
        "Salut dragi prieteni! Avem cafea nouă în meniu. Comandă acum.",
        "G8",
        judecatori=True,
        model_autor=judecator.cod_autor,
    )
    assert slab.stare is Stare.IN_REPARATIE and len(judecator.cereri) == 1
    assert [v.treapta.value for v in g(slab, "G8")] == ["V1", "V3"]
    assert g(slab, "G8", "V1")[0].rezultat.value == "avertisment" and g(slab, "G8", "V3")[0].blocheaza
    assert g(slab, "G8", "V3")[0].detalii["prompt"] == "validare.g8_conversie@1"
