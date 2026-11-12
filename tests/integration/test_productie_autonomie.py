"""F2.10 — nivelurile de autonomie pe bază reală: același livrabil de probă cere aprobare la L1 și trece singur la L2."""

import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app import productie
from app.conturi import PermisiuneRefuzata, Rol
from app.db import sesiune_tenant
from app.operare import motor
from app.operare.notificari import Nivel as NivelAnunt
from app.productie import Clasa, Decizie, Nivel, aprobari, autonomie
from app.productie.reguli_autonomie import esantionat
from app.productie.stari import Stare
from tests.integration import fluxuri_livrabil as proba
from tests.integration.utile_productie import AnunturiFalse, livrabil, muta, randuri, stare

pytestmark = pytest.mark.db
PC = Clasa.PUBLICARE_CONTINUT
S = Stare


def seteaza(
    tenant: uuid.UUID,
    nivel: Nivel,
    om: uuid.UUID,
    clasa: Clasa = PC,
    rol: Rol = Rol.PROPRIETAR,
    motiv: str = "client de încredere",
) -> bool:
    with sesiune_tenant(tenant, om) as db:
        return autonomie.seteaza_nivel(db, tenant, clasa, nivel, utilizator_id=om, rol=rol, motiv=motiv)


def nivelul(tenant: uuid.UUID, clasa: Clasa = PC) -> Nivel:
    with sesiune_tenant(tenant) as db:
        return autonomie.nivel(db, tenant, clasa)


def decizia(tenant: uuid.UUID, lid: uuid.UUID) -> Decizie:
    with sesiune_tenant(tenant) as db:
        liv = productie.citeste(db, lid)
        assert liv is not None
        return autonomie.decide(db, liv)


def livrabil_cu_soarta(
    tenant: uuid.UUID, esantionat_la_om: bool, rata: float = 0.15, **kw: object
) -> uuid.UUID:
    """Un livrabil nou al cărui identificator CADE (sau nu) în eșantionul de la L2: aleasă, nu ghicită."""
    clasa = Clasa(str(kw.get("clasa", PC.value)))
    for _ in range(300):
        lid = livrabil(tenant, **kw)  # type: ignore[arg-type]
        if esantionat(lid, clasa, rata) is esantionat_la_om:
            return lid
    raise AssertionError("nu am găsit un identificator potrivit")


def ruleaza(tenant: uuid.UUID, lid: uuid.UUID, eticheta: str = "a") -> str:
    job = motor.trimite(proba.proba, str(tenant), str(lid), "ok", cheie=f"autonomie-{eticheta}-{lid}")
    assert motor.asteapta_flux(job, timeout_sec=30).stare is motor.StareJob.TERMINAT
    return stare(tenant, lid).value


def parcurse(admin: Engine, lid: uuid.UUID) -> list[object]:
    return [r["in_stare"] for r in randuri(admin, lid) if r["rezultat"] == "aplicata"]


def cereri(admin: Engine, lid: uuid.UUID) -> int:
    with admin.connect() as c:
        return int(
            c.execute(text("SELECT count(*) FROM aprobari WHERE livrabil_id = :l"), {"l": lid}).scalar_one()
        )


# --- matricea și schimbarea ---------------------------------------------------------------------------------


def test_implicit_toate_cele_cinci_clase_sunt_la_l1(tenant: uuid.UUID) -> None:
    with sesiune_tenant(tenant) as db:
        m = autonomie.matrice(db, tenant)
    assert m == dict.fromkeys(Clasa, Nivel.L1) and len(m) == 5


def test_doar_proprietarul_schimba_nivelul_cu_motiv_si_audit(
    tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    for rol in (Rol.OPERATOR, Rol.ANALIST, Rol.CLIENT_TITULAR, Rol.CLIENT_APROBATOR, Rol.CLIENT_VIZITATOR):
        with pytest.raises(PermisiuneRefuzata):
            seteaza(tenant, Nivel.L2, om, rol=rol)
    assert nivelul(tenant) is Nivel.L1
    for motiv in ("", "  ", "ab"):
        with pytest.raises(autonomie.MotivLipsa):
            seteaza(tenant, Nivel.L2, om, motiv=motiv)
    assert seteaza(tenant, Nivel.L2, om, motiv="30 de livrabile fără probleme") is True
    assert nivelul(tenant) is Nivel.L2 and nivelul(tenant, Clasa.CHELTUIALA) is Nivel.L1, "doar clasa aleasă"
    assert seteaza(tenant, Nivel.L2, om) is False, "același nivel: nimic de scris"
    with admin_engine.connect() as c:
        a = c.execute(
            text(
                "SELECT utilizator_id, tenant_id, detalii FROM jurnal_audit WHERE actiune = 'autonomie.seteaza' "
                "AND obiect_id = :o"
            ),
            {"o": f"{tenant}:{PC.value}"},
        ).one()
        h = c.execute(
            text("SELECT de_la, la, tip, utilizator_id, motiv FROM autonomie_istoric WHERE tenant_id = :t"),
            {"t": tenant},
        ).all()
    assert (a.utilizator_id, a.tenant_id) == (om, tenant)
    assert a.detalii["de_la"] == 1 and a.detalii["la"] == 2 and "30 de livrabile" in a.detalii["motiv"]
    assert [tuple(r) for r in h] == [(1, 2, "setare", om, "30 de livrabile fără probleme")]


def test_nivelul_unui_client_nu_il_atinge_pe_al_altuia(
    tenant: uuid.UUID, om: uuid.UUID, fabrica_clienti: Callable[[], uuid.UUID]
) -> None:
    alt = fabrica_clienti()
    seteaza(tenant, Nivel.L3, om)
    assert nivelul(tenant) is Nivel.L3 and nivelul(alt) is Nivel.L1


def test_baza_nu_lasa_istoricul_sa_se_schimbe_si_cere_om_la_setare(tenant: uuid.UUID, om: uuid.UUID) -> None:
    seteaza(tenant, Nivel.L2, om)
    for sql in ("UPDATE autonomie_istoric SET motiv = 'x'", "DELETE FROM autonomie_istoric"):
        with pytest.raises(DBAPIError), sesiune_tenant(tenant) as db:
            db.execute(text(sql))
    with pytest.raises(DBAPIError), sesiune_tenant(tenant) as db:  # o „setare” fără om nu există
        db.execute(
            text(
                "INSERT INTO autonomie_istoric (id, tenant_id, clasa, de_la, la, tip) "
                "VALUES (gen_random_uuid(), :t, 'cheltuiala', 1, 2, 'setare')"
            ),
            {"t": tenant},
        )


# --- „Gata când”: același livrabil de probă ----------------------------------------------------------------------


def test_acelasi_livrabil_cere_aprobare_la_l1_si_trece_singur_la_l2(
    executor: None, tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    # 1) La L1 (implicit) un livrabil care nu e în niciun eșantion tot cere aprobare: fluxul se oprește la un om.
    primul = livrabil_cu_soarta(tenant, esantionat_la_om=False)
    assert decizia(tenant, primul) is Decizie.APROBARE
    # (livrabilul se produce până la „validat”; abia acolo autonomia hotărăște)
    assert ruleaza(tenant, primul) == S.ASTEAPTA_APROBARE.value
    assert cereri(admin_engine, primul) == 1
    # 2) Proprietarul urcă clasa la L2: ACELAȘI livrabil (aceeași identitate) ar trece acum singur.
    assert seteaza(tenant, Nivel.L2, om)
    assert decizia(tenant, primul) is Decizie.AUTOMAT, "același id, alt nivel, alt răspuns, determinist"
    # 3) Un livrabil de același fel, la L2, trece singur: nicio cerere, nicio așteptare, până la capăt.
    al_doilea = livrabil_cu_soarta(tenant, esantionat_la_om=False)
    assert ruleaza(tenant, al_doilea) == S.INCHIS.value
    drum = parcurse(admin_engine, al_doilea)
    assert "asteapta_aprobare" not in drum and "aprobat" in drum
    assert cereri(admin_engine, al_doilea) == 0
    aprobat = next(r for r in randuri(admin_engine, al_doilea) if r["in_stare"] == "aprobat")
    assert (aprobat["componenta"], aprobat["actor_tip"], aprobat["detalii"]) == (
        "autonomie",
        "componenta",
        {"autonomie": "automat"},
    )


def test_la_l2_eșantionul_merge_totusi_la_om(
    executor: None, tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    seteaza(tenant, Nivel.L2, om)
    ales = livrabil_cu_soarta(tenant, esantionat_la_om=True)
    assert decizia(tenant, ales) is Decizie.APROBARE
    assert ruleaza(tenant, ales) == S.ASTEAPTA_APROBARE.value and cereri(admin_engine, ales) == 1


def test_ponderea_eșantionului_se_configureaza(
    tenant: uuid.UUID, om: uuid.UUID, config: Callable[..., None]
) -> None:
    seteaza(tenant, Nivel.L2, om)
    lid = livrabil_cu_soarta(tenant, esantionat_la_om=False)
    assert decizia(tenant, lid) is Decizie.AUTOMAT
    config(autonomie_esantion_l2="1.0")
    assert decizia(tenant, lid) is Decizie.APROBARE, "rata 1: toți la om"
    config(autonomie_esantion_l2="0.0")
    assert decizia(tenant, livrabil_cu_soarta(tenant, esantionat_la_om=True)) is Decizie.AUTOMAT


def test_canalul_tiktok_ramane_la_l1_chiar_daca_clasa_e_la_l2(
    executor: None, tenant: uuid.UUID, om: uuid.UUID, config: Callable[..., None], admin_engine: Engine
) -> None:
    seteaza(tenant, Nivel.L3, om)
    tiktok = livrabil_cu_soarta(tenant, esantionat_la_om=False, canal="tiktok")
    facebook = livrabil_cu_soarta(tenant, esantionat_la_om=False, canal="facebook")
    assert decizia(tenant, tiktok) is Decizie.APROBARE and decizia(tenant, facebook) is Decizie.AUTOMAT
    assert ruleaza(tenant, tiktok) == S.ASTEAPTA_APROBARE.value
    assert ruleaza(tenant, facebook) == S.INCHIS.value
    # lista canalelor e configurare: adăugând „facebook”, și el rămâne la L1
    config(canale_consimtamant="tiktok, Facebook")
    assert (
        decizia(tenant, livrabil_cu_soarta(tenant, esantionat_la_om=False, canal="facebook"))
        is Decizie.APROBARE
    )


def test_clasele_sunt_independente(tenant: uuid.UUID, om: uuid.UUID) -> None:
    clasa_reclame = Clasa.SCHIMBARE_RECLAME
    seteaza(tenant, Nivel.L2, om, clasa=PC)
    reclama = livrabil_cu_soarta(tenant, False, rata=0.075, clasa=clasa_reclame.value)
    assert decizia(tenant, reclama) is Decizie.APROBARE, "reclamele rămân la L1 deși conținutul e la L2"
    seteaza(tenant, Nivel.L2, om, clasa=clasa_reclame)
    assert decizia(tenant, reclama) is Decizie.APROBARE, "ajustările de reclame trec singure abia de la L3"
    seteaza(tenant, Nivel.L3, om, clasa=clasa_reclame)
    assert decizia(tenant, reclama) is Decizie.AUTOMAT, "L3, în afara eșantionului de 7,5%"
    strategie = livrabil(tenant, clasa=Clasa.SCHIMBARE_STRATEGIE.value)
    seteaza(tenant, Nivel.L3, om, clasa=Clasa.SCHIMBARE_STRATEGIE)
    assert decizia(tenant, strategie) is Decizie.APROBARE, "strategia se schimbă singură doar la L4"
    seteaza(tenant, Nivel.L4, om, clasa=Clasa.SCHIMBARE_STRATEGIE)
    assert decizia(tenant, strategie) is Decizie.AUTOMAT


# --- poarta: autonomia nu se poate falsifica ---------------------------------------------------------------------


def validat(tenant: uuid.UUID, lid: uuid.UUID) -> None:
    curenta = S.PLANIFICAT
    for s in (S.BRIEFAT, S.IN_SCRIERE, S.IN_VALIDARE, S.VALIDAT):
        muta(tenant, lid, curenta, s)
        curenta = s


def test_poarta_accepta_temeiul_de_autonomie_doar_cand_decizia_este_automat(
    tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    a_trece = livrabil_cu_soarta(tenant, esantionat_la_om=False)
    la_om = livrabil_cu_soarta(tenant, esantionat_la_om=True)
    for lid in (a_trece, la_om):
        validat(tenant, lid)

    def incearca(lid: uuid.UUID) -> productie.Rezultat:
        with sesiune_tenant(tenant) as db:
            return productie.muta(
                db, lid, S.VALIDAT, S.APROBAT, componenta="autonomie", temei=productie.Temei.autonomie()
            )

    with pytest.raises(productie.TranzitieNepermisa, match="cere aprobare"):
        incearca(a_trece)  # la L1 nimic nu trece singur
    seteaza(tenant, Nivel.L2, om)
    with pytest.raises(productie.TranzitieNepermisa, match="cere aprobare"):
        incearca(la_om)  # în eșantion: la om
    assert [r["rezultat"] for r in randuri(admin_engine, la_om)][-1] == "refuzata"
    assert incearca(a_trece).aplicat and stare(tenant, a_trece) == S.APROBAT


def test_retrogradarea_scoate_dreptul_de_a_trece_singur(tenant: uuid.UUID, om: uuid.UUID) -> None:
    seteaza(tenant, Nivel.L2, om)
    lid = livrabil_cu_soarta(tenant, esantionat_la_om=False)
    validat(tenant, lid)
    with sesiune_tenant(tenant) as db:
        autonomie.retrogradeaza(db, tenant, motiv="postare cu fapt greșit", referinta="incident-7")
    with pytest.raises(productie.TranzitieNepermisa, match="cere aprobare"), sesiune_tenant(tenant) as db:
        productie.muta(
            db, lid, S.VALIDAT, S.APROBAT, componenta="autonomie", temei=productie.Temei.autonomie()
        )
    assert decizia(tenant, lid) is Decizie.APROBARE


# --- L0: produce, nu publică -----------------------------------------------------------------------------------


def test_la_l0_livrabilul_se_produce_dar_nu_merge_spre_aprobare_sau_publicare(
    executor: None, tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    seteaza(tenant, Nivel.L0, om)
    lid = livrabil(tenant)
    assert ruleaza(tenant, lid) == S.VALIDAT.value, "produs și validat, apoi parcat"
    assert decizia(tenant, lid) is Decizie.UMBRA and cereri(admin_engine, lid) == 0
    with pytest.raises(aprobari.NivelUmbra), sesiune_tenant(tenant) as db:
        aprobari.cere(db, lid)
    for la, temei in (
        (S.ASTEAPTA_APROBARE, None),
        (S.APROBAT, None),
        (S.APROBAT, productie.Temei.autonomie()),
    ):
        with pytest.raises(productie.TranzitieNepermisa), sesiune_tenant(tenant) as db:
            productie.muta(db, lid, S.VALIDAT, la, componenta="H1", temei=temei)
    assert stare(tenant, lid) == S.VALIDAT
    assert not {"aprobat", "programat", "in_publicare", "publicat"} & set(parcurse(admin_engine, lid))
    # a doua rulare a fluxului nu face nimic în plus
    assert ruleaza(tenant, lid, "b") == S.VALIDAT.value
    # când proprietarul urcă la L1, livrabilul parcat poate merge la aprobare
    seteaza(tenant, Nivel.L1, om)
    with sesiune_tenant(tenant) as db:
        assert aprobari.cere(db, lid).stare == "in_asteptare"


def test_coborarea_la_l0_oprește_si_aprobarea_unei_cereri_deja_deschise(
    tenant: uuid.UUID, om: uuid.UUID
) -> None:
    lid = livrabil(tenant)
    validat(tenant, lid)
    with sesiune_tenant(tenant) as db:
        ap = aprobari.cere(db, lid)
    seteaza(tenant, Nivel.L0, om)
    with pytest.raises(aprobari.NivelUmbra), sesiune_tenant(tenant, om) as db:
        aprobari.decide(db, ap.id, productie.Hotarare.APROBAT, utilizator_id=om, rol=Rol.OPERATOR)
    assert stare(tenant, lid) == S.ASTEAPTA_APROBARE


# --- retrogradarea automată ------------------------------------------------------------------------------------


def test_incidentul_critic_coboara_cu_un_nivel_pe_o_clasa_sau_pe_toate(
    tenant: uuid.UUID, om: uuid.UUID, anunturi: AnunturiFalse, admin_engine: Engine
) -> None:
    seteaza(tenant, Nivel.L3, om, clasa=PC)
    seteaza(tenant, Nivel.L2, om, clasa=Clasa.RASPUNS_INBOX)
    anunturi.trimise.clear()
    with sesiune_tenant(tenant) as db:
        schimbate = autonomie.retrogradeaza(
            db, tenant, clasa=PC, motiv="postare cu fapt greșit", referinta="inc-1"
        )
    assert [(s.clasa, s.de_la, s.la) for s in schimbate] == [(PC, Nivel.L3, Nivel.L2)]
    assert nivelul(tenant) is Nivel.L2 and nivelul(tenant, Clasa.RASPUNS_INBOX) is Nivel.L2
    assert anunturi.nivele() == [NivelAnunt.IMPORTANT]
    with sesiune_tenant(tenant) as db:  # toate clasele: cele la L1 → L0, cele la L2 → L1
        toate = autonomie.retrogradeaza(db, tenant, motiv="al doilea incident")
    assert {s.clasa: (s.de_la, s.la) for s in toate} == {
        PC: (Nivel.L2, Nivel.L1),
        Clasa.RASPUNS_INBOX: (Nivel.L2, Nivel.L1),
        Clasa.SCHIMBARE_RECLAME: (Nivel.L1, Nivel.L0),
        Clasa.SCHIMBARE_STRATEGIE: (Nivel.L1, Nivel.L0),
        Clasa.CHELTUIALA: (Nivel.L1, Nivel.L0),
    }
    with sesiune_tenant(tenant) as db:  # podeaua e L0: o clasă la L0 nu mai coboară
        assert [s.clasa for s in autonomie.retrogradeaza(db, tenant, motiv="încă unul")] == [
            PC,
            Clasa.RASPUNS_INBOX,
        ]
        assert autonomie.retrogradeaza(db, tenant, clasa=Clasa.CHELTUIALA, motiv="x") == []
    with admin_engine.connect() as c:
        h = c.execute(
            text(
                "SELECT tip, utilizator_id, referinta FROM autonomie_istoric WHERE tenant_id = :t AND tip = 'retrogradare' "
                "ORDER BY creat_la LIMIT 1"
            ),
            {"t": tenant},
        ).one()
        a = c.execute(
            text(
                "SELECT actor_tip, utilizator_id FROM jurnal_audit WHERE actiune = 'autonomie.retrogradata' AND obiect_id = :o"
            ),
            {"o": f"{tenant}:{PC.value}"},
        ).first()
    assert tuple(h) == ("retrogradare", None, "inc-1")
    assert a is not None and (a.actor_tip, a.utilizator_id) == ("sistem", None)
