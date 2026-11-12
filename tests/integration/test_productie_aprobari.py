"""F2.8 — cererile de aprobare pe bază reală: creare, decizie legată de versiune, expirare, reamintiri, concurență."""

import datetime as dt
import threading
import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app import productie
from app.config import get_settings
from app.conturi import Rol
from app.db import sesiune_agentie, sesiune_tenant
from app.ids import new_id
from app.operare.notificari import Nivel
from app.productie import aprobari
from app.productie.reguli_aprobare import Decident, Hotarare
from app.productie.stari import Stare
from tests.integration.utile_productie import AnunturiFalse, livrabil, muta, randuri, stare

pytestmark = pytest.mark.db
S = Stare
ACUM = dt.datetime.now(dt.UTC)


@pytest.fixture(autouse=True)
def _fara_cereri_ramase(admin_engine: Engine) -> None:
    """Joburile programate și expirarea citesc cererile tuturor clienților: cele rămase de la alte teste se închid."""
    with admin_engine.begin() as c:
        c.execute(text("UPDATE aprobari SET stare = 'anulat', decis_la = now() WHERE stare = 'in_asteptare'"))


def validat(tenant: uuid.UUID, **kw: object) -> uuid.UUID:
    lid = livrabil(tenant, **kw)  # type: ignore[arg-type]
    curenta = S.PLANIFICAT
    for s in (S.BRIEFAT, S.IN_SCRIERE, S.IN_VALIDARE, S.VALIDAT):
        muta(tenant, lid, curenta, s)
        curenta = s
    return lid


def cere(tenant: uuid.UUID, lid: uuid.UUID, **kw: object) -> productie.Aprobare:
    with sesiune_tenant(tenant) as db:
        return aprobari.cere(db, lid, **kw)  # type: ignore[arg-type]


def decide(
    tenant: uuid.UUID,
    ap_id: uuid.UUID,
    hotarare: Hotarare,
    om: uuid.UUID,
    rol: Rol = Rol.OPERATOR,
    **kw: object,
) -> aprobari.RezultatDecizie:
    with sesiune_tenant(tenant, om) as db:
        return aprobari.decide(db, ap_id, hotarare, utilizator_id=om, rol=rol, **kw)  # type: ignore[arg-type]


def citeste(tenant: uuid.UUID, ap_id: uuid.UUID) -> productie.Aprobare:
    with sesiune_tenant(tenant) as db:
        a = aprobari.citeste(db, ap_id)
        assert a is not None
        return a


def stari_istoric(admin: Engine, lid: uuid.UUID) -> list[object]:
    return [r["in_stare"] for r in randuri(admin, lid) if r["rezultat"] == "aplicata"]


def audit(admin: Engine, actiune: str, ap_id: uuid.UUID) -> list[dict[str, object]]:
    with admin.connect() as c:
        return [
            dict(r._mapping)
            for r in c.execute(
                text(
                    "SELECT utilizator_id, tenant_id, actor_tip, detalii FROM jurnal_audit "
                    "WHERE actiune = :a AND obiect_id = :o ORDER BY id"
                ),
                {"a": actiune, "o": str(ap_id)},
            )
        ]


# --- creare ----------------------------------------------------------------------------------------------------


def test_cererea_se_leaga_de_versiunea_curenta_cu_termen_si_reamintire(
    tenant: uuid.UUID, anunturi: AnunturiFalse, admin_engine: Engine
) -> None:
    lid = validat(tenant)
    ap = cere(tenant, lid, acum=ACUM)
    s = get_settings()
    assert (ap.stare, ap.versiune, ap.decident, ap.clasa_actiune) == (
        "in_asteptare",
        1,
        "operator",
        "publicare_continut",
    )
    assert ap.termen_la == ACUM + dt.timedelta(hours=s.aprobare_termen_ore)
    assert ap.reamintire_la == ap.termen_la - dt.timedelta(hours=s.aprobare_reamintire_ore)
    assert (s.aprobare_termen_ore, s.aprobare_reamintire_ore) == (48, 24)
    assert stare(tenant, lid) == S.ASTEAPTA_APROBARE
    [a] = audit(admin_engine, "aprobare.creata", ap.id)
    assert a["tenant_id"] == tenant and a["actor_tip"] == "sistem" and a["detalii"]["versiune"] == 1  # type: ignore[index]
    assert anunturi.titluri() == ["Aprobare nouă în așteptare"] and anunturi.nivele() == [Nivel.IMPORTANT]
    assert anunturi.trimise[0][3] == "/aprobari"


def test_cererea_anulata_odata_cu_tranzactia_nu_anunta_nimic(
    tenant: uuid.UUID, anunturi: AnunturiFalse
) -> None:
    lid = validat(tenant)

    class Ratat(Exception):
        pass

    with pytest.raises(Ratat), sesiune_tenant(tenant) as db:
        aprobari.cere(db, lid)
        raise Ratat
    assert stare(tenant, lid) == S.VALIDAT and anunturi.trimise == []


def test_termenul_nu_depaseste_slotul_livrabilului(tenant: uuid.UUID) -> None:
    slot = ACUM + dt.timedelta(hours=10)
    lid = validat(tenant, termen_la=slot)
    ap = cere(tenant, lid, acum=ACUM)
    assert ap.termen_la == slot and ap.reamintire_la == ACUM + dt.timedelta(hours=5)


def test_slotul_trecut_nu_permite_cererea_si_nu_scrie_nimic(tenant: uuid.UUID) -> None:
    lid = validat(tenant, termen_la=ACUM - dt.timedelta(minutes=1))
    with pytest.raises(aprobari.TermenTrecut), sesiune_tenant(tenant) as db:
        aprobari.cere(db, lid, acum=ACUM)
    assert stare(tenant, lid) == S.VALIDAT
    muta(tenant, lid, S.VALIDAT, S.EXPIRAT)  # apelantul îl expiră: slotul a trecut fără aprobare


def test_cererea_se_face_doar_pentru_un_livrabil_validat_si_o_singura_data(tenant: uuid.UUID) -> None:
    lid = livrabil(tenant)
    with pytest.raises(aprobari.NuSeCereAprobare), sesiune_tenant(tenant) as db:
        aprobari.cere(db, lid)
    lid = validat(tenant)
    cere(tenant, lid)
    with pytest.raises(aprobari.NuSeCereAprobare, match="deja"), sesiune_tenant(tenant) as db:
        aprobari.cere(db, lid)


# --- decizia ---------------------------------------------------------------------------------------------------


def test_operatorul_aproba_si_se_vede_cine_cand_si_ce_versiune(
    tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    lid = validat(tenant)
    ap = cere(tenant, lid)
    r = decide(tenant, ap.id, Hotarare.APROBAT, om, versiune=1)
    assert r.aplicat and r.stare_livrabil == S.APROBAT
    a = citeste(tenant, ap.id)
    assert (a.stare, a.decis_de, a.versiune) == ("aprobat", om, 1) and a.decis_la is not None
    assert stare(tenant, lid) == S.APROBAT
    ultim = randuri(admin_engine, lid)[-1]
    assert (ultim["actor_tip"], ultim["componenta"], ultim["in_stare"]) == ("utilizator", "L2", "aprobat")
    [au] = audit(admin_engine, "aprobare.aprobata", ap.id)
    assert (au["utilizator_id"], au["tenant_id"]) == (om, tenant) and au["detalii"]["versiune"] == 1  # type: ignore[index]


def test_respingerea_cere_motiv_si_il_pastreaza(
    tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    lid = validat(tenant)
    ap = cere(tenant, lid)
    for motiv in ("", "  ", "ab"):
        with pytest.raises(aprobari.MotivLipsa):
            decide(tenant, ap.id, Hotarare.RESPINS, om, motiv=motiv)
    with pytest.raises(aprobari.MotivLipsa, match="standard"):
        decide(tenant, ap.id, Hotarare.RESPINS, om, motiv="nu se potrivește", motiv_standard="inventat")
    assert stare(tenant, lid) == S.ASTEAPTA_APROBARE
    r = decide(tenant, ap.id, Hotarare.RESPINS, om, motiv="hook slab, rescrie", motiv_standard="hook_slab")
    assert r.aplicat and stare(tenant, lid) == S.RESPINS
    a = citeste(tenant, ap.id)
    assert (a.stare, a.motiv, a.motiv_cod, a.decis_de) == ("respins", "hook slab, rescrie", "hook_slab", om)
    [au] = audit(admin_engine, "aprobare.respinsa", ap.id)
    assert au["detalii"]["motiv"] == "hook slab, rescrie" and au["detalii"]["motiv_standard"] == "hook_slab"  # type: ignore[index]


def test_cine_poate_decide_depinde_de_decident(tenant: uuid.UUID, om: uuid.UUID) -> None:
    pentru_operator = cere(tenant, validat(tenant))
    pentru_client = cere(tenant, validat(tenant), decident=Decident.CLIENT)
    for rol in (Rol.ANALIST, Rol.CLIENT_TITULAR, Rol.CLIENT_APROBATOR, Rol.CLIENT_VIZITATOR):
        with pytest.raises(aprobari.FaraDrept):
            decide(tenant, pentru_operator.id, Hotarare.APROBAT, om, rol=rol)
    for rol in (Rol.PROPRIETAR, Rol.OPERATOR, Rol.ANALIST, Rol.CLIENT_VIZITATOR):
        with pytest.raises(aprobari.FaraDrept):
            decide(tenant, pentru_client.id, Hotarare.APROBAT, om, rol=rol)
    assert citeste(tenant, pentru_operator.id).stare == "in_asteptare"
    assert decide(tenant, pentru_client.id, Hotarare.APROBAT, om, rol=Rol.CLIENT_APROBATOR).aplicat
    assert decide(tenant, pentru_operator.id, Hotarare.APROBAT, om, rol=Rol.PROPRIETAR).aplicat


def test_o_cerere_decisa_nu_se_mai_decide(tenant: uuid.UUID, om: uuid.UUID) -> None:
    ap = cere(tenant, validat(tenant))
    decide(tenant, ap.id, Hotarare.APROBAT, om)
    for h in Hotarare:
        with pytest.raises(aprobari.DejaDecisa, match="aprobat"):
            decide(tenant, ap.id, h, om, motiv="încă o dată")
    with pytest.raises(aprobari.AprobareInexistenta):
        decide(tenant, uuid.uuid4(), Hotarare.APROBAT, om)


# --- legătura cu versiunea ---------------------------------------------------------------------------------------


def test_o_aprobare_pe_versiunea_veche_nu_aproba_versiunea_noua(
    tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    lid = validat(tenant)
    veche = cere(tenant, lid)
    with sesiune_tenant(tenant, om) as db:
        assert productie.versiune_noua(db, lid, componenta="E1", utilizator_id=om, motiv="editat de om") == 2
    # cererea veche s-a anulat; una nouă, pentru versiunea 2, a preluat decidentul și termenul
    assert citeste(tenant, veche.id).stare == "anulat"
    with sesiune_tenant(tenant) as db:
        noua = aprobari.cerere_activa(db, lid)
        assert noua is not None and noua.id != veche.id
        assert (noua.versiune, noua.decident, noua.termen_la) == (2, "operator", veche.termen_la)
    assert stare(tenant, lid) == S.ASTEAPTA_APROBARE
    [anulata] = audit(admin_engine, "aprobare.anulata", veche.id)
    assert anulata["detalii"]["versiune_veche"] == 1 and anulata["detalii"]["versiune_noua"] == 2  # type: ignore[index]
    # decizia pe cererea veche nu mai poate aproba nimic
    with pytest.raises(aprobari.DejaDecisa, match="anulat"):
        decide(tenant, veche.id, Hotarare.APROBAT, om, versiune=1)
    assert stare(tenant, lid) == S.ASTEAPTA_APROBARE
    # omul care a văzut încă versiunea 1 nu poate aproba cererea nouă
    with pytest.raises(aprobari.VersiuneVeche):
        decide(tenant, noua.id, Hotarare.APROBAT, om, versiune=1)
    assert stare(tenant, lid) == S.ASTEAPTA_APROBARE
    assert decide(tenant, noua.id, Hotarare.APROBAT, om, versiune=2).aplicat


def test_poarta_refuza_o_aprobare_de_versiune_veche_chiar_daca_exista_in_baza(
    tenant: uuid.UUID, admin_engine: Engine
) -> None:
    """Chiar dacă cineva a aprobat versiunea 1, mutarea livrabilului aflat la versiunea 2 nu o poate invoca."""
    lid = validat(tenant)
    cere(tenant, lid)
    with sesiune_tenant(tenant) as db:
        productie.versiune_noua(db, lid, componenta="E1")
    veche_aprobata = new_id()
    with admin_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO aprobari (id, tenant_id, livrabil_id, versiune, clasa_actiune, decident, stare, "
                "termen_la, reamintire_la, decis_de, decis_la) "
                "SELECT :i, tenant_id, id, 1, clasa_actiune, 'operator', 'aprobat', now() + interval '1 day', "
                "now(), (SELECT id FROM utilizatori LIMIT 1), now() FROM livrabile WHERE id = :l"
            ),
            {"i": veche_aprobata, "l": lid},
        )
    with pytest.raises(productie.TranzitieNepermisa, match="versiunea 1") as e, sesiune_tenant(tenant) as db:
        productie.muta(
            db,
            lid,
            S.ASTEAPTA_APROBARE,
            S.APROBAT,
            componenta="H1",
            temei=productie.Temei.aprobare(veche_aprobata),
        )
    assert e.value.cod == "fara_temei" and stare(tenant, lid) == S.ASTEAPTA_APROBARE
    assert randuri(admin_engine, lid)[-1]["rezultat"] == "refuzata"


def test_versiune_noua_la_un_livrabil_validat_fara_cerere_nu_deschide_nimic(tenant: uuid.UUID) -> None:
    lid = validat(tenant)
    with sesiune_tenant(tenant) as db:
        assert productie.versiune_noua(db, lid, componenta="E1") == 2
        assert aprobari.cerere_activa(db, lid) is None


# --- porțile: fără aprobare automată -----------------------------------------------------------------------------


def test_nicio_mutare_prin_poarta_fara_temei(tenant: uuid.UUID, admin_engine: Engine) -> None:
    lid = validat(tenant)
    for la in (S.APROBAT, S.ASTEAPTA_APROBARE):
        with (
            pytest.raises(productie.TranzitieNepermisa, match="fără aprobare automată") as e,
            sesiune_tenant(tenant) as db,
        ):
            productie.muta(db, lid, S.VALIDAT, la, componenta="H1")
        assert e.value.cod == "fara_temei"
    ap = cere(tenant, lid)
    for la in (S.APROBAT, S.RESPINS, S.EXPIRAT):
        with pytest.raises(productie.TranzitieNepermisa), sesiune_tenant(tenant) as db:
            productie.muta(db, lid, S.ASTEAPTA_APROBARE, la, componenta="H1")
        # nici cu un temei care nu se potrivește stării (cererea e încă „în așteptare")
        with pytest.raises(productie.TranzitieNepermisa), sesiune_tenant(tenant) as db:
            productie.muta(
                db, lid, S.ASTEAPTA_APROBARE, la, componenta="H1", temei=productie.Temei.aprobare(ap.id)
            )
    with pytest.raises(productie.TranzitieNepermisa, match="autonomie"), sesiune_tenant(tenant) as db:
        productie.muta(
            db, lid, S.ASTEAPTA_APROBARE, S.APROBAT, componenta="H1", temei=productie.Temei.autonomie()
        )
    assert stare(tenant, lid) == S.ASTEAPTA_APROBARE
    refuzuri = [r for r in randuri(admin_engine, lid) if r["rezultat"] == "refuzata"]
    assert len(refuzuri) == 2 + 3 + 3 + 1


def test_temeiul_unui_alt_livrabil_nu_deschide_poarta(tenant: uuid.UUID, om: uuid.UUID) -> None:
    unu, altul = validat(tenant), validat(tenant)
    ap_unu, ap_altul = cere(tenant, unu), cere(tenant, altul)
    decide(tenant, ap_altul.id, Hotarare.APROBAT, om)
    with pytest.raises(productie.TranzitieNepermisa, match="nu aparține"), sesiune_tenant(tenant) as db:
        productie.muta(
            db,
            unu,
            S.ASTEAPTA_APROBARE,
            S.APROBAT,
            componenta="H1",
            temei=productie.Temei.aprobare(ap_altul.id),
        )
    assert stare(tenant, unu) == S.ASTEAPTA_APROBARE and citeste(tenant, ap_unu.id).stare == "in_asteptare"


# --- expirarea: „Gata când” ------------------------------------------------------------------------------------


def test_aprobarea_neprimita_la_timp_duce_la_expirat_nu_la_publicare(
    tenant: uuid.UUID, om: uuid.UUID, anunturi: AnunturiFalse, admin_engine: Engine
) -> None:
    lid = validat(tenant)
    trecut = ACUM - dt.timedelta(hours=49)  # cererea s-a făcut acum 49 de ore, termenul era de 48
    ap = cere(tenant, lid, acum=trecut)
    # înainte de termen nu se atinge nimic
    with sesiune_agentie() as db:
        assert aprobari.expira_restante(db, acum=trecut + dt.timedelta(hours=47)) == []
    assert stare(tenant, lid) == S.ASTEAPTA_APROBARE
    anunturi.trimise.clear()
    with sesiune_agentie() as db:
        assert aprobari.expira_restante(db, acum=ACUM) == [ap.id]
    a = citeste(tenant, ap.id)
    assert a.stare == "expirat" and a.decis_de is None and a.decis_la is not None
    assert stare(tenant, lid) == S.EXPIRAT
    # niciodată aprobat și niciodată pe drumul spre publicare
    parcurse = stari_istoric(admin_engine, lid)
    assert parcurse[-2:] == ["asteapta_aprobare", "expirat"]
    assert not {"aprobat", "programat", "in_publicare", "publicat"} & set(parcurse)
    [au] = audit(admin_engine, "aprobare.expirata", ap.id)
    assert au["actor_tip"] == "sistem" and au["tenant_id"] == tenant
    assert anunturi.titluri() == ["Aprobare expirată"]
    # o decizie întârziată nu mai poate nimic; livrabilul nu poate ajunge la aprobat din expirat
    with pytest.raises(aprobari.DejaDecisa, match="expirat"):
        decide(tenant, ap.id, Hotarare.APROBAT, om)
    with pytest.raises(productie.TranzitieNepermisa), sesiune_tenant(tenant) as db:
        productie.muta(db, lid, S.EXPIRAT, S.APROBAT, componenta="H1", temei=productie.Temei.aprobare(ap.id))
    # expirarea e idempotentă; livrabilul expirat se reprogramează (7.3)
    with sesiune_agentie() as db:
        assert aprobari.expira_restante(db, acum=ACUM) == []
    assert muta(tenant, lid, S.EXPIRAT, S.PLANIFICAT, motiv="reprogramat").aplicat


def test_decizia_de_dupa_termen_expira_cererea_in_loc_sa_o_aprobe(tenant: uuid.UUID, om: uuid.UUID) -> None:
    lid = validat(tenant)
    ap = cere(tenant, lid, acum=ACUM)
    dupa = ap.termen_la + dt.timedelta(seconds=1)
    r = decide(tenant, ap.id, Hotarare.APROBAT, om, acum=dupa)
    assert not r.aplicat and r.stare_livrabil == S.EXPIRAT
    assert citeste(tenant, ap.id).stare == "expirat" and stare(tenant, lid) == S.EXPIRAT


def test_o_cerere_expirata_a_unui_client_nu_atinge_cererea_altuia(
    tenant: uuid.UUID,
    fabrica_clienti,  # type: ignore[no-untyped-def]
) -> None:
    alt = fabrica_clienti()
    a, b = validat(tenant), validat(alt)
    cere(tenant, a, acum=ACUM - dt.timedelta(hours=60))
    ap_b = cere(alt, b, acum=ACUM)
    with sesiune_agentie() as db:
        assert aprobari.expira_restante(db, acum=ACUM) != []
    assert stare(tenant, a) == S.EXPIRAT and stare(alt, b) == S.ASTEAPTA_APROBARE
    assert citeste(alt, ap_b.id).stare == "in_asteptare"


# --- reamintiri ----------------------------------------------------------------------------------------------


def test_reamintirea_vine_o_data_inainte_de_termen(tenant: uuid.UUID, anunturi: AnunturiFalse) -> None:
    lid = validat(tenant)
    ap = cere(tenant, lid, acum=ACUM)
    anunturi.trimise.clear()
    with sesiune_agentie() as db:
        assert aprobari.trimite_reamintiri(db, acum=ap.reamintire_la - dt.timedelta(minutes=1)) == []
    assert anunturi.trimise == []
    with sesiune_agentie() as db:
        assert aprobari.trimite_reamintiri(db, acum=ap.reamintire_la + dt.timedelta(minutes=1)) == [ap.id]
    assert anunturi.titluri() == ["Reamintire: aprobare în așteptare"] and anunturi.nivele() == [
        Nivel.IMPORTANT
    ]
    with sesiune_agentie() as db:  # a doua oară nu mai trimite
        assert aprobari.trimite_reamintiri(db, acum=ap.reamintire_la + dt.timedelta(minutes=2)) == []
    assert len(anunturi.trimise) == 1
    assert citeste(tenant, ap.id).reamintit_la is not None


def test_dupa_termen_nu_se_mai_reamintește(tenant: uuid.UUID, anunturi: AnunturiFalse) -> None:
    ap = cere(tenant, validat(tenant), acum=ACUM)
    anunturi.trimise.clear()
    with sesiune_agentie() as db:
        assert aprobari.trimite_reamintiri(db, acum=ap.termen_la + dt.timedelta(minutes=1)) == []


# --- concurență ----------------------------------------------------------------------------------------------


def test_doua_decizii_simultane_pe_aceeasi_cerere_reusesc_o_singura_data(
    tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    lid = validat(tenant)
    ap = cere(tenant, lid)
    a_blocat, a_poate_inchide = threading.Event(), threading.Event()
    rezultate: dict[str, object] = {}

    def a() -> None:
        try:
            with sesiune_tenant(tenant, om) as db:
                aprobari.decide(db, ap.id, Hotarare.APROBAT, utilizator_id=om, rol=Rol.OPERATOR)
                a_blocat.set()
                assert a_poate_inchide.wait(20)
            rezultate["a"] = "ok"
        except Exception as e:
            rezultate["a"] = e

    def b() -> None:
        try:
            with sesiune_tenant(tenant, om) as db:
                aprobari.decide(
                    db, ap.id, Hotarare.RESPINS, utilizator_id=om, rol=Rol.OPERATOR, motiv="nu-mi place"
                )
            rezultate["b"] = "ok"
        except Exception as e:
            rezultate["b"] = e

    ta, tb = threading.Thread(target=a), threading.Thread(target=b)
    ta.start()
    assert a_blocat.wait(20)
    tb.start()
    tb.join(0.7)
    assert tb.is_alive(), "a doua decizie așteaptă, nu trece pe lângă"
    a_poate_inchide.set()
    ta.join(20)
    tb.join(20)
    assert rezultate["a"] == "ok" and isinstance(rezultate["b"], aprobari.DejaDecisa)
    assert citeste(tenant, ap.id).stare == "aprobat" and stare(tenant, lid) == S.APROBAT
    iesiri = [r for r in randuri(admin_engine, lid) if r["din"] == "asteapta_aprobare"]
    assert [r["in_stare"] for r in iesiri] == ["aprobat"], "o singură mutare a ieșit din „așteaptă aprobare”"


def test_expirarea_si_decizia_simultane_dau_un_singur_rezultat(tenant: uuid.UUID, om: uuid.UUID) -> None:
    lid = validat(tenant)
    ap = cere(tenant, lid, acum=ACUM - dt.timedelta(hours=60))  # termenul a trecut
    a_blocat, a_poate_inchide = threading.Event(), threading.Event()
    rezultate: dict[str, object] = {}

    def expirare() -> None:
        with sesiune_agentie() as db:
            rezultate["expirate"] = aprobari.expira_restante(db, acum=ACUM)
            a_blocat.set()
            assert a_poate_inchide.wait(20)

    def decizie() -> None:
        try:
            with sesiune_tenant(tenant, om) as db:
                rezultate["decizie"] = aprobari.decide(
                    db, ap.id, Hotarare.APROBAT, utilizator_id=om, rol=Rol.OPERATOR, acum=ACUM
                )
        except Exception as e:
            rezultate["decizie"] = e

    te, td = threading.Thread(target=expirare), threading.Thread(target=decizie)
    te.start()
    assert a_blocat.wait(20)
    td.start()
    td.join(0.7)
    assert td.is_alive()
    a_poate_inchide.set()
    te.join(20)
    td.join(20)
    assert rezultate["expirate"] == [ap.id]
    assert isinstance(rezultate["decizie"], aprobari.DejaDecisa)
    assert citeste(tenant, ap.id).stare == "expirat" and stare(tenant, lid) == S.EXPIRAT


# --- gărzile din bază --------------------------------------------------------------------------------------------


def test_baza_nu_lasa_o_decizie_sa_se_schimbe_si_cere_o_singura_cerere_in_asteptare(
    tenant: uuid.UUID, om: uuid.UUID
) -> None:
    lid = validat(tenant)
    ap = cere(tenant, lid)
    # a doua cerere în așteptare pentru același livrabil
    with pytest.raises(DBAPIError), sesiune_tenant(tenant) as db:
        db.execute(
            text(
                "INSERT INTO aprobari (id, tenant_id, livrabil_id, versiune, clasa_actiune, decident, termen_la, "
                "reamintire_la) VALUES (:i, :t, :l, 1, 'publicare_continut', 'operator', now(), now())"
            ),
            {"i": new_id(), "t": tenant, "l": lid},
        )
    decide(tenant, ap.id, Hotarare.APROBAT, om)
    for sql in (
        "UPDATE aprobari SET stare = 'respins', motiv = 'schimbat' WHERE id = :i",
        "UPDATE aprobari SET stare = 'in_asteptare', decis_la = NULL, decis_de = NULL WHERE id = :i",
        "DELETE FROM aprobari WHERE id = :i",
    ):
        with pytest.raises(DBAPIError), sesiune_tenant(tenant) as db:
            db.execute(text(sql), {"i": ap.id})
    assert citeste(tenant, ap.id).stare == "aprobat"
    with pytest.raises(DBAPIError):  # versiunea unei cereri în așteptare nu se schimbă
        altul = cere(tenant, validat(tenant))
        with sesiune_tenant(tenant) as db:
            db.execute(text("UPDATE aprobari SET versiune = 9 WHERE id = :i"), {"i": altul.id})
