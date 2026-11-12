"""F2.5 — executorul de efecte externe: outbox, chei de idempotență, verificare înainte de reîncercare, opriri,
poarta de stare, clasificarea erorilor. Conectorul este FALS (`tests/conector_fals.py`, SIMULAT)."""

import threading
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from app import productie
from app.connectors import registru
from app.connectors.contract import EfectDeTrimis
from app.db import sesiune_agentie, sesiune_tenant
from app.operare import coada_erori, efecte, motor, opriri
from app.operare.efecte import servicii
from app.operare.notificari import Nivel
from app.operare.opriri import Oprire
from app.productie.stari import Stare
from tests.conector_fals import ConectorFals
from tests.integration.utile_productie import (
    AnunturiFalse,
    livrabil,
    livrabil_in_publicare,
    livrabil_programat,
    muta,
    stare,
)

pytestmark = pytest.mark.db


@pytest.fixture
def platforma(tmp_path: Path) -> Iterator[ConectorFals]:
    """SIMULAT: platforma fală, înregistrată pe canalul `fals`."""
    registru.uita_tot()
    fals = ConectorFals(tmp_path)
    registru.inregistreaza("fals", fals)
    yield fals
    registru.uita_tot()


def cere(tenant: uuid.UUID, lid: uuid.UUID, **kw: object) -> efecte.Cerere:
    with sesiune_tenant(tenant) as db:
        return efecte.cere(db, lid, porneste=bool(kw.pop("porneste", False)), **kw)  # type: ignore[arg-type]


def efect(tenant: uuid.UUID, efect_id: uuid.UUID) -> efecte.Efect:
    with sesiune_tenant(tenant) as db:
        e = efecte.citeste(db, efect_id)
        assert e is not None
        return e


def incearca(tenant: uuid.UUID, efect_id: uuid.UUID) -> str:
    return efecte.incearca_efect(tenant, efect_id)


def audit_efect(admin: Engine, efect_id: uuid.UUID, actiune: str) -> int:
    with admin.connect() as c:
        return c.execute(
            text("SELECT count(*) FROM jurnal_audit WHERE actiune = :a AND obiect_id = :o"),
            {"a": actiune, "o": str(efect_id)},
        ).scalar_one()


# --- Gata când: același efect de două ori = o singură execuție -----------------------------------------------------


def test_acelasi_efect_cerut_de_doua_ori_se_executa_o_singura_data(
    tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    prima = cere(tenant, lid, payload={"continut_id": "c1"})
    a_doua = cere(tenant, lid, payload={"continut_id": "c1"})
    assert prima.nou and not a_doua.nou and prima.efect.id == a_doua.efect.id
    assert prima.efect.cheia == f"{tenant}:{lid}:fals:v1:publicare", (
        "client + livrabil + canal + versiune + tip"
    )
    with sesiune_tenant(tenant) as db:
        assert len(efecte.ale_livrabilului(db, lid)) == 1

    assert incearca(tenant, prima.efect.id) == "trimis"
    assert incearca(tenant, a_doua.efect.id) == "trimis", "a doua execuție întoarce rezultatul primei"
    assert len(platforma.postari()) == 1 and platforma.apeluri("trimite") == [
        f"trimite {prima.efect.cheia} ok"
    ]
    e = efect(tenant, prima.efect.id)
    assert (e.stare, e.id_extern, e.incercari) == ("trimis", "fals-1", 1)
    assert e.link and e.link.startswith("https://")


def test_o_versiune_noua_este_alt_efect(tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals) -> None:
    lid = livrabil_in_publicare(tenant, om)
    e1 = cere(tenant, lid).efect
    assert e1.cheia.endswith(":v1:publicare")
    assert efecte.cheia(tenant, lid, "fals", 2, efecte.Tip.PUBLICARE).endswith(":v2:publicare")


def test_cererea_a_doua_in_paralel_da_un_singur_rand(
    tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    bariera = threading.Barrier(2)
    rezultate: list[efecte.Cerere] = []

    def cerere() -> None:
        with sesiune_tenant(tenant) as db:
            bariera.wait(timeout=10)
            rezultate.append(efecte.cere(db, lid, porneste=False))

    fire = [threading.Thread(target=cerere) for _ in range(2)]
    [f.start() for f in fire]
    [f.join(timeout=30) for f in fire]
    assert len(rezultate) == 2 and rezultate[0].efect.id == rezultate[1].efect.id
    assert sorted(r.nou for r in rezultate) == [False, True]


# --- outbox tranzacțional și poarta de stare ----------------------------------------------------------------------


def test_efectul_se_inregistreaza_in_aceeasi_tranzactie_cu_mutarea(
    tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals
) -> None:
    lid = livrabil_programat(tenant, om)
    with pytest.raises(RuntimeError), sesiune_tenant(tenant) as db:
        productie.muta(db, lid, Stare.PROGRAMAT, Stare.IN_PUBLICARE, componenta="B4")
        efecte.cere(db, lid, porneste=False)
        raise RuntimeError("tranzacția apelantului se anulează")
    assert stare(tenant, lid) == Stare.PROGRAMAT
    with sesiune_tenant(tenant) as db:
        assert efecte.ale_livrabilului(db, lid) == [], "nici mutarea, nici efectul"
    with sesiune_tenant(tenant) as db:
        productie.muta(db, lid, Stare.PROGRAMAT, Stare.IN_PUBLICARE, componenta="B4")
        efecte.cere(db, lid, porneste=False)
    assert stare(tenant, lid) == Stare.IN_PUBLICARE
    with sesiune_tenant(tenant) as db:
        assert len(efecte.ale_livrabilului(db, lid)) == 1, "ambele, în același commit"


def test_poarta_de_stare_efectul_cere_un_livrabil_in_publicare(
    tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals
) -> None:
    lid = livrabil(tenant, canal="fals")  # `planificat`: nu a ajuns legitim în publicare
    with pytest.raises(efecte.EfectRefuzat, match="În publicare"), sesiune_tenant(tenant) as db:
        efecte.cere(db, lid, porneste=False)
    with sesiune_tenant(tenant) as db:
        assert efecte.ale_livrabilului(db, lid) == []
    assert platforma.apeluri() == []


def test_mutarea_anulata_nu_lasa_efect_in_urma(
    tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    with pytest.raises(RuntimeError), sesiune_tenant(tenant) as db:
        efecte.cere(db, lid, porneste=False)
        raise RuntimeError("tranzacția apelantului se anulează")
    with sesiune_tenant(tenant) as db:
        assert efecte.ale_livrabilului(db, lid) == []


@pytest.mark.parametrize("cheie", ["token", "parola", "secret_api", "api_key", "authorization_jeton"])
def test_payload_nu_poarta_secrete(
    tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals, cheie: str
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    with pytest.raises(efecte.EfectRefuzat, match="secret"), sesiune_tenant(tenant) as db:
        efecte.cere(db, lid, payload={"anexe": [{cheie: "x"}]}, porneste=False)


# --- verificarea la platformă înainte de reîncercare -------------------------------------------------------------


def test_conectorul_executa_apoi_raspunde_cu_eroare_executorul_verifica_si_nu_retrimite(
    tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals, admin_engine: Engine
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    e = cere(tenant, lid).efect
    platforma.scenariu(trimite=["reuseste_dar_eroare"])

    with pytest.raises(motor.EroareTemporara):
        incearca(tenant, e.id)
    assert efect(tenant, e.id).stare == "esuat_temporar" and len(platforma.postari()) == 1

    assert incearca(tenant, e.id) == "trimis"
    assert len(platforma.postari()) == 1, "nicio publicare dublă"
    assert [a.split()[0] for a in platforma.apeluri()] == ["trimite", "verifica"], (
        "nu a mai trimis a doua oară"
    )
    final = efect(tenant, e.id)
    assert (final.stare, final.id_extern) == ("trimis", "fals-1")
    assert stare(tenant, lid) == Stare.PUBLICAT
    assert audit_efect(admin_engine, e.id, "efect.incercare") == 2, "fiecare încercare e în jurnalul de audit"
    assert audit_efect(admin_engine, e.id, "efect.trimis") == 1


def test_expirarea_conectorului_este_temporara_si_urmatoarea_incercare_verifica_intai(
    tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    e = cere(tenant, lid).efect
    platforma.scenariu(trimite=["expira", "ok"])
    with pytest.raises(motor.EroareTemporara):
        incearca(tenant, e.id)
    assert incearca(tenant, e.id) == "trimis"
    assert [a.split()[0] for a in platforma.apeluri()] == ["trimite", "verifica", "trimite"]
    assert len(platforma.postari()) == 1


def test_o_incercare_intrerupta_lasa_efectul_in_trimitere_si_repornirea_verifica(
    tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals, admin_engine: Engine
) -> None:
    """Procesul a murit între trimitere și notarea rezultatului: starea rămasă este `în trimitere`."""
    lid = livrabil_in_publicare(tenant, om)
    e = cere(tenant, lid).efect
    with sesiune_tenant(tenant) as db:  # primul pas al încercării (ca în `_incearca`), apoi „moartea”
        rand = servicii.blocheaza(db, e.id)
        servicii.muta_efect(db, rand, efecte.Stare.IN_TRIMITERE, incercari=1)
    platforma._posteaza(
        EfectDeTrimis(e.id, tenant, lid, "fals", 1, "publicare", e.cheia, {})
    )  # a ajuns la „platformă”
    assert incearca(tenant, e.id) == "trimis"
    assert len(platforma.postari()) == 1 and platforma.apeluri("trimite") == []
    assert platforma.apeluri("verifica") == [f"verifica {e.cheia} ok"]


def test_reincercari_temporare_cu_pauza_prin_fluxul_durabil_si_o_singura_publicare(
    executor: None, tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    platforma.scenariu(trimite=["temporar", "temporar", "ok"])
    e = cere(tenant, lid).efect
    job = efecte.porneste_executia(e.id)
    assert job is not None
    assert motor.asteapta_flux(job, timeout_sec=30).stare is motor.StareJob.TERMINAT
    final = efect(tenant, e.id)
    assert (final.stare, final.incercari) == ("trimis", 3)
    assert len(platforma.postari()) == 1
    assert [a.split()[0] for a in platforma.apeluri()] == [
        "trimite", "verifica", "trimite", "verifica", "trimite",
    ]  # fmt: skip
    assert stare(tenant, lid) == Stare.PUBLICAT


def test_reincercarile_epuizate_duc_livrabilul_in_coada_de_erori_cu_context(
    executor: None, tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals, anunturi: AnunturiFalse
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    platforma.scenariu(trimite=["temporar"] * 10)
    e = cere(tenant, lid).efect
    job = efecte.porneste_executia(e.id)
    assert job is not None
    assert motor.asteapta_flux(job, timeout_sec=30).stare is motor.StareJob.TERMINAT
    final = efect(tenant, e.id)
    assert (
        final.stare == "esuat_definitiv" and final.eroare_cod == "IncercariEpuizate" and final.incercari == 4
    )
    assert platforma.postari() == []
    assert stare(tenant, lid) == Stare.COADA_DE_ERORI
    with sesiune_tenant(tenant) as db:
        [intrare] = coada_erori.lista(db)
    assert intrare.context["tip_sursa"] == "efect" and intrare.context["efect_id"] == str(e.id)
    assert intrare.context["canal"] == "fals" and intrare.context["incercari"] == 4
    assert Nivel.IMPORTANT in anunturi.nivele()


def test_eroarea_definitiva_nu_se_reincearca(
    tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    e = cere(tenant, lid).efect
    platforma.scenariu(trimite=["definitiv"])
    assert incearca(tenant, e.id) == "esuat"
    assert incearca(tenant, e.id) == "esuat", "un efect eșuat așteaptă un om"
    assert platforma.apeluri("trimite") == [f"trimite {e.cheia} definitiv"]
    assert efect(tenant, e.id).stare == "esuat_definitiv" and stare(tenant, lid) == Stare.COADA_DE_ERORI


def test_omul_reia_livrabilul_si_efectul_esuat_pleaca_dupa_verificare(
    tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    e = cere(tenant, lid).efect
    platforma.scenariu(trimite=["definitiv"])
    incearca(tenant, e.id)
    with sesiune_tenant(tenant) as db:
        rez = efecte.reia_livrabilul(db, lid, utilizator_id=om, motiv="platforma a fost reparată")
    assert rez.stare == Stare.IN_PUBLICARE
    reluat = efect(tenant, e.id)
    assert reluat.stare == "in_asteptare" and reluat.incercari == 1
    with sesiune_tenant(tenant) as db:
        assert coada_erori.lista(db) == [], "intrarea din coada de erori s-a închis"
    assert incearca(tenant, e.id) == "trimis"
    assert platforma.apeluri()[-2:] == [f"verifica {e.cheia} ok", f"trimite {e.cheia} ok"]
    assert stare(tenant, lid) == Stare.PUBLICAT


# --- autentificarea --------------------------------------------------------------------------------------------------


def test_eroare_de_autentificare_pune_canalul_pe_pauza_si_nu_pierde_efectul(
    tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals, anunturi: AnunturiFalse
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    e = cere(tenant, lid).efect
    platforma.scenariu(trimite=["autentificare"])
    assert incearca(tenant, e.id) == "autentificare"
    with sesiune_tenant(tenant) as db:
        [p] = efecte.pauze(db)
    assert (p.tenant_id, p.canal) == (tenant, "fals")
    tinut = efect(tenant, e.id)
    assert tinut.stare == "in_asteptare" and "reautorizare" in tinut.motiv
    assert stare(tenant, lid) == Stare.IN_PUBLICARE, "nimic nu se pierde"
    assert anunturi.titluri().count("Reautorizare necesară") == 1

    assert incearca(tenant, e.id) == "pauza"
    assert platforma.apeluri("trimite") == [f"trimite {e.cheia} autentificare"], "pe pauză nu se mai apelează"

    with sesiune_tenant(tenant, om) as db:
        assert efecte.reia_conectorul(db, tenant, "fals", utilizator_id=om)
    assert incearca(tenant, e.id) == "trimis"
    assert platforma.apeluri("verifica") == [f"verifica {e.cheia} ok"], "după o încercare, verifică întâi"
    assert len(platforma.postari()) == 1


# --- opririle --------------------------------------------------------------------------------------------------------


def opreste(tip: Oprire, *, tenant_id: uuid.UUID | None = None, activ: bool = True) -> None:
    with sesiune_agentie() as db:
        opriri.seteaza(db, tip, activ, canal="sistem", motiv="test", tenant_id=tenant_id)


@pytest.fixture(autouse=True)
def _fara_opriri(admin_engine: Engine) -> Iterator[None]:
    with admin_engine.begin() as c:
        c.execute(text("TRUNCATE opriri, efecte_de_trimis, conectori_pauze"))
    yield
    with admin_engine.begin() as c:
        c.execute(text("TRUNCATE opriri"))


def test_cu_oprirea_globala_nu_pleaca_niciun_efect_si_ele_raman_in_asteptare(
    tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals
) -> None:
    efecte_cerute = [cere(tenant, livrabil_in_publicare(tenant, om)).efect for _ in range(3)]
    opreste(Oprire.PUBLICARE)
    for e in efecte_cerute:
        assert incearca(tenant, e.id) == "oprit"
    assert platforma.apeluri() == [], "niciun apel la conector cu oprirea activă"
    for e in efecte_cerute:
        tinut = efect(tenant, e.id)
        assert tinut.stare == "in_asteptare" and tinut.incercari == 0 and "oprit" in tinut.motiv

    # repornire: pleacă, fiindcă sunt încă valabile
    opreste(Oprire.PUBLICARE, activ=False)
    for e in efecte_cerute:
        assert incearca(tenant, e.id) == "trimis"
    assert len(platforma.postari()) == 3


def test_oprirea_se_verifica_chiar_inainte_de_trimitere_nu_doar_la_programare(
    executor: None, tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    e = cere(tenant, lid).efect  # cerut (și pus în coadă) înainte de oprire
    opreste(Oprire.PUBLICARE)
    job = efecte.porneste_executia(e.id)
    assert job is not None and motor.asteapta_flux(job, timeout_sec=30).stare is motor.StareJob.TERMINAT
    assert platforma.apeluri() == [] and efect(tenant, e.id).stare == "in_asteptare"


def test_oprirea_pe_client_tine_doar_efectele_clientului(
    tenant: uuid.UUID, fabrica_clienti: Callable[[], uuid.UUID], om: uuid.UUID, platforma: ConectorFals
) -> None:
    alt_client = fabrica_clienti()
    e_a = cere(tenant, livrabil_in_publicare(tenant, om)).efect
    e_b = cere(alt_client, livrabil_in_publicare(alt_client, om)).efect
    opreste(Oprire.CLIENT, tenant_id=tenant)
    assert incearca(tenant, e_a.id) == "oprit"
    assert incearca(alt_client, e_b.id) == "trimis"
    assert len(platforma.postari()) == 1


def test_dupa_repornire_efectul_care_nu_mai_e_valabil_se_anuleaza_cu_motiv(
    tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals, admin_engine: Engine
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    e = cere(tenant, lid).efect
    opreste(Oprire.PUBLICARE)
    assert incearca(tenant, e.id) == "oprit"
    muta(
        tenant, lid, Stare.IN_PUBLICARE, Stare.COADA_DE_ERORI
    )  # între timp, livrabilul a ieșit din publicare
    opreste(Oprire.PUBLICARE, activ=False)
    assert incearca(tenant, e.id) == "anulat"
    anulat = efect(tenant, e.id)
    assert anulat.stare == "anulat" and "nu mai este" in anulat.motiv
    assert platforma.apeluri() == []


def test_dupa_repornire_efectul_cu_versiune_schimbata_se_anuleaza(
    tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals, admin_engine: Engine
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    e = cere(tenant, lid).efect
    with (
        admin_engine.begin() as c
    ):  # SIMULAT: o versiune nouă a conținutului (în viața reală: după o reîntoarcere în producție)
        c.execute(text("UPDATE livrabile SET versiune = 2 WHERE id = :i"), {"i": lid})
    assert incearca(tenant, e.id) == "anulat"
    assert "versiunea livrabilului s-a schimbat (v1 → v2)" in efect(tenant, e.id).motiv
    assert platforma.apeluri() == []


def test_clasele_de_efect_se_mapeaza_pe_tipuri_de_oprire() -> None:
    assert set(efecte.OPRIRE_PE_TIP) == set(efecte.Tip), "fiecare clasă de efect are o oprire"
    assert efecte.OPRIRE_PE_TIP[efecte.Tip.PUBLICARE] is Oprire.PUBLICARE


def test_redistribuirea_porneste_efectele_ramase_dupa_oprire_numai_cand_nu_mai_e_oprit(
    executor: None, tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    opreste(Oprire.PUBLICARE)
    e = cere(tenant, lid, porneste=True).efect
    motor_job = f"efect:{e.id}:1"
    assert motor.asteapta_flux(motor_job, timeout_sec=30).stare is motor.StareJob.TERMINAT
    assert efect(tenant, e.id).stare == "in_asteptare" and platforma.apeluri() == []
    assert efecte.redistribuie() == 0, "cât timp e oprit, tic-ul nu repune nimic în coadă"
    opreste(Oprire.PUBLICARE, activ=False)
    assert efecte.redistribuie() == 1
    motor.asteapta_flux(f"efect:{e.id}:2", timeout_sec=30)
    assert efect(tenant, e.id).stare == "trimis" and len(platforma.postari()) == 1


# --- o singură încercare odată -----------------------------------------------------------------------------------------


def test_doua_incercari_simultane_pe_acelasi_efect_trimit_o_singura_data(
    tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    e = cere(tenant, lid).efect
    platforma.scenariu(trimite=["blocheaza_dupa"])
    (platforma.dir / "blocheaza").touch()
    rezultat: list[str] = []
    fir = threading.Thread(target=lambda: rezultat.append(incearca(tenant, e.id)))
    fir.start()
    from tests.chaos.utile import asteapta

    asteapta(lambda: (platforma.dir / "dupa.marcaj").exists(), mesaj="trimiterea blocată")
    assert incearca(tenant, e.id) == "ocupat", "a doua încercare nu trimite cât prima e în curs"
    (platforma.dir / "blocheaza").unlink()
    fir.join(timeout=30)
    assert rezultat == ["trimis"] and len(platforma.postari()) == 1


# --- stările ca date; jurnalul -------------------------------------------------------------------------------------------


def test_tabelul_de_stari_din_cod_este_cel_din_baza(baza, admin_engine: Engine) -> None:  # type: ignore[no-untyped-def]
    import importlib

    from app.operare.efecte import stari

    mig = importlib.import_module("migrations.versions.0011_efecte")

    assert sorted(mig.TRANZITII) == stari.perechi()
    assert {s.value for s in stari.Stare} == set(mig.STARI)
    assert {t.value for t in stari.Tip} == set(mig.TIPURI)


def test_baza_refuza_tranzitia_nepermisa_si_schimbarea_identitatii(
    tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals
) -> None:
    from sqlalchemy.exc import DBAPIError

    lid = livrabil_in_publicare(tenant, om)
    e = cere(tenant, lid).efect
    with pytest.raises(DBAPIError, match="tranziție nepermisă"), sesiune_tenant(tenant) as db:
        db.execute(
            text("UPDATE efecte_de_trimis SET stare = 'trimis', id_extern = 'x' WHERE id = :i"), {"i": e.id}
        )
    with pytest.raises(DBAPIError, match="identitatea"), sesiune_tenant(tenant) as db:
        db.execute(text("UPDATE efecte_de_trimis SET canal = 'altul' WHERE id = :i"), {"i": e.id})
    incearca(tenant, e.id)
    with pytest.raises(DBAPIError), sesiune_tenant(tenant) as db:  # `trimis` e final
        db.execute(text("UPDATE efecte_de_trimis SET stare = 'anulat' WHERE id = :i"), {"i": e.id})


def test_anularea_de_om_cere_motiv_si_se_audita(
    tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals, admin_engine: Engine
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    e = cere(tenant, lid).efect
    with pytest.raises(ValueError), sesiune_tenant(tenant, om) as db:
        efecte.anuleaza(db, e.id, motiv=" ")
    with sesiune_tenant(tenant, om) as db:
        efecte.anuleaza(db, e.id, motiv="clientul a cerut oprirea")
    assert efect(tenant, e.id).stare == "anulat" and audit_efect(admin_engine, e.id, "efect.anulat") == 1
    assert incearca(tenant, e.id) == "anulat" and platforma.apeluri() == []


def test_programarea_tic_este_declarata_si_modulul_incarcat_de_worker() -> None:
    from app import worker

    efecte.declara_programari()
    [p] = [p for p in motor.programari_declarate() if p.nume == efecte.NUME_TIC]
    assert p.cron == "0 * * * * *" and p.flux == "efecte.tic"
    assert "app.operare.efecte" in worker.MODULE_FLUXURI
