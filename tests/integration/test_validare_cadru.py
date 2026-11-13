"""F5.1 — cadrul de validare, cu Postgres real. „Gata când”: un validator de probă blochează și trimite autorului
instrucțiunea de corectare. Validatorii de probă sunt SIMULAȚI (`# SIMULAT`), autorul reparațiilor e scriptat."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app import productie, validare
from app.db import sesiune_tenant
from app.operare import coada_erori, motor
from app.productie import Stare
from app.validare import registru
from app.validare.autor import ContinutNou, SarcinaReparatie
from app.validare.registru import DefinitieValidator
from app.validare.verdict import Dovada, Severitate, Treapta, avertisment, esec, trece
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.validare_utile import autor_scriptat, livrabil_in_validare, registru_gol, ruleaza, verdicte  # noqa: F401

pytestmark = pytest.mark.db
INTERZIS = "INTERZIS"


@pytest.fixture
def probe(registru_gol: None) -> None:
    """# SIMULAT: doi validatori de probă. GP (V1) blochează textul care conține „INTERZIS” (reparabil), GC (V1) pe cel
    cu „CRITIC” (carantină), GA (V1) avertizează pentru fiecare „SLAB” din text."""

    def gp(i: validare.Intrare) -> validare.Verdict:
        if INTERZIS in i.text:
            return esec(
                "GP", "1", Treapta.V1,
                dovezi=[Dovada(INTERZIS, "cuvântul interzis nu are voie")],
                instructiune=f"Scoate cuvântul {INTERZIS} din text.",
            )  # fmt: skip
        return trece("GP", "1", Treapta.V1)

    def gc(i: validare.Intrare) -> validare.Verdict:
        if "CRITIC" in i.text:
            return esec(
                "GC", "1", Treapta.V1, dovezi=[Dovada("CRITIC", "cerere refuzată")],
                instructiune="Cererea nu se poate onora.", severitate=Severitate.CRITICA,
            )  # fmt: skip
        return trece("GC", "1", Treapta.V1)

    def ga(i: validare.Intrare) -> validare.Verdict:
        n = i.text.count("SLAB")
        if n:
            return avertisment(
                "GA", "1", Treapta.V1, dovezi=[Dovada("SLAB", "formulare slabă")],
                instructiune="Înlocuiește formulările slabe.", severitate=Severitate.MAJORA if n > 1 else Severitate.MINORA,
            )  # fmt: skip
        return trece("GA", "1", Treapta.V1)

    for cod, f, ordine in (("GP", gp, 10), ("GC", gc, 20), ("GA", ga, 30)):
        registru.inregistreaza(DefinitieValidator(cod, f"Probă {cod}", "1", Treapta.V1, ordine), f)


def curata(s: SarcinaReparatie) -> ContinutNou:
    return ContinutNou(
        s.continut.text.replace(INTERZIS, "").strip() + " Text curat.", autor="E4", model_autor="p/m"
    )


def test_un_validator_blocheaza_si_trimite_autorului_instructiunea_de_corectare(
    tenant: uuid.UUID, probe: None
) -> None:
    lid = livrabil_in_validare(tenant, f"Cumpără acum, {INTERZIS} la noi.")
    r = ruleaza(tenant, lid)
    assert r.decizie is validare.Decizie.REPARATIE and r.stare is Stare.IN_REPARATIE
    assert r.instructiune.splitlines()[1] == f"1. [GP] Scoate cuvântul {INTERZIS} din text."
    with sesiune_tenant(tenant) as db:
        ultima = validare.ultima_rulare(db, lid)
        assert ultima is not None and ultima.instructiune == r.instructiune and ultima.decizie == "reparatie"
        # instrucțiunea ajunge și în istoricul mutării, ca omul să o vadă în urma livrabilului
        mutare = next(t for t in productie.istoric(db, lid) if t.in_stare == "in_reparatie")
        assert mutare.detalii["instructiune"] == r.instructiune and mutare.detalii["validatori"] == ["GP"]
    [v] = [x for x in verdicte(tenant, lid) if x.validator == "GP"]
    assert (v.validator_versiune, v.treapta, v.rezultat, v.severitate) == ("1", "V1", "esec", "majora")
    assert v.dovezi == [{"fragment": INTERZIS, "regula": "cuvântul interzis nu are voie", "detalii": ""}]
    assert v.versiune == 1 and v.runda == 0 and len(v.amprenta) == 64


def test_autorul_primeste_instructiunea_repara_si_livrabilul_ajunge_validat(
    tenant: uuid.UUID, probe: None, autor_scriptat: Callable[..., list[SarcinaReparatie]]
) -> None:
    primite = autor_scriptat(curata)
    lid = livrabil_in_validare(tenant, f"Oferta {INTERZIS} de azi.", model_autor="p/m")
    r1 = ruleaza(tenant, lid)
    with sesiune_tenant(tenant) as db:
        assert validare.ruleaza_repararea(db, lid) == "in_validare"
    [sarcina] = primite
    assert sarcina.instructiune == r1.instructiune and sarcina.runda == 1 and sarcina.versiune == 1
    assert INTERZIS in sarcina.continut.text, "autorul vede textul respins"
    r2 = ruleaza(tenant, lid)
    assert r2.decizie is validare.Decizie.TRECE and r2.stare is Stare.VALIDAT
    with sesiune_tenant(tenant) as db:
        liv = productie.citeste(db, lid)
        assert liv is not None and (liv.versiune, liv.runde_reparatie) == (2, 1)
        assert [c.versiune for c in validare.continut.versiuni(db, lid)] == [1, 2]
        assert INTERZIS not in validare.continut.citeste(db, lid).text
    # verdictele pe versiuni: v1 a picat, v2 a trecut; fiecare își păstrează textul (amprenta) și runda
    v1, v2 = (
        verdicte(tenant, lid, versiune=1, validator="GP"),
        verdicte(tenant, lid, versiune=2, validator="GP"),
    )
    assert [x.rezultat for x in v1] == ["esec"] and [x.rezultat for x in v2] == ["trece"]
    assert v1[0].amprenta != v2[0].amprenta and (v1[0].runda, v2[0].runda) == (0, 1)


def test_a_treia_reparatie_merge_la_om_prin_limita_existenta_nu_prin_una_dublata(
    tenant: uuid.UUID,
    probe: None,
    autor_scriptat: Callable[..., list[SarcinaReparatie]],
    admin_engine: Engine,
) -> None:
    autor_scriptat(lambda s: ContinutNou(s.continut.text + " Tot cu INTERZIS.", autor="E4"))
    lid = livrabil_in_validare(tenant, f"Text {INTERZIS}.")
    for runda in (1, 2):
        assert ruleaza(tenant, lid).stare is Stare.IN_REPARATIE
        with sesiune_tenant(tenant) as db:
            assert validare.ruleaza_repararea(db, lid) == "in_validare"
        with sesiune_tenant(tenant) as db:
            liv = productie.citeste(db, lid)
            assert liv is not None and liv.runde_reparatie == runda
    r3 = ruleaza(tenant, lid)
    assert r3.stare is Stare.COADA_DE_ERORI and r3.escaladat == "runde_reparatie"
    with sesiune_tenant(tenant) as db:
        intrare = coada_erori.dupa_cheie(db, productie.tranzitii.cheie_escaladare(lid, 1))
        assert intrare is not None
        assert intrare.context["de_la_componenta"]["instructiune"].startswith("Textul nu a trecut validarea")
        assert len(validare.rulari(db, lid)) == 3


def test_esecul_critic_intra_in_carantina_cu_dovezile_salvate(tenant: uuid.UUID, probe: None) -> None:
    lid = livrabil_in_validare(tenant, "Ceva CRITIC aici.")
    r = ruleaza(tenant, lid)
    assert r.decizie is validare.Decizie.CARANTINA and r.stare is Stare.CARANTINA
    [v] = [x for x in verdicte(tenant, lid) if x.validator == "GC"]
    assert v.severitate == "critica" and v.dovezi[0]["fragment"] == "CRITIC"


def test_o_treapta_cu_esec_opreste_cascada_dar_toate_corecturile_ajung_odata(
    tenant: uuid.UUID, probe: None
) -> None:
    lid = livrabil_in_validare(tenant, f"{INTERZIS} și SLAB.")
    r = ruleaza(tenant, lid)
    assert [v.validator for v in r.verdicte] == ["GP", "GC", "GA"], "toți pașii treptei gratuite rulează"
    linii = r.instructiune.splitlines()
    assert linii[1].startswith("1. [GP]") and linii[2].startswith("2. [GA]"), (
        "blocajele întâi, avertismentele după"
    )


def test_avertismentele_peste_prag_cer_aprobarea_unui_om_sub_prag_nu(tenant: uuid.UUID, probe: None) -> None:
    def alt_avertisment(cod: str, ordine: int, severitate: Severitate) -> None:
        registru.inregistreaza(
            DefinitieValidator(cod, f"Probă {cod}", "1", Treapta.V1, ordine),
            lambda i: avertisment(
                cod, "1", Treapta.V1, dovezi=[Dovada("x", "r")], instructiune=f"Îmbunătățire {cod}.",
                severitate=severitate,
            ),
        )  # fmt: skip

    sub = livrabil_in_validare(tenant, "Un SLAB singur.")  # GA minoră = 1 punct
    assert ruleaza(tenant, sub).stare is Stare.VALIDAT
    alt_avertisment("GB", 40, Severitate.MAJORA)  # +2
    la_prag = livrabil_in_validare(tenant, "SLAB, SLAB.")  # GA majoră (2) + GB (2) = 4: pragul e strict
    r = ruleaza(tenant, la_prag)
    assert r.stare is Stare.VALIDAT and not r.cere_om
    alt_avertisment("GD", 50, Severitate.MINORA)  # +1
    peste = livrabil_in_validare(tenant, "SLAB, SLAB.")  # 2 + 2 + 1 = 5 > 4
    r = ruleaza(tenant, peste)
    assert r.decizie is validare.Decizie.TRECE and r.cere_om and r.stare is Stare.ASTEAPTA_APROBARE
    with sesiune_tenant(tenant) as db:
        cerere = productie.aprobari.cerere_activa(db, peste)
        assert cerere is not None and cerere.versiune == 1
        ultima = validare.ultima_rulare(db, peste)
        assert ultima is not None and (ultima.puncte, ultima.prag, ultima.cere_om) == (5, 4, True)


def test_verdictele_si_rularile_sunt_doar_adaugare(tenant: uuid.UUID, probe: None) -> None:
    lid = livrabil_in_validare(tenant, "Text bun.")
    ruleaza(tenant, lid)
    for sql in (
        "UPDATE validari_verdicte SET rezultat = 'trece' WHERE livrabil_id = :l",
        "DELETE FROM validari_verdicte WHERE livrabil_id = :l",
        "UPDATE validari_rulari SET decizie = 'trece' WHERE livrabil_id = :l",
        "DELETE FROM validari_rulari WHERE livrabil_id = :l",
        "UPDATE livrabile_continut SET text = 'altceva' WHERE livrabil_id = :l",
        "DELETE FROM livrabile_continut WHERE livrabil_id = :l",
    ):
        with pytest.raises(DBAPIError), sesiune_tenant(tenant) as db:
            db.execute(text(sql), {"l": lid})


def test_cadrul_refuza_cascada_goala_continut_lipsa_si_starea_gresita(
    tenant: uuid.UUID, registru_gol: None
) -> None:
    lid = livrabil_in_validare(tenant, "Orice text.")
    with pytest.raises(validare.FaraValidatori), sesiune_tenant(tenant) as db:
        validare.ruleaza_runda(db, lid)
    assert productie_stare(tenant, lid) is Stare.IN_VALIDARE, "niciun validator ≠ trece"
    with sesiune_tenant(tenant) as db:  # fără conținut
        l2 = productie.creeaza(db, tenant_id=tenant, tip="postare", canal="facebook").id
        for a, b in (
            (Stare.PLANIFICAT, Stare.BRIEFAT),
            (Stare.BRIEFAT, Stare.IN_SCRIERE),
            (Stare.IN_SCRIERE, Stare.IN_VALIDARE),
        ):
            productie.muta(db, l2, a, b, componenta="test")
    with pytest.raises(validare.continut.FaraContinut), sesiune_tenant(tenant) as db:
        validare.ruleaza_runda(db, l2)
    registru.inregistreaza(
        DefinitieValidator("GP", "P", "1", Treapta.V1), lambda i: trece("GP", "1", Treapta.V1)
    )
    assert ruleaza(tenant, lid).stare is Stare.VALIDAT
    with pytest.raises(validare.NuSeValideaza), sesiune_tenant(tenant) as db:
        validare.ruleaza_runda(db, lid)  # acum e `validat`


def productie_stare(tenant: uuid.UUID, lid: uuid.UUID) -> Stare:
    with sesiune_tenant(tenant) as db:
        liv = productie.citeste(db, lid)
        assert liv is not None
        return Stare(liv.stare)


def test_continutul_scris_pe_aceeasi_versiune_ridica_versiunea(tenant: uuid.UUID, om: uuid.UUID) -> None:
    with sesiune_tenant(tenant) as db:
        lid = productie.creeaza(db, tenant_id=tenant, tip="postare", canal="facebook").id
        productie.muta(db, lid, Stare.PLANIFICAT, Stare.BRIEFAT, componenta="t")
        productie.muta(db, lid, Stare.BRIEFAT, Stare.IN_SCRIERE, componenta="t")
        a = validare.continut.scrie(db, lid, text="Prima", autor="E4")
        b = validare.continut.scrie(
            db, lid, text="A doua", campuri={"titlu": "T"}, autor="E4", utilizator_id=om
        )
        assert (a.versiune, b.versiune) == (1, 2) and b.campuri == {"titlu": "T"} and b.creat_de == om
        assert validare.continut.citeste(db, lid, 1).text == "Prima"


def test_fluxul_durabil_valideaza_repara_si_se_opreste_la_validat(
    tenant: uuid.UUID, probe: None, autor_scriptat: Callable[..., list[SarcinaReparatie]], executor: None
) -> None:
    autor_scriptat(curata)
    lid = livrabil_in_validare(tenant, f"Text {INTERZIS}.")
    job = validare.trimite(tenant, lid, cheie=f"validare:{lid}:1")
    assert motor.asteapta_flux(job, timeout_sec=60).stare is motor.StareJob.TERMINAT
    assert productie_stare(tenant, lid) is Stare.VALIDAT
    assert validare.trimite(tenant, lid, cheie=f"validare:{lid}:1") == job, "idempotent pe cheie"
    with sesiune_tenant(tenant) as db:
        assert [r.decizie for r in validare.rulari(db, lid)] == ["reparatie", "trece"]


def test_fluxul_fara_autor_asteapta_in_reparatie(tenant: uuid.UUID, probe: None, executor: None) -> None:
    lid = livrabil_in_validare(tenant, f"Text {INTERZIS}.")
    job = validare.trimite(tenant, lid, cheie=f"validare:{lid}:fara-autor")
    assert motor.asteapta_flux(job, timeout_sec=60).stare is motor.StareJob.TERMINAT
    assert productie_stare(tenant, lid) is Stare.IN_REPARATIE
