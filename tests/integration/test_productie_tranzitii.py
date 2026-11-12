"""F2.3 — mașina de stări a livrabilului pe bază reală: o singură ușă (`muta`), refuz înregistrat, concurență."""

import threading
import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app import productie
from app.config import get_settings
from app.db import sesiune_agentie, sesiune_tenant
from app.productie import stari
from app.productie.stari import Stare
from tests.integration.utile_productie import livrabil, muta, randuri, stare

pytestmark = pytest.mark.db


# --- creare ------------------------------------------------------------------------------------------------


def test_livrabilul_nou_incepe_planificat_cu_buget_si_istoric(
    tenant: uuid.UUID, admin_engine: Engine
) -> None:
    lid = livrabil(tenant)
    s = get_settings()
    with sesiune_tenant(tenant) as db:
        livr = productie.citeste(db, lid)
        assert livr is not None
        assert (livr.stare, livr.versiune, livr.runde_reparatie, livr.predari, livr.apeluri_llm) == (
            "planificat",
            1,
            0,
            0,
            0,
        )
        assert (livr.buget_apeluri_llm, livr.buget_timp_sec) == (
            s.productie_buget_apeluri_llm,
            s.productie_buget_timp_sec,
        )
        assert livr.clasa_actiune == "publicare_continut" and livr.id.version == 7
    primul = randuri(admin_engine, lid)[0]
    assert (primul["rezultat"], primul["din"], primul["in_stare"]) == ("aplicata", None, "planificat")


# --- mutări permise ----------------------------------------------------------------------------------------


def test_drumul_unui_text_pana_la_inchis_scrie_istoricul_in_ordine(
    tenant: uuid.UUID, admin_engine: Engine
) -> None:
    lid = livrabil(tenant)
    drum = [
        Stare.BRIEFAT,
        Stare.IN_SCRIERE,
        Stare.IN_VALIDARE,
        Stare.VALIDAT,
        Stare.APROBAT,  # aici gardă de aprobare vine în F2.8; în F2.3 tabelul o permite
        Stare.PROGRAMAT,
        Stare.IN_PUBLICARE,
        Stare.PUBLICAT,
        Stare.IN_MASURARE,
        Stare.INCHIS,
    ]
    curenta = Stare.PLANIFICAT
    for urmatoarea in drum:
        rez = muta(tenant, lid, curenta, urmatoarea, componenta="D5")
        assert rez.aplicat and rez.stare == urmatoarea
        curenta = urmatoarea
    assert stare(tenant, lid) == Stare.INCHIS
    r = randuri(admin_engine, lid)
    assert [x["in_stare"] for x in r] == ["planificat", *[s.value for s in drum]]
    assert all(x["rezultat"] == "aplicata" for x in r)
    assert r[1]["componenta"] == "D5" and r[1]["actor_tip"] == "componenta"
    with admin_engine.connect() as c:
        n = c.execute(
            text(
                "SELECT count(*) FROM jurnal_evenimente WHERE tip = 'livrabil.tranzitie' AND obiect_id = :i"
            ),
            {"i": str(lid)},
        ).scalar_one()
    assert n == len(drum), "fiecare tranziție aplicată emite un eveniment (22.1)"


def test_un_om_apare_in_istoric_cu_numele_lui(tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine) -> None:
    lid = livrabil(tenant)
    muta(tenant, lid, Stare.PLANIFICAT, Stare.ANULAT, utilizator_id=om, motiv="clientul a renunțat")
    ultimul = randuri(admin_engine, lid)[-1]
    assert (ultimul["actor_tip"], ultimul["motiv"]) == ("utilizator", "clientul a renunțat")


# --- mutări refuzate ---------------------------------------------------------------------------------------


def test_tranzitia_nepermisa_este_refuzata_si_inregistrata(tenant: uuid.UUID, admin_engine: Engine) -> None:
    lid = livrabil(tenant)
    with pytest.raises(productie.TranzitieNepermisa) as e, sesiune_tenant(tenant) as db:
        productie.muta(db, lid, Stare.PLANIFICAT, Stare.PUBLICAT, componenta="H1")
    assert e.value.cod == "nepermisa" and "nu se poate trece" in str(e.value)
    assert stare(tenant, lid) == Stare.PLANIFICAT, "starea nu s-a mișcat"
    refuz = randuri(admin_engine, lid)[-1]
    assert (refuz["rezultat"], refuz["din"], refuz["in_stare"], refuz["componenta"]) == (
        "refuzata",
        "planificat",
        "publicat",
        "H1",
    )
    assert refuz["detalii"] == {"cod": "nepermisa"} and "Planificat" in str(refuz["motiv"])
    with sesiune_tenant(tenant) as db:
        assert (
            len(productie.istoric(db, lid)) == 2 and len(productie.istoric(db, lid, si_refuzuri=False)) == 1
        )


def test_refuzul_supravietuieste_rollback_ului_apelantului(tenant: uuid.UUID, admin_engine: Engine) -> None:
    lid = livrabil(tenant)

    class Ratat(Exception):
        pass

    with pytest.raises(Ratat), sesiune_tenant(tenant) as db:
        productie.muta(
            db, lid, Stare.PLANIFICAT, Stare.BRIEFAT, componenta="D5"
        )  # o mutare bună, în tranzacția lui
        try:
            productie.muta(db, lid, Stare.BRIEFAT, Stare.PUBLICAT, componenta="D5")
        except productie.TranzitieNepermisa:
            raise Ratat from None  # apelantul își anulează tranzacția
    assert stare(tenant, lid) == Stare.PLANIFICAT, "tranzacția apelantului s-a anulat, cu mutarea bună cu tot"
    r = randuri(admin_engine, lid)
    assert [x["rezultat"] for x in r] == ["aplicata", "refuzata"], "dar refuzul a rămas"
    assert (r[-1]["din"], r[-1]["in_stare"]) == ("briefat", "publicat")


def test_conflictul_de_stare_este_refuzat_si_inregistrat(tenant: uuid.UUID, admin_engine: Engine) -> None:
    lid = livrabil(tenant)
    muta(tenant, lid, Stare.PLANIFICAT, Stare.BRIEFAT)
    with pytest.raises(productie.ConflictStare) as e, sesiune_tenant(tenant) as db:
        productie.muta(
            db, lid, Stare.PLANIFICAT, Stare.ANULAT, componenta="test"
        )  # credea că e încă planificat
    assert e.value.cod == "conflict"
    assert stare(tenant, lid) == Stare.BRIEFAT
    assert randuri(admin_engine, lid)[-1]["detalii"] == {"cod": "conflict"}


def test_versiunea_asteptata_se_verifica(tenant: uuid.UUID) -> None:
    lid = livrabil(tenant)
    with pytest.raises(productie.VersiuneNepotrivita), sesiune_tenant(tenant) as db:
        productie.muta(db, lid, Stare.PLANIFICAT, Stare.BRIEFAT, componenta="test", versiune=7)
    muta(tenant, lid, Stare.PLANIFICAT, Stare.BRIEFAT, versiune=1)


def test_o_stare_finala_nu_mai_iese_nicaieri(tenant: uuid.UUID) -> None:
    lid = livrabil(tenant)
    muta(tenant, lid, Stare.PLANIFICAT, Stare.ANULAT)
    for la in Stare:
        with pytest.raises(productie.TranzitieRefuzata), sesiune_tenant(tenant) as db:
            productie.muta(db, lid, Stare.ANULAT, la, componenta="test")


def test_livrabil_inexistent_sau_al_altui_client(tenant: uuid.UUID, fabrica_clienti) -> None:  # type: ignore[no-untyped-def]
    alt_client = fabrica_clienti()
    lid = livrabil(tenant)
    with pytest.raises(productie.LivrabilInexistent), sesiune_tenant(alt_client) as db:
        productie.muta(db, lid, Stare.PLANIFICAT, Stare.ANULAT, componenta="test")
    with pytest.raises(productie.LivrabilInexistent), sesiune_tenant(tenant) as db:
        productie.muta(db, uuid.uuid4(), Stare.PLANIFICAT, Stare.ANULAT, componenta="test")
    assert stare(tenant, lid) == Stare.PLANIFICAT


# --- revenirea din eșec temporar și din coada de erori; ieșirea doar prin om --------------------------------


def _pana_la(tenant: uuid.UUID, lid: uuid.UUID, *drum: Stare) -> Stare:
    curenta = Stare.PLANIFICAT
    for s in drum:
        muta(tenant, lid, curenta, s)
        curenta = s
    return curenta


def test_din_esec_temporar_se_revine_doar_unde_era(tenant: uuid.UUID) -> None:
    lid = livrabil(tenant)
    _pana_la(tenant, lid, Stare.BRIEFAT, Stare.IN_SCRIERE, Stare.IN_VALIDARE)
    muta(tenant, lid, Stare.IN_VALIDARE, Stare.ESEC_TEMPORAR, motiv="furnizor căzut")
    with sesiune_tenant(tenant) as db:
        assert productie.citeste(db, lid).stare_anterioara == "in_validare"  # type: ignore[union-attr]
    with pytest.raises(productie.TranzitieNepermisa), sesiune_tenant(tenant) as db:
        productie.muta(db, lid, Stare.ESEC_TEMPORAR, Stare.IN_SCRIERE, componenta="test")
    muta(tenant, lid, Stare.ESEC_TEMPORAR, Stare.IN_VALIDARE)
    with sesiune_tenant(tenant) as db:
        assert productie.citeste(db, lid).stare_anterioara is None  # type: ignore[union-attr]


def test_escaladarea_din_esec_temporar_pastreaza_starea_de_dinainte(tenant: uuid.UUID, om: uuid.UUID) -> None:
    lid = livrabil(tenant)
    _pana_la(tenant, lid, Stare.BRIEFAT, Stare.IN_SCRIERE)
    muta(tenant, lid, Stare.IN_SCRIERE, Stare.ESEC_TEMPORAR)
    muta(tenant, lid, Stare.ESEC_TEMPORAR, Stare.COADA_DE_ERORI)
    with sesiune_tenant(tenant) as db:
        assert productie.citeste(db, lid).stare_anterioara == "in_scriere"  # type: ignore[union-attr]
    muta(tenant, lid, Stare.COADA_DE_ERORI, Stare.IN_SCRIERE, utilizator_id=om, motiv="reluat de om")
    assert stare(tenant, lid) == Stare.IN_SCRIERE


def test_din_coada_de_erori_iese_doar_un_om(tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine) -> None:
    lid = livrabil(tenant)
    _pana_la(tenant, lid, Stare.BRIEFAT, Stare.IN_SCRIERE, Stare.COADA_DE_ERORI)
    with pytest.raises(productie.TranzitieNepermisa) as e, sesiune_tenant(tenant) as db:
        productie.muta(
            db, lid, Stare.COADA_DE_ERORI, Stare.IN_SCRIERE, componenta="D5"
        )  # o componentă, nu un om
    assert e.value.cod == "doar_om"
    assert randuri(admin_engine, lid)[-1]["rezultat"] == "refuzata"
    muta(tenant, lid, Stare.COADA_DE_ERORI, Stare.IN_SCRIERE, utilizator_id=om)
    assert stare(tenant, lid) == Stare.IN_SCRIERE


# --- versiunea conținutului --------------------------------------------------------------------------------


def test_versiunea_creste_doar_cat_continutul_poate_fi_schimbat(tenant: uuid.UUID) -> None:
    lid = livrabil(tenant)
    with pytest.raises(productie.TranzitieNepermisa), sesiune_tenant(tenant) as db:
        productie.versiune_noua(db, lid, componenta="E1")  # încă planificat: nu există conținut
    _pana_la(tenant, lid, Stare.BRIEFAT, Stare.IN_SCRIERE)
    with sesiune_tenant(tenant) as db:
        assert productie.versiune_noua(db, lid, componenta="E1") == 2


# --- declanșatorul din bază --------------------------------------------------------------------------------


def _executa_ca_aplicatie(tenant: uuid.UUID, sql: str, **params: object) -> None:
    with sesiune_tenant(tenant) as db:
        db.execute(text(sql), params)


def test_baza_refuza_schimbarea_directa_a_starii(tenant: uuid.UUID) -> None:
    lid = livrabil(tenant)
    # o pereche permisă, dar fără `muta`
    with pytest.raises(DBAPIError, match=r"doar prin productie\.muta"):
        _executa_ca_aplicatie(tenant, "UPDATE livrabile SET stare = 'briefat' WHERE id = :i", i=lid)
    # o pereche nepermisă, chiar cu marcajul pus de cineva care ocolește `muta`
    with pytest.raises(DBAPIError, match="tranziție nepermisă"), sesiune_tenant(tenant) as db:
        db.execute(text("SELECT set_config('app.muta_livrabil', :s, true)"), {"s": str(lid)})
        db.execute(text("UPDATE livrabile SET stare = 'publicat' WHERE id = :i"), {"i": lid})
    assert stare(tenant, lid) == Stare.PLANIFICAT


def test_baza_refuza_inserarea_intr_o_stare_avansata_si_mutarea_la_alt_client(
    tenant: uuid.UUID,
    fabrica_clienti,  # type: ignore[no-untyped-def]
) -> None:
    lid = livrabil(tenant)
    with pytest.raises(DBAPIError, match="începe în starea planificat"):
        _executa_ca_aplicatie(
            tenant,
            "INSERT INTO livrabile (id, tenant_id, tip, canal, stare, buget_apeluri_llm, buget_timp_sec) "
            "VALUES (:i, :t, 'postare', 'x', 'publicat', 1, 1)",
            i=uuid.uuid4(),
            t=tenant,
        )
    with pytest.raises(DBAPIError):
        _executa_ca_aplicatie(
            tenant, "UPDATE livrabile SET tenant_id = :t WHERE id = :i", t=fabrica_clienti(), i=lid
        )


def test_functia_din_baza_are_exact_perechile_din_cod(admin_engine: Engine) -> None:
    with admin_engine.connect() as c:
        permise = {
            (d, la)
            for d in Stare
            for la in Stare
            if c.execute(
                text("SELECT ama_livrabil_tranzitie_permisa(:d, :l)"), {"d": d.value, "l": la.value}
            ).scalar_one()
        }
    assert permise == {(Stare(d), Stare(la)) for d, la in stari.perechi()}


def test_istoricul_este_doar_pentru_adaugare(tenant: uuid.UUID) -> None:
    lid = livrabil(tenant)
    for sql in (
        "UPDATE livrabile_tranzitii SET motiv = 'x' WHERE livrabil_id = :i",
        "DELETE FROM livrabile_tranzitii WHERE livrabil_id = :i",
    ):
        with pytest.raises(DBAPIError):
            _executa_ca_aplicatie(tenant, sql, i=lid)
    with pytest.raises(DBAPIError):  # nici livrabilul nu se șterge
        _executa_ca_aplicatie(tenant, "DELETE FROM livrabile WHERE id = :i", i=lid)


# --- concurență --------------------------------------------------------------------------------------------


def test_doua_tranzitii_simultane_pe_acelasi_livrabil_reusesc_o_singura_data(
    tenant: uuid.UUID, admin_engine: Engine
) -> None:
    lid = livrabil(tenant)
    _pana_la(tenant, lid, Stare.BRIEFAT, Stare.IN_SCRIERE, Stare.IN_VALIDARE)
    a_blocat, a_poate_inchide = threading.Event(), threading.Event()
    rezultate: dict[str, object] = {}

    def a() -> None:
        try:
            with sesiune_tenant(tenant) as db:
                productie.muta(db, lid, Stare.IN_VALIDARE, Stare.VALIDAT, componenta="G1")
                a_blocat.set()  # ține rândul blocat, cu tranzacția deschisă
                assert a_poate_inchide.wait(20)
            rezultate["a"] = "ok"
        except Exception as e:
            rezultate["a"] = e

    def b() -> None:
        try:
            with sesiune_tenant(tenant) as db:
                productie.muta(db, lid, Stare.IN_VALIDARE, Stare.IN_REPARATIE, componenta="G2")
            rezultate["b"] = "ok"
        except Exception as e:
            rezultate["b"] = e

    ta, tb = threading.Thread(target=a), threading.Thread(target=b)
    ta.start()
    assert a_blocat.wait(20)
    tb.start()
    tb.join(0.7)
    assert tb.is_alive(), "a doua mutare așteaptă rândul blocat, nu trece pe lângă"
    a_poate_inchide.set()
    ta.join(20)
    tb.join(20)
    assert rezultate["a"] == "ok"
    assert isinstance(rezultate["b"], productie.ConflictStare)
    assert stare(tenant, lid) == Stare.VALIDAT
    r = randuri(admin_engine, lid)
    assert [x["rezultat"] for x in r if x["in_stare"] in ("validat", "in_reparatie")] == [
        "aplicata",
        "refuzata",
    ]


def test_garda_agentiei_vede_livrabilele_tuturor_clientilor(tenant: uuid.UUID, fabrica_clienti) -> None:  # type: ignore[no-untyped-def]
    altul = fabrica_clienti()
    a, b = livrabil(tenant), livrabil(altul)
    with sesiune_agentie() as db:
        ids = {x.id for x in db.query(productie.Livrabil).all()}
    assert {a, b} <= ids
