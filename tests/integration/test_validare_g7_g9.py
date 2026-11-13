"""F5.6 — G7 Originalitate și G9 Juridic, cu Postgres real. „Gata când”: un text copiat dintr-o sursă este blocat și o reducere fără
preț de referință este semnalată. Momentele sunt FIXE (LA), vectorii SIMULAȚI (sac de cuvinte), judecătorul V4 un model FALS."""

# ruff: noqa: F811
import datetime as dt
import uuid
from typing import Any

import pytest

from app import validare
from app.creier import oferte
from app.creier.compartimente import SursaTip
from app.creier.versiuni import Sursa
from app.db import sesiune_tenant
from app.productie import Stare
from tests.gateway_utile import cheie_proba, fabrica_modele, fals  # noqa: F401
from tests.integration.test_creier_cautare import Model, _mediu, indexeaza, model  # noqa: F401
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.validare_utile import (  # noqa: F401
    LA,
    JudecatorFals,
    judecator,
    livrabil_in_validare,
    oferta_aprobata,
    raspuns,
    registru_doar,
    rubrica,
    ruleaza,
    sursa_cu_pasaje,
)

pytestmark = pytest.mark.db

SURSA_CONCURENTA = (
    "Prăjitoria Nordului prepară cafea de specialitate în loturi foarte mici, direct din boabe verzi aduse din Etiopia, "
    "apoi o ambalează manual și o trimite în toată țara în cel mult patru zile de la comandă."
)


def g(rez: validare.RezultatRunda, cod: str, treapta: str | None = None) -> list[validare.Verdict]:
    return [v for v in rez.verdicte if v.validator == cod and (treapta is None or v.treapta.value == treapta)]


def ruleaza_doar(tenant: uuid.UUID, text_: str, cod: str, **kw: Any) -> validare.RezultatRunda:
    jud, v4 = bool(kw.pop("judecatori", False)), bool(kw.pop("v4", False))
    with registru_doar(cod):
        lid = livrabil_in_validare(tenant, text_, **kw)
        return ruleaza(tenant, lid, la=LA, judecatori=jud, v4=v4)


# --- G7 --------------------------------------------------------------------------------------------------------------------------


def test_un_text_copiat_din_sursa_concurentei_este_blocat_cu_fragmentul_suprapus(tenant: uuid.UUID) -> None:
    sursa_cu_pasaje(tenant, [SURSA_CONCURENTA], statut="site_concurenta", nume="Prăjitoria Nordului")
    copie = "Vino la noi! " + SURSA_CONCURENTA + " Te așteptăm."
    r = ruleaza_doar(tenant, copie, "G7")
    assert r.stare is Stare.IN_REPARATIE
    [v] = g(r, "G7", "V1")
    d = v.dovezi[0]
    assert d.regula == "G7.copiat_din_sursa" and d.fragment.startswith("Prăjitoria Nordului prepară cafea")
    assert "Prăjitoria Nordului" in v.instructiune and v.detalii["documente_comparate"] == 1


def test_un_text_original_trece(tenant: uuid.UUID) -> None:
    sursa_cu_pasaje(tenant, [SURSA_CONCURENTA], statut="site_concurenta")
    r = ruleaza_doar(
        tenant,
        "Sâmbătă la 11:00 facem degustare la cafenea, vino să guști cafea proaspăt prăjită și să afli cum se prepară acasă.",
        "G7",
    )
    assert r.stare is Stare.VALIDAT and g(r, "G7", "V1")[0].rezultat.value == "trece"


def test_materialele_clientului_doar_avertizeaza_si_doar_la_copie_aproape_integrala(
    tenant: uuid.UUID,
) -> None:
    sursa_cu_pasaje(tenant, [SURSA_CONCURENTA], statut="material_client", nume="Site-ul clientului")
    partial = (
        "Pe site-ul nostru scrie: "
        + SURSA_CONCURENTA[:90]
        + ". Dar noi mai adăugăm multe lucruri despre cafeneaua și echipa noastră."
    )
    assert ruleaza_doar(tenant, partial, "G7").stare is Stare.VALIDAT
    r = ruleaza_doar(tenant, SURSA_CONCURENTA, "G7")
    [v] = g(r, "G7", "V1")
    assert v.rezultat.value == "avertisment" and v.dovezi[0].regula == "G7.copie_a_materialelor_clientului"
    assert r.stare is Stare.VALIDAT


def test_sursele_altui_client_nu_se_compara(tenant: uuid.UUID, fabrica_clienti) -> None:  # type: ignore[no-untyped-def]
    sursa_cu_pasaje(fabrica_clienti(), [SURSA_CONCURENTA], statut="site_concurenta")
    assert ruleaza_doar(tenant, SURSA_CONCURENTA, "G7").stare is Stare.VALIDAT


def test_activul_fara_licenta_blocheaza_iar_cu_licenta_trece(tenant: uuid.UUID) -> None:
    text_ = "Sâmbătă la 11:00 facem degustare la cafenea, vino să guști cafea proaspăt prăjită."
    r = ruleaza_doar(
        tenant,
        text_,
        "G7",
        active=[{"nume": "poza-cafenea.jpg", "licenta": "CC BY 4.0"}, {"nume": "logo-vechi.png"}],
    )
    assert r.stare is Stare.IN_REPARATIE and g(r, "G7", "V1")[0].dovezi[0].fragment == "logo-vechi.png"
    ok = ruleaza_doar(tenant, text_, "G7", active=[{"nume": "poza-cafenea.jpg", "licenta": "CC BY 4.0"}])
    assert ok.stare is Stare.VALIDAT


def test_parafraza_apropiata_de_o_sursa_nereutilizabila_este_semnalata_prin_vectori(
    tenant: uuid.UUID, model: Model
) -> None:
    sid, _ = sursa_cu_pasaje(tenant, [SURSA_CONCURENTA], statut="site_concurenta")
    indexeaza(tenant, sid)
    cuvinte = SURSA_CONCURENTA.split()
    amestecat = " ".join(
        cuvinte[0::3] + cuvinte[1::3] + cuvinte[2::3]
    )  # aceleași cuvinte, fără rânduri copiate
    r = ruleaza_doar(tenant, amestecat, "G7")
    [v1] = g(r, "G7", "V1")
    assert v1.rezultat.value == "trece", "nicio suprapunere de shingle-uri: nu e copie literală"
    [v2] = g(r, "G7", "V2")
    assert v2.rezultat.value == "avertisment" and v2.dovezi[0].regula == "G7.parafraza_apropiata"
    assert v2.detalii["scor_maxim"] >= v2.detalii["prag"]


def test_vectori_indisponibili_dau_necalculat_nu_blocare(tenant: uuid.UUID, model: Model) -> None:
    sid, _ = sursa_cu_pasaje(tenant, [SURSA_CONCURENTA], statut="site_concurenta")
    indexeaza(tenant, sid)
    model.opreste()
    r = ruleaza_doar(
        tenant,
        "Cafea de specialitate din Etiopia, în loturi mici, trimisă în toată țara în patru zile.",
        "G7",
    )
    assert r.stare is Stare.VALIDAT


# --- G9 --------------------------------------------------------------------------------------------------------------------------

PACHET = "Pachet Etiopia Guji 250 g"
TEXT_REDUCERE = f"{PACHET}: reducere 30%, 49 lei în loc de 70 lei."


def noua_versiune(
    tenant: uuid.UUID, om: uuid.UUID, intrare_id: uuid.UUID, pret: str, ref: str | None, la: dt.datetime
) -> None:
    continut: dict[str, Any] = {"tip": "produs", "nume": PACHET, "pret": {"numar": pret, "moneda": "RON"}}
    if ref:
        continut["pret_referinta"] = {"numar": ref, "moneda": "RON"}
    with sesiune_tenant(tenant, om) as db:
        v = oferte.modifica_oferta(
            db,
            intrare_id,
            continut=continut,
            sursa=Sursa(SursaTip.DECLARATIE_CLIENT),
            utilizator_id=om,
            acum=la,
        )
        oferte.aproba_oferta(db, intrare_id, v.nr, utilizator_id=om, acum=la)


def zile(n: int) -> dt.datetime:
    return LA - dt.timedelta(days=n)


def oferta_cu_istoric(
    tenant: uuid.UUID, om: uuid.UUID, trepte: list[tuple[str, int]], ref: str | None
) -> None:
    """`trepte`: (preț, acum câte zile a intrat în vigoare); ultima treaptă primește prețul de referință."""
    primul, pas = trepte[0], trepte[1:]
    iid = oferta_aprobata(
        tenant,
        om,
        PACHET,
        primul[0],
        aprobat_la=zile(primul[1]),
        **({"pret_referinta": ref} if ref and not pas else {}),
    )
    for i, (pret, inainte) in enumerate(pas):
        noua_versiune(tenant, om, iid, pret, ref if i == len(pas) - 1 else None, zile(inainte))


def test_reducere_cu_pret_de_referinta_egal_cu_minimul_din_30_de_zile_trece(
    tenant: uuid.UUID, om: uuid.UUID
) -> None:
    oferta_cu_istoric(tenant, om, [("70", 60), ("49", 1)], ref="70")
    r = ruleaza_doar(tenant, TEXT_REDUCERE, "G9")
    assert r.stare is Stare.VALIDAT and g(r, "G9")[0].rezultat.value == "trece"


def test_pretul_de_referinta_mai_mare_decat_minimul_recent_este_blocat(
    tenant: uuid.UUID, om: uuid.UUID
) -> None:
    oferta_cu_istoric(tenant, om, [("70", 60), ("60", 20), ("49", 1)], ref="70")
    r = ruleaza_doar(tenant, TEXT_REDUCERE, "G9")
    assert r.stare is Stare.IN_REPARATIE
    d = g(r, "G9")[0].dovezi[0]
    assert (
        d.regula == "G9.pret_de_referinta_gresit"
        and "60" in g(r, "G9")[0].instructiune
        and d.fragment == "30%"
    )


def test_reducere_fara_istoric_de_preturi_este_semnalata_explicit(tenant: uuid.UUID, om: uuid.UUID) -> None:
    oferta_cu_istoric(tenant, om, [("49", 1)], ref="70")
    r = ruleaza_doar(tenant, TEXT_REDUCERE, "G9")
    [v] = g(r, "G9")
    assert v.rezultat.value == "avertisment" and v.dovezi[0].regula == "G9.istoric_preturi_lipsa"
    assert "nu există istoric de prețuri" in v.instructiune


def test_istoric_mai_scurt_de_30_de_zile_este_avertisment_minor(tenant: uuid.UUID, om: uuid.UUID) -> None:
    oferta_cu_istoric(tenant, om, [("70", 10), ("49", 1)], ref="70")
    [v] = g(ruleaza_doar(tenant, TEXT_REDUCERE, "G9"), "G9")
    assert v.rezultat.value == "avertisment" and v.dovezi[0].regula == "G9.istoric_preturi_partial"


def test_reducere_la_o_oferta_fara_pret_de_referinta_este_blocata(tenant: uuid.UUID, om: uuid.UUID) -> None:
    oferta_aprobata(tenant, om, PACHET, "49", aprobat_la=zile(60))
    r = ruleaza_doar(tenant, f"{PACHET}: reducere 30%, 49 lei în loc de 70 lei.", "G9")
    assert (
        r.stare is Stare.IN_REPARATIE
        and g(r, "G9")[0].dovezi[0].regula == "G9.reducere_fara_pret_de_referinta"
    )


def test_reducere_fara_nicio_oferta_in_catalog_si_fara_pret_anterior_este_blocata(tenant: uuid.UUID) -> None:
    r = ruleaza_doar(tenant, "Reducere 30% la toate cafelele din magazin.", "G9")
    assert r.stare is Stare.IN_REPARATIE
    reguli = {d.regula for d in g(r, "G9")[0].dovezi}
    assert reguli == {"G9.reducere_fara_oferta", "G9.juridic.jur-reducere-pret-anterior"}


def test_promisiunea_de_rezultat_blocheaza(tenant: uuid.UUID) -> None:
    r = ruleaza_doar(tenant, "Rezultate garantate în prima lună, sau o schimbăm.", "G9")
    assert r.stare is Stare.IN_REPARATIE and g(r, "G9")[0].dovezi[0].regula == "G9.promisiune_de_rezultat"


def test_mentiunea_obligatorie_lipsa_si_prezenta(tenant: uuid.UUID) -> None:
    fara = ruleaza_doar(tenant, "Participă la concursul nostru și câștigă un pachet de cafea.", "G9")
    assert fara.stare is Stare.IN_REPARATIE and "regulament" in fara.instructiune
    cu = ruleaza_doar(
        tenant, "Participă la concursul nostru; regulamentul complet: https://zorilor.ro/regulament.", "G9"
    )
    assert cu.stare is Stare.VALIDAT
    assert g(cu, "G9")[0].detalii["pachete"][0]["pachet"] == "juridic"


def test_pachetul_juridic_nu_se_aplica_de_g3(tenant: uuid.UUID) -> None:
    with registru_doar("G3"):
        lid = livrabil_in_validare(tenant, "Participă la concursul nostru și câștigă un pachet de cafea.")
        r = ruleaza(tenant, lid, la=LA)
    assert "juridic" not in {p["pachet"] for p in g(r, "G3")[0].detalii["pachete"]}


def test_judecatorul_puternic_ruleaza_doar_cu_v4_activ_si_dupa_ce_v1_a_trecut(
    tenant: uuid.UUID, judecator: JudecatorFals
) -> None:
    fraza = "Ești un verificator juridic pentru texte de marketing"
    judecator.raspunde(
        fraza,
        rubrica(
            raspuns("fara_promisiune_de_rezultat", True),
            raspuns("fara_urgenta_falsa", False, "Ultimele 2 bucăți, grăbește-te", "stoc inventat"),
            raspuns("fara_recenzii_false", True),
        ),
    )
    text_ = "Cafea proaspătă prăjită azi. Ultimele 2 bucăți, grăbește-te!"
    fara_v4 = ruleaza_doar(tenant, text_, "G9", model_autor=judecator.cod_autor)
    assert fara_v4.stare is Stare.VALIDAT and judecator.cereri == []
    r = ruleaza_doar(tenant, text_, "G9", model_autor=judecator.cod_autor, v4=True)
    [v4] = g(r, "G9", "V4")
    assert r.stare is Stare.IN_REPARATIE and v4.blocheaza and v4.dovezi[0].regula == "G9.fara_urgenta_falsa"
    assert v4.detalii["prompt"] == "validare.g9_juridic@1" and v4.detalii["model"] == judecator.cod
    judecator.cereri.clear()
    esec_v1 = ruleaza_doar(
        tenant, "Rezultate garantate. " + text_, "G9", model_autor=judecator.cod_autor, v4=True
    )
    assert esec_v1.stare is Stare.IN_REPARATIE and judecator.cereri == [], "V1 a blocat: V4 nu consumă cotă"
