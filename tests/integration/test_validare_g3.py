"""F5.4 — G3 Politici și regulile pe client, cu Postgres real. „Gata când”: fiecare regulă are un exemplu blocat și unul care trece
(testul rulează exemplele în `tests/unit/test_reguli.py`); aici G3 aplică pachetele potrivite livrabilului (platformă + nișă + client)."""

# ruff: noqa: F811
import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app import validare
from app.db import sesiune_tenant
from app.productie import Stare
from app.validare import reguli, reguli_client
from tests.gateway_utile import cheie_proba, fabrica_modele, fals  # noqa: F401
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


def g3(rez: validare.RezultatRunda) -> list[validare.Verdict]:
    return [v for v in rez.verdicte if v.validator == "G3"]


def ruleaza_g3(tenant: uuid.UUID, text_: str, **kw: object) -> validare.RezultatRunda:
    with registru_doar("G3"):
        lid = livrabil_in_validare(tenant, text_, **kw)  # type: ignore[arg-type]
        return ruleaza(tenant, lid, la=LA)


def test_un_text_curat_trece_si_verdictul_spune_ce_pachete_au_judecat(tenant: uuid.UUID) -> None:
    r = ruleaza_g3(
        tenant, "Sâmbătă la 11:00 facem degustare la cafenea. Vino să guști cafeaua proaspăt prăjită."
    )
    assert r.stare is Stare.VALIDAT
    [v] = g3(r)
    assert v.rezultat.value == "trece"
    pachete = {p["pachet"]: p for p in v.detalii["pachete"]}
    assert set(pachete) == {"general", "meta", "jocuri-de-noroc", "adulti", "politica", "finante"}
    incarcate = {p.nume: p for p in reguli.incarca()}
    assert all(
        pachete[n]["versiune"] == incarcate[n].pachet.versiune
        and pachete[n]["amprenta"] == incarcate[n].amprenta
        for n in pachete
    ), "verdictul păstrează versiunea și amprenta fișierelor de reguli care au judecat"
    assert v.detalii["reguli_neverificate"] > 0 and v.detalii["reguli_client"] == []


def test_o_promisiune_medicala_este_blocata_cu_regula_fragmentul_si_sursa(tenant: uuid.UUID) -> None:
    r = ruleaza_g3(tenant, "Cafeaua noastră vindecă anxietatea în câteva zile.")
    assert r.stare is Stare.IN_REPARATIE
    [v] = g3(r)
    d = v.dovezi[0]
    assert d.regula == "G3.general.gen-promisiune-medicala" and d.fragment == "vindecă"
    assert "[I]" in d.detalii and "Legea" in d.detalii
    assert "promisiunile medicale" in v.instructiune


def test_regulile_platformei_se_aplica_doar_pe_canalul_ei(tenant: uuid.UUID) -> None:
    text_ = "Slăbește rapid cu ceaiul nostru detox."
    assert ruleaza_g3(tenant, text_, canal="facebook").stare is Stare.VALIDAT
    r = ruleaza_g3(tenant, text_, canal="tiktok")
    assert r.stare is Stare.IN_REPARATIE and {d.regula for d in g3(r)[0].dovezi} == {
        "G3.tiktok.tt-slabit-detox"
    }


def test_momeala_de_interactiune_pe_facebook(tenant: uuid.UUID) -> None:
    r = ruleaza_g3(
        tenant, "Dă like dacă iubești cafeaua și etichetează doi prieteni ca să câștigi!", canal="instagram"
    )
    assert r.stare is Stare.IN_REPARATIE
    assert {d.regula for d in g3(r)[0].dovezi} == {"G3.meta.meta-engagement-bait"}


def test_o_nisa_refuzata_intra_in_carantina_nu_in_reparatie(tenant: uuid.UUID) -> None:
    r = ruleaza_g3(tenant, "Joacă la cazino online și câștigă mare.")
    assert r.decizie is validare.Decizie.CARANTINA and r.stare is Stare.CARANTINA
    assert g3(r)[0].severitate is validare.Severitate.CRITICA


def test_avertismentele_nu_blocheaza(tenant: uuid.UUID) -> None:
    r = ruleaza_g3(tenant, "OFERTA ZILEI LA TOATE CAFELELE DIN MAGAZIN ACUM, vino repede.")
    assert r.stare is Stare.VALIDAT
    [v] = g3(r)
    assert v.rezultat.value == "avertisment" and v.severitate is validare.Severitate.MINORA


def test_emailul_fara_dezabonare_este_blocat_cu_dezabonare_trece(tenant: uuid.UUID) -> None:
    fara = ruleaza_g3(
        tenant, "Salut! Pachetul tău pleacă marți, proaspăt prăjit.", canal="email", tip="email"
    )
    assert fara.stare is Stare.IN_REPARATIE
    assert g3(fara)[0].dovezi[0].regula == "G3.email.email-dezabonare-obligatorie"
    assert "dezabonare" in fara.instructiune
    cu = ruleaza_g3(
        tenant,
        "Primești acest email deoarece te-ai abonat. Pachetul tău pleacă marți.",
        canal="email",
        tip="email",
        campuri={"link_dezabonare": "https://zorilor.ro/dezabonare"},
    )
    assert cu.stare is Stare.VALIDAT


def test_continutul_sponsorizat_trebuie_marcat(tenant: uuid.UUID) -> None:
    r = ruleaza_g3(tenant, "Noul nostru amestec e de neratat.", campuri={"sponsorizat": True})
    assert r.stare is Stare.IN_REPARATIE and g3(r)[0].dovezi[0].regula == "G3.general.gen-sponsorizat-marcat"
    ok = ruleaza_g3(
        tenant, "Parteneriat plătit: noul nostru amestec e de neratat.", campuri={"sponsorizat": True}
    )
    assert ok.stare is Stare.VALIDAT


# --- nișa clientului -----------------------------------------------------------------------------------------------------------

SUPLIMENT = "Suplimentul nostru cu magneziu te ajută în fiecare zi."


def test_nisa_declarata_de_livrabil_aduce_regulile_ei(tenant: uuid.UUID) -> None:
    assert ruleaza_g3(tenant, SUPLIMENT).stare is Stare.VALIDAT, (
        "fără nișa «sănătate» declarată, regula nu se aplică"
    )
    r = ruleaza_g3(tenant, SUPLIMENT, campuri={"nise": ["sanatate"]})
    assert r.stare is Stare.IN_REPARATIE and g3(r)[0].dovezi[0].regula == "G3.sanatate.san-supliment-mentiune"
    assert "sanatate" in g3(r)[0].detalii["nise"]


def test_nisa_din_profilul_de_brand_aprobat_se_aplica_la_toate_livrabilele(
    tenant: uuid.UUID, om: uuid.UUID
) -> None:
    profil_aprobat(tenant, om, {"pozitionare": "Magazin de suplimente", "nise": ["sanatate"]})
    r = ruleaza_g3(tenant, SUPLIMENT)
    assert r.stare is Stare.IN_REPARATIE and g3(r)[0].detalii["nise"] == ["sanatate"]
    ok = ruleaza_g3(
        tenant, SUPLIMENT + " Suplimentele alimentare nu înlocuiesc o dietă variată și echilibrată."
    )
    assert ok.stare is Stare.VALIDAT


# --- regulile pe client ------------------------------------------------------------------------------------------------------------


def regula_client(**kw: object) -> dict[str, object]:
    baza: dict[str, object] = {
        "id": "zorilor-fara-ieftin",
        "text": "Brandul Cafeneaua Zorilor nu folosește cuvântul «ieftin».",
        "potrivire": "cuvant",
        "tipare": ["ieftin", "ieftină"],
        "severitate": "majora",
        "marcaj": "[I]",
        "verificat_la": "2026-11-13",
        "sursa": {
            "tip": "lege",
            "titlu": "Ghidul de brand al clientului",
            "url": "https://zorilor.exemplu.test/ghid",
        },
        "exemple_blocate": ["Cea mai ieftină cafea din oraș."],
        "exemple_trece": ["Cafea bună la un preț corect."],
    }
    return {**baza, **kw}


def test_o_regula_a_clientului_se_aplica_doar_clientului_ei(
    tenant: uuid.UUID, om: uuid.UUID, fabrica_clienti
) -> None:  # type: ignore[no-untyped-def]
    altul = fabrica_clienti()
    with sesiune_tenant(tenant, om) as db:
        r1 = reguli_client.adauga(
            db, tenant_id=tenant, definitie=regula_client(), utilizator_id=om, motiv="din ghid"
        )
        assert r1.versiune == 1
    text_ = "Cafea ieftină pentru toți."
    r = ruleaza_g3(tenant, text_)
    assert r.stare is Stare.IN_REPARATIE
    d = g3(r)[0].dovezi[0]
    assert d.regula == "G3.client.zorilor-fara-ieftin" and d.fragment == "ieftină"
    assert g3(r)[0].detalii["reguli_client"] == [{"regula": "zorilor-fara-ieftin", "versiune": 1}]
    assert ruleaza_g3(altul, text_).stare is Stare.VALIDAT, "regula unui client nu se aplică altuia"


def test_regula_clientului_cere_exemple_corecte_si_schema_la_fel_de_stricta(
    tenant: uuid.UUID, om: uuid.UUID
) -> None:
    with sesiune_tenant(tenant, om) as db:
        with pytest.raises(reguli_client.RegulaClientInvalida, match="nu a fost blocat"):
            reguli_client.adauga(
                db, tenant_id=tenant, utilizator_id=om,
                definitie=regula_client(exemple_blocate=["Cafea bună, fără probleme."]),
            )  # fmt: skip
        with pytest.raises(reguli_client.RegulaClientInvalida):
            reguli_client.adauga(
                db, tenant_id=tenant, utilizator_id=om, definitie=regula_client(exemple_trece=[])
            )
        with pytest.raises(reguli_client.RegulaClientInvalida, match="conflict"):
            reguli_client.adauga(
                db, tenant_id=tenant, utilizator_id=om, definitie=regula_client(id="gen-venit-nerealist")
            )
        assert reguli_client.active(db, tenant) == []


def test_regula_clientului_se_versioneaza_si_se_retrage_fara_sa_se_piarda_istoricul(
    tenant: uuid.UUID, om: uuid.UUID
) -> None:
    with sesiune_tenant(tenant, om) as db:
        reguli_client.adauga(db, tenant_id=tenant, definitie=regula_client(), utilizator_id=om)
        v2 = reguli_client.adauga(
            db, tenant_id=tenant, utilizator_id=om,
            definitie=regula_client(tipare=["ieftin", "ieftină", "ieftine"], exemple_blocate=["Prețuri ieftine!"]),
        )  # fmt: skip
        assert v2.versiune == 2
        assert [(r.id, v) for r, v in reguli_client.active(db, tenant)] == [("zorilor-fara-ieftin", 2)]
        with pytest.raises(ValueError, match="motiv"):
            reguli_client.retrage(
                db, tenant_id=tenant, regula_id="zorilor-fara-ieftin", utilizator_id=om, motiv=" "
            )
        reguli_client.retrage(
            db, tenant_id=tenant, regula_id="zorilor-fara-ieftin", utilizator_id=om, motiv="nu mai e cerută"
        )
        assert reguli_client.active(db, tenant) == []
        assert [(r.versiune, r.retrasa) for r in reguli_client.istoric(db, tenant, "zorilor-fara-ieftin")] == [
            (1, False), (2, False), (3, True)
        ]  # fmt: skip
    assert ruleaza_g3(tenant, "Cafea ieftină pentru toți.").stare is Stare.VALIDAT


def test_regulile_clientului_nu_se_scriu_fara_un_om_si_nu_se_modifica(
    tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    with sesiune_tenant(tenant, om) as db:
        reguli_client.adauga(db, tenant_id=tenant, definitie=regula_client(), utilizator_id=om)
    with pytest.raises(DBAPIError), sesiune_tenant(tenant) as db:
        db.execute(
            text(
                "INSERT INTO reguli_client (id, tenant_id, regula_id, versiune, definitie, creat_de) "
                "VALUES (gen_random_uuid(), :t, 'regula-fara-om', 1, '{}'::jsonb, NULL)"
            ),
            {"t": tenant},
        )
    for sql in ("UPDATE reguli_client SET retrasa = true", "DELETE FROM reguli_client"):
        with pytest.raises(DBAPIError), sesiune_tenant(tenant) as db:
            db.execute(text(sql))
    with admin_engine.connect() as c:
        actiuni = {
            r[0]
            for r in c.execute(text("SELECT actiune FROM jurnal_audit WHERE tenant_id = :t"), {"t": tenant})
        }
    assert "validare.regula_client_adaugata" in actiuni


# --- V3: promisiuni formulate liber ------------------------------------------------------------------------------------------------

FRAZA = "Ești un verificator de conformitate pentru texte de marketing"


def test_judecatorul_de_politici_prinde_o_promisiune_formulata_liber(
    tenant: uuid.UUID, judecator: JudecatorFals
) -> None:
    text_ = "După o lună cu ceaiul nostru, durerile de spate dispar pentru totdeauna."
    judecator.raspunde(
        FRAZA,
        rubrica(
            raspuns("fara_promisiuni_medicale", False, "durerile de spate dispar pentru totdeauna"),
            raspuns("fara_castig_garantat", True),
            raspuns("fara_atribute_personale", True),
            raspuns("fara_minori", True),
        ),
    )
    with registru_doar("G3"):
        lid = livrabil_in_validare(tenant, text_, model_autor=judecator.cod_autor)
        assert ruleaza(tenant, lid, la=LA).stare is Stare.VALIDAT, "tiparele nu o prind: fără judecător trece"
    with registru_doar("G3"):
        lid = livrabil_in_validare(tenant, text_, model_autor=judecator.cod_autor)
        r = ruleaza(tenant, lid, la=LA, judecatori=True)
    assert r.stare is Stare.IN_REPARATIE
    [v3] = [v for v in g3(r) if v.treapta.value == "V3"]
    assert v3.dovezi[0].regula == "G3.fara_promisiuni_medicale" and "promisiunea medicală" in v3.instructiune
    assert v3.detalii["prompt"] == "validare.g3_politici@1" and v3.cost.apeluri_llm == 1
