"""F5.3 — G2 Verificatorul de fapte, cu Postgres real. „Gata când”: un text cu un preț greșit și unul cu o
afirmație
neacoperită sunt blocate (și un text corect trece). Faptele se aprobă la T_APROB și se validează la LA
(fixe, nu ceasul real).
Judecătorul V3 este un model FALS (# SIMULAT)."""

# ruff: noqa: F811
import datetime as dt
import re
import uuid

import pytest

from app import productie, validare
from app.db import sesiune_tenant
from app.productie import Stare
from tests.gateway_utile import cheie_proba, fabrica_modele, fals  # noqa: F401
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.validare_utile import (  # noqa: F401
    LA,
    JudecatorFals,
    fapt_aprobat,
    judecator,
    livrabil_in_validare,
    oferta_aprobata,
    raspuns,
    registru_doar,
    ruleaza,
    sursa_cu_pasaje,
    verdicte,
)

pytestmark = pytest.mark.db


@pytest.fixture
def registru_zorilor(tenant: uuid.UUID, om: uuid.UUID) -> dict[str, uuid.UUID]:
    """Faptele brandului fictiv „Cafeneaua Zorilor” (inventate), aprobate de un om."""
    return {
        "abonament": oferta_aprobata(
            tenant, om, "Abonament Lunar", "89", tip="abonament", descriere="Cafea proaspătă în fiecare lună"
        ),
        "pachet": oferta_aprobata(tenant, om, "Pachet Etiopia Guji 250 g", "49", pret_referinta="59"),
        "livrare": fapt_aprobat(
            tenant,
            om,
            "termen",
            "Livrare",
            "Livrăm în 2-3 zile lucrătoare în toată țara",
            valoare={"text": "2-3 zile"},
        ),
        "garantie": fapt_aprobat(
            tenant,
            om,
            "garantie",
            "Garanție",
            "Garanție: schimbăm cafeaua dacă nu ți-a plăcut, fără întrebări",
        ),
    }


def g2(rez: validare.RezultatRunda) -> list[validare.Verdict]:
    return [v for v in rez.verdicte if v.validator == "G2"]


def ruleaza_g2(tenant: uuid.UUID, text_: str, **kw: object) -> validare.RezultatRunda:
    with registru_doar("G2"):
        lid = livrabil_in_validare(tenant, text_, **kw)  # type: ignore[arg-type]
        return ruleaza(tenant, lid, la=LA)


def test_textul_corect_trece(tenant: uuid.UUID, registru_zorilor: dict[str, uuid.UUID]) -> None:
    r = ruleaza_g2(
        tenant,
        "Abonamentul Lunar costă 89 lei. Livrăm în 2-3 zile, iar dacă nu ți-a plăcut, ai garanție: schimbăm cafeaua. "
        "Pachetul Etiopia Guji 250 g: 49 lei în loc de 59 lei.",
    )
    assert r.stare is Stare.VALIDAT and [v.rezultat.value for v in g2(r)] == ["trece"]
    assert g2(r)[0].detalii["intrari_registru"] == 4


def test_un_pret_gresit_este_blocat_cu_ce_spune_registrul(
    tenant: uuid.UUID, registru_zorilor: dict[str, uuid.UUID]
) -> None:
    r = ruleaza_g2(tenant, "Abonamentul Lunar costă doar 59 lei pe lună.")
    assert r.stare is Stare.IN_REPARATIE
    [v] = g2(r)
    assert v.blocheaza and v.dovezi[0].regula == "G2.pret_diferit" and v.dovezi[0].fragment == "59 lei"
    assert "89" in v.instructiune and "registru" in v.instructiune
    assert "[G2]" in r.instructiune


def test_o_afirmatie_neacoperita_este_blocata(
    tenant: uuid.UUID, registru_zorilor: dict[str, uuid.UUID]
) -> None:
    r = ruleaza_g2(tenant, "Suntem cel mai bun prăjitor din țară și livrăm în 24 de ore, cu 40 de angajați.")
    assert r.stare is Stare.IN_REPARATIE
    reguli = {d.regula for d in g2(r)[0].dovezi}
    assert reguli == {"G2.neacoperita.superlativ", "G2.neacoperita.termen", "G2.neacoperita.cifra"}
    assert {d.fragment for d in g2(r)[0].dovezi} == {"cel mai bun", "24 de ore", "40"}


def test_faptele_expirate_sau_viitoare_nu_acopera(tenant: uuid.UUID, om: uuid.UUID) -> None:
    fapt_aprobat(
        tenant, om, "pret", "Etiopia Guji", "Etiopia Guji 250 g costă 39 lei",
        valoare={"numar": "39", "moneda": "RON"}, valabil_pana_la=LA - dt.timedelta(hours=1),
    )  # fmt: skip
    fapt_aprobat(
        tenant, om, "pret", "Etiopia Guji", "Etiopia Guji 250 g va costa 70 lei",
        valoare={"numar": "70", "moneda": "RON"}, valabil_de_la=LA + dt.timedelta(days=1),
    )  # fmt: skip
    fapt_aprobat(
        tenant,
        om,
        "pret",
        "Etiopia Guji",
        "Etiopia Guji 250 g costă 45 lei",
        valoare={"numar": "45", "moneda": "RON"},
    )
    r = ruleaza_g2(tenant, "Etiopia Guji 250 g costă 39 lei, mâine 70 lei, azi 45 lei.")
    fragmente = {d.fragment for d in g2(r)[0].dovezi}
    assert fragmente == {"39 lei", "70 lei"}, "la data publicării contează doar faptele valabile atunci"


def test_un_fapt_propus_dar_neaprobat_nu_acopera(tenant: uuid.UUID, om: uuid.UUID) -> None:
    from app.creier import fapte
    from app.creier.compartimente import SursaTip
    from app.creier.versiuni import Sursa

    with sesiune_tenant(tenant, om) as db:
        fapte.propune_fapt(
            db, tenant_id=tenant, utilizator_id=om, sursa=Sursa(SursaTip.DECLARATIE_CLIENT), acum=LA - dt.timedelta(days=1),
            continut={"tip": "pret", "subiect": "Espresso", "afirmatie": "Espresso costă 12 lei", "valoare": {"numar": "12", "moneda": "RON"}},
        )  # fmt: skip
    r = ruleaza_g2(tenant, "Un espresso costă 12 lei.")
    assert r.stare is Stare.IN_REPARATIE


def test_citatele_din_surse_acopera_doar_daca_apar_literal_in_pasaj(tenant: uuid.UUID) -> None:
    _, pasaje = sursa_cu_pasaje(
        tenant, ["Prăjim cafeaua în loturi de câte 5 kg, exclusiv la Brașov, în fiecare marți."]
    )
    p = pasaje[0]
    bun = {"surse_citate": [{"pasaj_id": str(p.id), "citat": "loturi de câte 5 kg"}]}
    r = ruleaza_g2(tenant, "Prăjim în loturi de câte 5 kg.", campuri=bun)
    assert r.stare is Stare.VALIDAT
    fals_ = {"surse_citate": [{"pasaj_id": str(p.id), "citat": "loturi de câte 50 kg, în fiecare zi"}]}
    r = ruleaza_g2(tenant, "Prăjim în loturi de câte 50 kg.", campuri=fals_)
    assert r.stare is Stare.IN_REPARATIE
    assert "G2.sursa_citata_falsa" in {d.regula for d in g2(r)[0].dovezi}


def test_citatul_unui_pasaj_al_altui_client_nu_acopera(tenant: uuid.UUID, fabrica_clienti) -> None:  # type: ignore[no-untyped-def]
    altul = fabrica_clienti()
    _, pasaje = sursa_cu_pasaje(altul, ["Prăjim cafeaua în loturi de câte 5 kg, exclusiv la Brașov."])
    camp = {"surse_citate": [{"pasaj_id": str(pasaje[0].id), "citat": "loturi de câte 5 kg"}]}
    r = ruleaza_g2(tenant, "Prăjim în loturi de câte 5 kg.", campuri=camp)
    assert r.stare is Stare.IN_REPARATIE, "pasajul altui client nu e vizibil (RLS), deci sursa e falsă"


# --- fapt lipsă → întrebare către client
# -------------------------------------------------------------------------------


def test_un_fapt_lipsa_opreste_livrabilul_cu_o_intrebare_vizibila_nu_cu_o_presupunere(
    tenant: uuid.UUID, om: uuid.UUID, registru_zorilor: dict[str, uuid.UUID]
) -> None:
    campuri = {"fapte_necesare": [{"tip": "pret", "subiect": "Abonament Birou"}], "intrebari_autor": []}
    with registru_doar("G2"):
        lid = livrabil_in_validare(
            tenant, "Abonamentul Birou costă 310 lei. Abonamentul Lunar costă 59 lei.", campuri=campuri
        )
        r = ruleaza(tenant, lid, la=LA)
    assert r.decizie is validare.Decizie.INTREBARE and r.stare is Stare.COADA_DE_ERORI
    with sesiune_tenant(tenant) as db:
        [q] = validare.intrebari.ale_livrabilului(db, lid)
        assert (
            q.stare == "deschisa"
            and q.tip_fapt == "pret"
            and q.subiect == "Abonament Birou"
            and q.validator == "G2"
        )
        assert "prețul" in q.intrebare and "Abonament Birou" in q.intrebare
        assert [x.id for x in validare.intrebari.deschise(db)] == [q.id]
        mutare = next(t for t in productie.istoric(db, lid) if t.in_stare == "coada_de_erori")
        assert mutare.detalii["intrebari"] == 1 and "întrebare către client" in mutare.motiv
        ultima = validare.ultima_rulare(db, lid)
        assert ultima is not None and ultima.decizie == "intrebare"
    # nimic nu s-a presupus: prețul de 310 lei nu a devenit fapt
    assert {v.rezultat for v in verdicte(tenant, lid)} == {"esec"}


def test_dupa_raspuns_faptul_se_adauga_in_creier_si_livrabilul_se_reia(
    tenant: uuid.UUID, om: uuid.UUID, registru_zorilor: dict[str, uuid.UUID]
) -> None:
    campuri = {"fapte_necesare": [{"tip": "pret", "subiect": "Abonament Birou"}]}
    with registru_doar("G2"):
        lid = livrabil_in_validare(tenant, "Abonamentul Birou costă 310 lei pe lună.", campuri=campuri)
        assert ruleaza(tenant, lid, la=LA).stare is Stare.COADA_DE_ERORI
        with sesiune_tenant(tenant, om) as db:
            [q] = validare.intrebari.ale_livrabilului(db, lid)
            validare.intrebari.raspunde(db, q.id, "310 lei pe lună, confirmat de client", utilizator_id=om)
            assert validare.intrebari.deschise(db) == []
            with pytest.raises(validare.intrebari.IntrebareInchisa):
                validare.intrebari.raspunde(db, q.id, "încă o dată", utilizator_id=om)
        # faptul îl aprobă un om în Creier (răspunsul nu devine fapt singur), apoi un om reia livrabilul
        oferta_aprobata(tenant, om, "Abonament Birou", "310", tip="abonament")
        with sesiune_tenant(tenant, om) as db:
            productie.reia_de_om(db, lid, utilizator_id=om, motiv="faptul a fost adăugat în registru")
        r = ruleaza(tenant, lid, la=LA)
    assert r.stare is Stare.VALIDAT and r.decizie is validare.Decizie.TRECE
    with sesiune_tenant(tenant) as db:
        assert [q.stare for q in validare.intrebari.ale_livrabilului(db, lid)] == ["raspunsa"]


def test_intrebarea_autorului_este_o_intrebare_deschisa(
    tenant: uuid.UUID, registru_zorilor: dict[str, uuid.UUID]
) -> None:
    campuri = {"intrebari_autor": ["Care este adresa cafenelei pentru postarea de weekend?"]}
    with registru_doar("G2"):
        lid = livrabil_in_validare(tenant, "Vino în weekend la cafenea.", campuri=campuri)
        r = ruleaza(tenant, lid, la=LA)
    assert r.stare is Stare.COADA_DE_ERORI
    with sesiune_tenant(tenant) as db:
        assert [q.intrebare for q in validare.intrebari.ale_livrabilului(db, lid)] == [
            "Care este adresa cafenelei pentru postarea de weekend?"
        ]


def test_un_fapt_necesar_existent_nu_opreste_livrabilul(
    tenant: uuid.UUID, registru_zorilor: dict[str, uuid.UUID]
) -> None:
    campuri = {
        "fapte_necesare": [
            {"tip": "pret", "subiect": "Abonament Lunar"},
            {"tip": "termen", "subiect": "Livrare"},
        ]
    }
    r = ruleaza_g2(tenant, "Abonamentul Lunar costă 89 lei, livrăm în 2-3 zile.", campuri=campuri)
    assert r.stare is Stare.VALIDAT


# --- V3: afirmații nestructurate
# ---------------------------------------------------------------------------------------------

FRAZA = "Ești un verificator de fapte pentru texte de marketing"


def test_judecatorul_aduce_afirmatii_nestructurate_si_acoperirea_se_verifica_in_registru(
    tenant: uuid.UUID, om: uuid.UUID, judecator: JudecatorFals
) -> None:
    fapt = fapt_aprobat(
        tenant,
        om,
        "caracteristica",
        "Origine",
        "Boabele vin exclusiv din Etiopia și Columbia; lucrăm cu fermierii de 10 ani",
    )
    judecator.raspunde(
        FRAZA,
        lambda c: json_afirmatii(
            {"fragment": "boabe exclusiv din Etiopia", "fapt_id": str(fapt)},
            {"fragment": "prăjite pe lemne de fag", "fapt_id": None},
            {"fragment": "o frază care nu e în text", "fapt_id": None},
            {"fragment": "de 10 ani", "fapt_id": None},
            {"fragment": "Colectăm boabele personal", "fapt_id": str(uuid.uuid4())},
        ),
    )
    text_ = (
        "Folosim boabe exclusiv din Etiopia, prăjite pe lemne de fag. Colectăm boabele personal, de 10 ani."
    )
    with registru_doar("G2"):
        lid = livrabil_in_validare(tenant, text_, model_autor=judecator.cod_autor)
        r = ruleaza(tenant, lid, la=LA, judecatori=True)
    [v3] = [v for v in g2(r) if v.treapta.value == "V3"]
    assert {d.fragment for d in v3.dovezi} == {"prăjite pe lemne de fag", "Colectăm boabele personal"}, (
        "acoperit: cel cu fapt real; ignorate: fragmentul inexistent și cel cu cifre"
    )
    assert v3.detalii["model_autor"] == judecator.cod_autor and v3.cost.apeluri_llm == 1
    [prompt] = judecator.prompturi()
    assert f"[{fapt}]" in prompt and "Boabele vin exclusiv din Etiopia" in prompt
    assert "<<<DATE_EXTERNE sursa=livrabil" in prompt


def json_afirmatii(*afirmatii: dict[str, object]) -> str:
    import json

    return json.dumps(
        {"afirmatii": list(afirmatii), "dovezi": ["scriptat"], "incredere": 0.9}, ensure_ascii=False
    )


def test_judecatorul_nu_ruleaza_dupa_un_esec_deterministic_nu_se_consuma_cota(
    tenant: uuid.UUID, registru_zorilor: dict[str, uuid.UUID], judecator: JudecatorFals
) -> None:
    judecator.raspunde(FRAZA, json_afirmatii())
    with registru_doar("G2"):
        lid = livrabil_in_validare(tenant, "Abonamentul Lunar costă 1 leu.", model_autor=judecator.cod_autor)
        r = ruleaza(tenant, lid, la=LA, judecatori=True)
    assert r.stare is Stare.IN_REPARATIE and judecator.cereri == []


def test_judecatorul_cu_registru_curat_si_fara_afirmatii_nu_blocheaza(
    tenant: uuid.UUID, judecator: JudecatorFals
) -> None:
    judecator.raspunde(FRAZA, json_afirmatii())
    with registru_doar("G2"):
        lid = livrabil_in_validare(tenant, "Vino să guști ceva bun.", model_autor=judecator.cod_autor)
        r = ruleaza(tenant, lid, la=LA, judecatori=True)
    assert r.stare is Stare.VALIDAT
    [prompt] = judecator.prompturi()
    assert "(registru gol)" in prompt


def test_identificatorii_din_prompt_sunt_cei_din_registru(
    tenant: uuid.UUID, om: uuid.UUID, judecator: JudecatorFals
) -> None:
    a = fapt_aprobat(tenant, om, "caracteristica", "Origine", "Boabele vin din Etiopia")
    judecator.raspunde(FRAZA, json_afirmatii())
    with registru_doar("G2"):
        lid = livrabil_in_validare(tenant, "Vino să guști ceva bun.", model_autor=judecator.cod_autor)
        ruleaza(tenant, lid, la=LA, judecatori=True)
    ids = re.findall(r"\[([0-9a-f-]{36})\]", judecator.prompturi()[0])
    assert ids == [str(a)]
