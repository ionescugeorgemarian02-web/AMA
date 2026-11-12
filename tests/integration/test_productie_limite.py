"""F2.4 — limitele anti-buclă pe bază reală: reparații, predări, buget, oprirea producției, întrerupătorul global."""

import uuid
from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import Engine, text

from app import productie
from app.config import get_settings
from app.db import sesiune_agentie, sesiune_tenant
from app.operare import coada_erori, opriri
from app.operare.notificari import Nivel
from app.operare.opriri import Oprire
from app.productie import intrerupator
from app.productie.stari import Stare
from tests.integration.utile_productie import AnunturiFalse, livrabil, muta, randuri, stare

pytestmark = pytest.mark.db
S = Stare


def drum(
    tenant: uuid.UUID, lid: uuid.UUID, *stari: Stare, de_la: Stare = S.PLANIFICAT, **kw: object
) -> Stare:
    curenta = de_la
    for s in stari:
        muta(tenant, lid, curenta, s, **kw)
        curenta = s
    return curenta


def citeste(tenant: uuid.UUID, lid: uuid.UUID) -> productie.Livrabil:
    with sesiune_tenant(tenant) as db:
        rand = productie.citeste(db, lid)
        assert rand is not None
        return rand


def intrari_deschise(tenant: uuid.UUID) -> list[object]:
    with sesiune_tenant(tenant) as db:
        return list(coada_erori.lista(db))


# --- reparații: a treia rundă merge la om ------------------------------------------------------------------


def test_a_treia_runda_de_reparatie_merge_la_om_cu_diagnostic(
    tenant: uuid.UUID, anunturi: AnunturiFalse
) -> None:
    lid = livrabil(tenant)
    drum(tenant, lid, S.BRIEFAT, S.IN_SCRIERE, S.IN_VALIDARE)
    for _ in range(2):  # două runde permise
        drum(tenant, lid, S.IN_REPARATIE, S.IN_VALIDARE, de_la=S.IN_VALIDARE)
    assert citeste(tenant, lid).runde_reparatie == 2
    assert anunturi.trimise == [] and intrari_deschise(tenant) == []

    rez = muta(
        tenant, lid, S.IN_VALIDARE, S.IN_REPARATIE, detalii={"verdict": "hook slab", "validator": "G1"}
    )
    assert not rez.aplicat and rez.cerut == S.IN_REPARATIE and rez.stare == S.COADA_DE_ERORI
    assert rez.escaladat == "runde_reparatie" and rez.intrare_eroare_id is not None
    liv = citeste(tenant, lid)
    assert (liv.stare, liv.runde_reparatie, liv.escaladari, liv.stare_anterioara) == (
        "coada_de_erori",
        2,
        1,
        "in_validare",
    )

    # intrare vizibilă pentru om, în coada de erori existentă, cu diagnostic
    [intrare] = intrari_deschise(tenant)
    assert intrare.id == rez.intrare_eroare_id  # type: ignore[attr-defined]
    assert (intrare.severitate, intrare.flux, intrare.pas, intrare.stare) == (  # type: ignore[attr-defined]
        "major",
        "livrabil",
        "in_validare",
        "noua",
    )
    d = intrare.context  # type: ignore[attr-defined]
    assert d["tip_sursa"] == "livrabil" and d["limita_depasita"] == "runde_reparatie"
    assert d["contoare"]["runde_reparatie"] == 2 and d["limite"]["runde_reparatie"] == 2
    assert d["de_la_componenta"] == {"verdict": "hook slab", "validator": "G1"}
    assert [t["in"] for t in d["ultimele_tranzitii"]][-3:] == ["in_validare", "in_reparatie", "in_validare"]
    # un om este anunțat (după commit)
    assert anunturi.nivele() == [Nivel.IMPORTANT] and anunturi.trimise[0][3] == f"/alerte/{intrare.id}"  # type: ignore[attr-defined]
    # istoricul: mutarea escaladată e aplicată în coada de erori, cu mutarea cerută în detalii
    ultimul = randuri_aplicate(tenant, lid)[-1]
    assert (ultimul["din"], ultimul["in_stare"]) == ("in_validare", "coada_de_erori")
    assert ultimul["detalii"] == {"cerut": "in_reparatie", "limita": "runde_reparatie"}
    assert "limită depășită" in str(ultimul["motiv"])


def randuri_aplicate(tenant: uuid.UUID, lid: uuid.UUID) -> list[dict[str, object]]:
    with sesiune_tenant(tenant) as db:
        return [
            {"din": t.din, "in_stare": t.in_stare, "motiv": t.motiv, "detalii": t.detalii}
            for t in productie.istoric(db, lid, si_refuzuri=False)
        ]


def test_escaladarea_se_anuleaza_cu_tranzactia_apelantului(
    tenant: uuid.UUID, anunturi: AnunturiFalse
) -> None:
    lid = livrabil(tenant)
    drum(tenant, lid, S.BRIEFAT, S.IN_SCRIERE, S.IN_VALIDARE)
    for _ in range(2):
        drum(tenant, lid, S.IN_REPARATIE, S.IN_VALIDARE, de_la=S.IN_VALIDARE)

    class Ratat(Exception):
        pass

    with pytest.raises(Ratat), sesiune_tenant(tenant) as db:
        assert productie.muta(db, lid, S.IN_VALIDARE, S.IN_REPARATIE, componenta="G1").escaladat
        raise Ratat
    assert stare(tenant, lid) == S.IN_VALIDARE
    assert intrari_deschise(tenant) == [] and anunturi.trimise == [], (
        "nici intrare, nici anunț pentru ceva anulat"
    )


def test_orice_runda_a_treia_pe_orice_cale_este_oprita(tenant: uuid.UUID) -> None:
    """Și după un eșec temporar: ocolirea prin `esec_temporar` nu dă runde în plus."""
    lid = livrabil(tenant)
    drum(tenant, lid, S.BRIEFAT, S.IN_SCRIERE, S.IN_VALIDARE, S.IN_REPARATIE, S.IN_VALIDARE, S.IN_REPARATIE)
    muta(tenant, lid, S.IN_REPARATIE, S.ESEC_TEMPORAR)
    rez = muta(
        tenant, lid, S.ESEC_TEMPORAR, S.IN_REPARATIE
    )  # revenirea nu e o rundă nouă... dar nici nu o ocolește
    assert rez.escaladat == "runde_reparatie", (
        "a treia intrare în reparație (chiar prin revenire) merge la om"
    )


# --- predări -----------------------------------------------------------------------------------------------


def test_a_treisprezecea_predare_merge_la_om(tenant: uuid.UUID) -> None:
    lid = livrabil(tenant)
    drum(tenant, lid, S.BRIEFAT, S.IN_SCRIERE)  # predarea 1
    for _ in range(11):  # predările 2..12
        muta(tenant, lid, S.IN_SCRIERE, S.ESEC_TEMPORAR)
        assert muta(tenant, lid, S.ESEC_TEMPORAR, S.IN_SCRIERE).aplicat
    assert citeste(tenant, lid).predari == 12
    muta(tenant, lid, S.IN_SCRIERE, S.ESEC_TEMPORAR)
    rez = muta(tenant, lid, S.ESEC_TEMPORAR, S.IN_SCRIERE)  # a 13-a
    assert rez.escaladat == "predari" and rez.stare == S.COADA_DE_ERORI
    liv = citeste(tenant, lid)
    assert (liv.stare, liv.predari, liv.stare_anterioara) == ("coada_de_erori", 12, "in_scriere")
    [intrare] = intrari_deschise(tenant)
    assert intrare.context["limita_depasita"] == "predari"  # type: ignore[attr-defined]


def test_pragurile_se_pot_configura(tenant: uuid.UUID, config: Callable[..., None]) -> None:
    config(productie_runde_reparatie="1", productie_predari_max="3")
    lid = livrabil(tenant)
    # predări: in_scriere (1), in_validare (2), in_reparatie (3); runde de reparație: 1 (permisă, pragul e 1)
    drum(tenant, lid, S.BRIEFAT, S.IN_SCRIERE, S.IN_VALIDARE, S.IN_REPARATIE)
    assert (citeste(tenant, lid).predari, citeste(tenant, lid).runde_reparatie) == (3, 1)
    rez = muta(tenant, lid, S.IN_REPARATIE, S.IN_VALIDARE)  # a patra predare, cu pragul de 3
    assert rez.escaladat == "predari" and rez.stare == S.COADA_DE_ERORI


# --- buget -------------------------------------------------------------------------------------------------


def test_bugetul_de_apeluri_oprește_livrabilul_cand_se_depaseste(
    tenant: uuid.UUID, anunturi: AnunturiFalse
) -> None:
    lid = livrabil(tenant)
    drum(tenant, lid, S.BRIEFAT, S.IN_SCRIERE)
    buget = citeste(tenant, lid).buget_apeluri_llm
    with sesiune_tenant(tenant) as db:
        c = productie.inregistreaza_consum(db, lid, apeluri_llm=buget, secunde=5.0, componenta="E1")
        assert c.depasit is None and not c.escaladat and c.apeluri_llm == buget, "exact bugetul e în regulă"
        liv = productie.citeste(db, lid)
        assert liv is not None and productie.poate_consuma(liv, 0) and not productie.poate_consuma(liv, 1)
    with sesiune_tenant(tenant) as db:
        c = productie.inregistreaza_consum(
            db, lid, apeluri_llm=1, componenta="E1", diagnostic={"model": "simulat"}
        )
    assert c.depasit is productie.Depasire.BUGET_APELURI and c.escaladat and c.intrare_eroare_id
    assert stare(tenant, lid) == S.COADA_DE_ERORI
    assert citeste(tenant, lid).apeluri_llm == buget + 1, "consumul rămâne adevărat"
    [intrare] = intrari_deschise(tenant)
    assert intrare.context["limita_depasita"] == "buget_apeluri"  # type: ignore[attr-defined]
    assert intrare.context["de_la_componenta"] == {"model": "simulat"}  # type: ignore[attr-defined]
    assert anunturi.nivele() == [Nivel.IMPORTANT]
    # nu se escaladează a doua oară
    with sesiune_tenant(tenant) as db:
        c2 = productie.inregistreaza_consum(db, lid, apeluri_llm=1, componenta="E1")
    assert c2.depasit and not c2.escaladat and len(intrari_deschise(tenant)) == 1


def test_bugetul_de_timp_oprește_livrabilul(tenant: uuid.UUID) -> None:
    lid = livrabil(tenant)
    drum(tenant, lid, S.BRIEFAT, S.IN_SCRIERE)
    buget = citeste(tenant, lid).buget_timp_sec
    with sesiune_tenant(tenant) as db:
        assert not productie.inregistreaza_consum(db, lid, secunde=buget, componenta="E1").escaladat
    with sesiune_tenant(tenant) as db:
        c = productie.inregistreaza_consum(db, lid, secunde=0.5, componenta="E1")
    assert c.depasit is productie.Depasire.BUGET_TIMP and c.escaladat
    assert stare(tenant, lid) == S.COADA_DE_ERORI


def test_consumul_unui_livrabil_neactiv_se_inregistreaza_fara_escaladare(tenant: uuid.UUID) -> None:
    lid = livrabil(tenant)  # planificat: din „planificat” nu se poate escalada
    with sesiune_tenant(tenant) as db:
        c = productie.inregistreaza_consum(db, lid, apeluri_llm=10_000, componenta="test")
    assert c.depasit and not c.escaladat and stare(tenant, lid) == S.PLANIFICAT


def test_bugetul_este_per_livrabil_si_din_configurare(tenant: uuid.UUID, config: Callable[..., None]) -> None:
    config(productie_buget_apeluri_llm="3", productie_buget_timp_sec="10")
    lid = livrabil(tenant)
    liv = citeste(tenant, lid)
    assert (liv.buget_apeluri_llm, liv.buget_timp_sec) == (3, 10)
    config(productie_buget_apeluri_llm="40", productie_buget_timp_sec="3600")
    assert citeste(tenant, lid).buget_apeluri_llm == 3, "un livrabil păstrează bugetul cu care a pornit"


def test_consumul_negativ_este_refuzat(tenant: uuid.UUID) -> None:
    lid = livrabil(tenant)
    with pytest.raises(ValueError), sesiune_tenant(tenant) as db:
        productie.inregistreaza_consum(db, lid, apeluri_llm=-1, componenta="test")


# --- reluarea de către om ----------------------------------------------------------------------------------


def test_omul_reia_livrabilul_cu_randuri_noi_si_intrarea_se_inchide(
    tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    lid = livrabil(tenant)
    drum(tenant, lid, S.BRIEFAT, S.IN_SCRIERE, S.IN_VALIDARE)
    for _ in range(2):
        drum(tenant, lid, S.IN_REPARATIE, S.IN_VALIDARE, de_la=S.IN_VALIDARE)
    muta(tenant, lid, S.IN_VALIDARE, S.IN_REPARATIE)  # escaladat
    inainte = citeste(tenant, lid)
    with pytest.raises(ValueError), sesiune_tenant(tenant, om) as db:
        productie.reia_de_om(db, lid, utilizator_id=om, motiv=" ")
    with sesiune_tenant(tenant, om) as db:
        rez = productie.reia_de_om(db, lid, utilizator_id=om, motiv="am schimbat promptul")
    assert rez.stare == S.IN_VALIDARE
    liv = citeste(tenant, lid)
    s = get_settings()
    assert (liv.stare, liv.runde_reparatie, liv.stare_anterioara) == ("in_validare", 0, None)
    assert liv.predari == 1, "resetat, apoi intrarea în starea de lucru numără din nou"
    assert liv.buget_apeluri_llm == inainte.buget_apeluri_llm + s.productie_buget_apeluri_llm
    assert intrari_deschise(tenant) == [], "intrarea din coada de erori s-a închis"
    with sesiune_tenant(tenant) as db:
        i = db.query(coada_erori.IntrareEroare).one() if hasattr(coada_erori, "IntrareEroare") else None
        assert (
            i is not None
            and i.stare == "inchisa"
            and i.inchis_de == om
            and "am schimbat" in i.motiv_inchidere
        )
    with admin_engine.connect() as c:
        a = c.execute(
            text(
                "SELECT utilizator_id, tenant_id, detalii FROM jurnal_audit "
                "WHERE actiune = 'livrabil.reluat_de_om' AND obiect_id = :l"
            ),
            {"l": str(lid)},
        ).one()
    assert (a.utilizator_id, a.tenant_id) == (om, tenant) and a.detalii["in_starea"] == "in_validare"
    ultimul = randuri(admin_engine, lid)[-1]
    assert ultimul["actor_tip"] == "utilizator" and ultimul["in_stare"] == "in_validare"
    # primește iar rânduri: o rundă de reparație merge
    assert muta(tenant, lid, S.IN_VALIDARE, S.IN_REPARATIE).aplicat


def test_reluarea_de_om_doar_din_coada_de_erori(
    tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    lid = livrabil(tenant)
    with pytest.raises(productie.TranzitieNepermisa), sesiune_tenant(tenant, om) as db:
        productie.reia_de_om(db, lid, utilizator_id=om, motiv="vreau")
    assert randuri(admin_engine, lid)[-1]["rezultat"] == "refuzata"


# --- producția nouă respectă opririle ---------------------------------------------------------------------


def opreste(tip: Oprire, om: uuid.UUID, *, tenant: uuid.UUID | None = None, activ: bool = True) -> None:
    with sesiune_agentie(om) as db:
        opriri.seteaza(db, tip, activ, canal="panou", motiv="test", tenant_id=tenant, utilizator_id=om)


def test_oprirea_globala_a_productiei_opreste_pornirea_de_lucru_nou(tenant: uuid.UUID, om: uuid.UUID) -> None:
    in_lucru = livrabil(tenant)
    drum(tenant, in_lucru, S.BRIEFAT, S.IN_SCRIERE)
    nou = livrabil(tenant)
    opreste(Oprire.PRODUCTIE, om)
    with pytest.raises(productie.ProductieOprita), sesiune_tenant(tenant) as db:
        productie.muta(db, nou, S.PLANIFICAT, S.BRIEFAT, componenta="D5")
    assert stare(tenant, nou) == S.PLANIFICAT, "nu se pierde nimic: rămâne planificat"
    assert muta(tenant, in_lucru, S.IN_SCRIERE, S.IN_VALIDARE).aplicat, (
        "ce e deja în lucru își termină drumul"
    )
    opreste(Oprire.PRODUCTIE, om, activ=False)
    assert muta(tenant, nou, S.PLANIFICAT, S.BRIEFAT).aplicat


def test_oprirea_pe_client_opreste_doar_clientul(
    tenant: uuid.UUID, fabrica_clienti: Callable[[], uuid.UUID], om: uuid.UUID
) -> None:
    alt_client = fabrica_clienti()
    a, b = livrabil(tenant), livrabil(alt_client)
    opreste(Oprire.CLIENT, om, tenant=tenant)
    with pytest.raises(productie.ProductieOprita), sesiune_tenant(tenant) as db:
        productie.muta(db, a, S.PLANIFICAT, S.BRIEFAT, componenta="D5")
    assert muta(alt_client, b, S.PLANIFICAT, S.BRIEFAT).aplicat
    with sesiune_tenant(tenant) as db:
        assert intrerupator.blocaj(db, tenant) is not None
    with sesiune_tenant(alt_client) as db:
        assert intrerupator.blocaj(db, alt_client) is None


def test_oprirea_publicarii_nu_opreste_productia(tenant: uuid.UUID, om: uuid.UUID) -> None:
    lid = livrabil(tenant)
    opreste(Oprire.PUBLICARE, om)
    assert muta(tenant, lid, S.PLANIFICAT, S.BRIEFAT).aplicat


# --- întrerupătorul global ---------------------------------------------------------------------------------


@pytest.fixture
def istoric_curat(admin_engine: Engine) -> Iterator[None]:
    """Întrerupătorul numără rezultatele tuturor clienților din ultima oră; testele anterioare au lăsat istoric
    (doar-adăugare pentru aplicație). Superutilizatorul îl golește, cu declanșatoarele oprite pe durata golirii."""
    with admin_engine.begin() as c:
        c.execute(text("ALTER TABLE livrabile_tranzitii DISABLE TRIGGER USER"))
        c.execute(text("TRUNCATE livrabile_tranzitii"))
        c.execute(text("ALTER TABLE livrabile_tranzitii ENABLE TRIGGER USER"))
    yield


def rezultat(tenant: uuid.UUID, reusit: bool) -> None:
    """Un livrabil care ajunge la capăt (`validat`) sau la om (`coada_de_erori`)."""
    lid = livrabil(tenant)
    drum(tenant, lid, S.BRIEFAT, S.IN_SCRIERE)
    if reusit:
        drum(tenant, lid, S.IN_VALIDARE, S.VALIDAT, de_la=S.IN_SCRIERE)
    else:
        muta(tenant, lid, S.IN_SCRIERE, S.COADA_DE_ERORI)


def evalueaza() -> intrerupator.Evaluare:
    with sesiune_agentie() as db:
        return intrerupator.evalueaza(db)


def oprita_productia() -> bool:
    with sesiune_agentie() as db:
        return opriri.este_oprit(db, Oprire.PRODUCTIE)


def test_un_esec_din_doua_nu_declanseaza_intrerupatorul(
    tenant: uuid.UUID, istoric_curat: None, anunturi: AnunturiFalse
) -> None:
    rezultat(tenant, True)
    rezultat(tenant, False)
    e = evalueaza()
    assert (e.succese, e.esecuri, e.rata) == (1, 1, 0.5)
    assert not e.declansat_acum and not oprita_productia() and anunturi.trimise == []


def test_exact_pragul_nu_declanseaza(tenant: uuid.UUID, istoric_curat: None) -> None:
    for reusit in [True] * 7 + [False] * 3:  # 30% din 10
        rezultat(tenant, reusit)
    assert not evalueaza().declansat_acum and not oprita_productia()


def test_rata_peste_prag_opreste_productia_noua_si_anunta(
    tenant: uuid.UUID, istoric_curat: None, anunturi: AnunturiFalse, admin_engine: Engine
) -> None:
    for reusit in [True] * 6 + [False] * 4:  # 40% din 10
        rezultat(tenant, reusit)
    e = evalueaza()
    assert e.declansat_acum and e.oprit and (e.succese, e.esecuri) == (6, 4)
    assert oprita_productia()
    with sesiune_agentie() as db:
        rand = opriri.citeste(db, Oprire.PRODUCTIE)
        assert rand is not None and rand.canal == "sistem" and "4 eșecuri din 10" in rand.motiv
    assert anunturi.nivele() == [Nivel.CRITIC]
    with admin_engine.connect() as c:
        a = c.execute(
            text(
                "SELECT actor_tip, utilizator_id FROM jurnal_audit WHERE actiune = 'oprire.oprit' AND obiect_id = 'productie' ORDER BY id DESC LIMIT 1"
            )
        ).one()
    assert (a.actor_tip, a.utilizator_id) == ("sistem", None)
    # producția NOUĂ nu mai pornește
    nou = livrabil(tenant)
    with pytest.raises(productie.ProductieOprita), sesiune_tenant(tenant) as db:
        productie.muta(db, nou, S.PLANIFICAT, S.BRIEFAT, componenta="D5")
    # o a doua evaluare nu anunță din nou
    assert evalueaza().oprit and not evalueaza().declansat_acum and len(anunturi.trimise) == 1


def test_intrerupatorul_nu_se_repornește_singur_ci_doar_de_om_cu_audit(
    tenant: uuid.UUID, om: uuid.UUID, istoric_curat: None, admin_engine: Engine
) -> None:
    in_lucru = [livrabil(tenant) for _ in range(30)]
    for lid in in_lucru:  # pornite înainte de oprire
        drum(tenant, lid, S.BRIEFAT, S.IN_SCRIERE)
    for reusit in [False] * 10:
        rezultat(tenant, reusit)
    assert evalueaza().declansat_acum
    for lid in in_lucru:  # ce era în lucru își termină drumul: rata scade sub prag, dar nimic nu repornește
        drum(tenant, lid, S.IN_VALIDARE, S.VALIDAT, de_la=S.IN_SCRIERE)
    assert evalueaza().oprit and oprita_productia(), "repornirea e doar a omului"
    opreste(Oprire.PRODUCTIE, om, activ=False)
    assert not oprita_productia()
    a = randuri_audit(admin_engine, "oprire.repornit", "productie")
    assert a and a[-1]["utilizator_id"] == om and a[-1]["detalii"]["canal"] == "panou"  # type: ignore[index]
    # după repornire, rezultatele de dinainte nu mai contează: nu se declanșează iar imediat
    e = evalueaza()
    assert not e.declansat_acum and (e.succese, e.esecuri) == (0, 0)
    for reusit in [False] * 10:  # dar eșecuri noi îl declanșează din nou
        rezultat(tenant, reusit)
    assert evalueaza().declansat_acum


def randuri_audit(admin: Engine, actiune: str, obiect_id: str) -> list[dict[str, object]]:
    with admin.connect() as c:
        return [
            dict(r._mapping)
            for r in c.execute(
                text(
                    "SELECT utilizator_id, detalii FROM jurnal_audit WHERE actiune = :a AND obiect_id = :o ORDER BY id"
                ),
                {"a": actiune, "o": obiect_id},
            )
        ]


def test_rezultatele_se_numara_pe_o_fereastra(tenant: uuid.UUID, istoric_curat: None) -> None:
    import datetime as dt

    for reusit in [False] * 10:
        rezultat(tenant, reusit)
    viitor = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=get_settings().intrerupator_fereastra_min + 5)
    with sesiune_agentie() as db:
        e = intrerupator.evalueaza(db, acum=viitor)
    assert (e.succese, e.esecuri) == (0, 0) and not e.declansat_acum, "rezultatele vechi ies din fereastră"


def test_intrerupatorul_este_configurabil(
    tenant: uuid.UUID, istoric_curat: None, config: Callable[..., None]
) -> None:
    config(intrerupator_volum_min="2", intrerupator_prag_esec="0.4")
    rezultat(tenant, True)
    rezultat(tenant, False)  # 50% din 2
    assert evalueaza().declansat_acum
