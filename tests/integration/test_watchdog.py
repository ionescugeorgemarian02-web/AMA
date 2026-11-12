"""F2.7 — watchdog și coada de erori: semne de viață, joburi eșuate și blocate, trierea, reluarea.

Executorul rulează în procesul testului; watchdog-ul se rulează pas cu pas (`bate`, `scaneaza`), fără fir, ca
testele să fie deterministe. Procesele reale (SIGKILL, restart) sunt în `tests/chaos/test_watchdog.py`.
"""

import time
import uuid
from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import Engine, text

from app.db import sesiune_agentie
from app.operare import coada_erori, motor, semnale, watchdog
from app.operare.coada_erori import Severitate, Stare
from app.operare.notificari import Nivel
from app.operare.tabele import IntrareEroare
from app.operare.watchdog import Watchdog
from tests.integration import fluxuri_watchdog as flux

pytestmark = pytest.mark.db
Pornire = Callable[..., None]


@pytest.fixture(autouse=True)
def _curat(porneste_executor: Pornire, admin_engine: Engine) -> Iterator[None]:
    """Depinde de `porneste_executor` ca să se închidă înaintea lui (joburile blocate se eliberează la timp)."""
    with admin_engine.begin() as c:
        c.execute(text("TRUNCATE coada_erori, worker_semnale, worker_evenimente"))
    flux.reseteaza()
    yield
    flux.elibereaza()
    flux.reseteaza()


class Notificari:
    """SIMULAT: ține locul canalelor push/Telegram; înregistrează ce s-ar fi trimis."""

    def __init__(self) -> None:
        self.trimise: list[tuple[Nivel, str, str, str]] = []

    def __call__(self, nivel: Nivel, titlu: str, text_: str, url: str = "/alerte") -> None:
        self.trimise.append((nivel, titlu, text_, url))

    def titluri(self) -> list[str]:
        return [t[1] for t in self.trimise]


@pytest.fixture
def notificari(monkeypatch: pytest.MonkeyPatch) -> Notificari:
    n = Notificari()
    monkeypatch.setattr(watchdog, "_notifica", n)
    return n


def un_watchdog(**kw: object) -> Watchdog:
    setari: dict[str, object] = {
        "bataie_sec": 0.2,
        "scanare_sec": 0.2,
        "timeout_sec": 5,
        "prag_reporniri": 3,
        "fereastra_min": 60,
        "prag_crestere": 3,
        "versiune": "f2",
    }
    setari.update(kw)
    return Watchdog("worker-local", **setari)  # type: ignore[arg-type]


def client_nou(admin: Engine) -> str:
    cid = uuid.uuid4()
    with admin.begin() as c:
        c.execute(text("INSERT INTO clienti (id, nume) VALUES (:i, 'Firma Alerte')"), {"i": cid})
    return str(cid)


def trimite_si_asteapta(fluxul: Callable[..., object], *args: str, cheie: str) -> motor.StareFlux:
    job = motor.trimite(fluxul, *args, cheie=cheie)
    return motor.asteapta_flux(job, timeout_sec=20)


def intrari() -> list[IntrareEroare]:
    with sesiune_agentie() as db:
        return coada_erori.lista(db, doar_deschise=False)


# ---- coada de erori: un job eșuat, cu context complet ----------------------------------------------------------------------


def test_un_job_esuat_intra_in_coada_cu_contextul_complet(
    porneste_executor: Pornire, admin_engine: Engine, notificari: Notificari
) -> None:
    porneste_executor()
    tenant = client_nou(admin_engine)
    stare = trimite_si_asteapta(flux.esueaza, tenant, "a1", cheie="wd-a1")
    assert stare.stare is motor.StareJob.ESUAT

    rez = un_watchdog().scaneaza()
    assert rez.ingerate == 1 and not rez.erori, rez.erori

    (i,) = intrari()
    assert (i.workflow_id, i.flux, i.pas, i.eroare_tip) == (
        "wd-a1",
        "watchdog.esueaza",
        "watchdog.pas_stricat",
        "EroareDefinitiva",
    )
    assert str(i.tenant_id) == tenant, "clientul vine din primul argument al jobului"
    assert (i.severitate, i.stare, i.stare_job, i.coada) == ("minor", "noua", "esuat", "io")
    assert "nu merge jobul a1" in i.eroare_mesaj and len(i.eroare_mesaj) <= 500
    c = i.context
    assert c["argumente"] == [tenant, "a1"] and c["flux"] == "watchdog.esueaza"
    assert [(p["nume"], p["stare"]) for p in c["pasi"]] == [
        ("watchdog.pas_bun", "ok"),
        ("watchdog.pas_stricat", "eroare"),
    ], "pașii de până la eșec, cu starea lor"
    assert c["pasi"][1]["eroare"].startswith("EroareDefinitiva: nu merge jobul a1")
    assert any("nu se reîncearcă" in x for x in c["ce_s_a_incercat"])
    assert c["executor"] == "worker-local" and c["versiune_joburi"] == "f2"
    with admin_engine.connect() as cn:
        ev = cn.execute(
            text(
                "SELECT tip, obiect_id, tenant_id::text FROM jurnal_evenimente "
                "WHERE tip = 'job.in_coada_de_erori' AND obiect_id = 'wd-a1'"
            )
        ).all()
    assert [(e[0], e[1], e[2]) for e in ev] == [("job.in_coada_de_erori", "wd-a1", tenant)]


def test_a_doua_scanare_nu_dubleaza_si_o_decizie_inchisa_nu_se_redeschide(
    porneste_executor: Pornire, admin_engine: Engine, notificari: Notificari
) -> None:
    porneste_executor()
    tenant = client_nou(admin_engine)
    trimite_si_asteapta(flux.esueaza, tenant, "b1", cheie="wd-b1")
    w = un_watchdog()
    assert w.scaneaza().ingerate == 1
    assert w.scaneaza().ingerate == 0
    with sesiune_agentie() as db:
        (i,) = coada_erori.lista(db)
        coada_erori.inchide(db, i, motiv="cunoscut, se rezolvă în F9", utilizator_id=None)
    assert w.scaneaza().ingerate == 0, (
        "jobul rămâne eșuat în bibliotecă, dar decizia înregistrată nu se redeschide"
    )
    (i,) = intrari()
    assert i.stare == "inchisa" and i.motiv_inchidere and i.inchis_la is not None


def test_nimic_nu_se_inchide_fara_motiv(
    porneste_executor: Pornire, admin_engine: Engine, notificari: Notificari
) -> None:
    porneste_executor()
    trimite_si_asteapta(flux.esueaza, client_nou(admin_engine), "c1", cheie="wd-c1")
    un_watchdog().scaneaza()
    with sesiune_agentie() as db:
        (i,) = coada_erori.lista(db)
        with pytest.raises(ValueError, match="motiv"):
            coada_erori.inchide(db, i, motiv="   ", utilizator_id=None)


def test_erorile_cu_aceeasi_cauza_se_grupeaza_iar_pragul_urca_alerta_o_singura_data(
    porneste_executor: Pornire, admin_engine: Engine, notificari: Notificari
) -> None:
    porneste_executor()
    tenant = client_nou(admin_engine)
    w = un_watchdog(prag_crestere=3)
    trimite_si_asteapta(flux.esueaza, tenant, "g1", cheie="wd-g1")
    w.scaneaza()
    assert notificari.titluri() == ["Cauză nouă de eroare: watchdog.esueaza"], (
        "o cauză nouă este un incident nou"
    )
    assert notificari.trimise[0][0] is Nivel.INFORMATIV, "un singur job în coadă = minor = rezumat zilnic"
    trimite_si_asteapta(flux.esueaza, tenant, "g2", cheie="wd-g2")
    w.scaneaza()
    assert len(notificari.trimise) == 1, "aceeași cauză, sub prag: fără alertă nouă"
    trimite_si_asteapta(flux.esueaza, tenant, "g3", cheie="wd-g3")
    w.scaneaza()
    assert [t[0] for t in notificari.trimise[1:]] == [Nivel.IMPORTANT]
    assert notificari.trimise[1][1] == "Erori care se tot repetă"

    toate = intrari()
    assert {i.cauza for i in toate} == {toate[0].cauza}, (
        "mesaje cu numere și identificatori diferite = aceeași cauză"
    )
    assert {i.severitate for i in toate} == {"major"}, "coada care crește urcă toată cauza la major"
    (grup,) = coada_erori.grupeaza(toate)
    assert grup.intrari == 3 and grup.severitate == "major"

    trimite_si_asteapta(flux.esueaza, tenant, "g4", cheie="wd-g4")
    w.scaneaza()
    assert len(notificari.trimise) == 2, "peste prag nu se mai alertează la fiecare intrare"


def test_cauze_diferite_sunt_grupuri_diferite(
    porneste_executor: Pornire, admin_engine: Engine, notificari: Notificari
) -> None:
    porneste_executor()
    tenant = client_nou(admin_engine)
    trimite_si_asteapta(flux.esueaza, tenant, "d1", cheie="wd-d1")
    trimite_si_asteapta(flux.esueaza_alt, tenant, "d2", cheie="wd-d2")
    un_watchdog().scaneaza()
    assert len(coada_erori.grupeaza(intrari())) == 2


def test_eroarea_de_autentificare_este_major_si_anunta_imediat(
    porneste_executor: Pornire, admin_engine: Engine, notificari: Notificari
) -> None:
    porneste_executor()
    trimite_si_asteapta(flux.autentificare, client_nou(admin_engine), "e1", cheie="wd-e1")
    un_watchdog().scaneaza()
    (i,) = intrari()
    assert i.severitate == "major" and i.eroare_tip == "EroareAutentificare"
    assert [(n[0], n[1]) for n in notificari.trimise] == [
        (Nivel.IMPORTANT, "Job eșuat: watchdog.autentificare")
    ]
    assert notificari.trimise[0][3] == f"/alerte/{i.id}"
    text_notificare = " ".join(notificari.trimise[0][1:3]).lower()
    assert "conectorul a pierdut" not in text_notificare, (
        "mesajul erorii nu pleacă în notificare, doar numele și pasul"
    )


def test_jobul_fara_client_cunoscut_intra_ca_eroare_de_sistem(
    porneste_executor: Pornire, notificari: Notificari
) -> None:
    porneste_executor()
    trimite_si_asteapta(flux.esueaza, str(uuid.uuid4()), "s1", cheie="wd-s1")  # un client care nu există
    un_watchdog().scaneaza()
    (i,) = intrari()
    assert i.tenant_id is None


# ---- joburi blocate ------------------------------------------------------------------------------------------------------------


def asteapta_scanand(w: Watchdog, conditie: Callable[[], bool], timeout_sec: float = 15.0) -> None:
    limita = time.monotonic() + timeout_sec
    while not conditie():
        if time.monotonic() > limita:
            raise AssertionError("condiția nu s-a îndeplinit")
        w.scaneaza()
        time.sleep(0.15)


def test_jobul_blocat_este_oprit_si_reincercat_o_data_iar_intrarea_se_inchide_singura(
    porneste_executor: Pornire, admin_engine: Engine, notificari: Notificari
) -> None:
    porneste_executor()
    flux.BLOCHEAZA_PRIMELE["k1"] = 1  # prima rulare a pasului se blochează, a doua trece
    job = motor.trimite(flux.capricios, client_nou(admin_engine), "k1", cheie="wd-k1")
    w = un_watchdog()
    asteapta_scanand(w, lambda: any(i.workflow_id == job for i in intrari()))

    (i,) = intrari()
    assert (i.eroare_tip, i.stare, i.reluari) == ("TimpDepasit", "reluata", 1)
    assert not notificari.trimise or all(t[0] is Nivel.INFORMATIV for t in notificari.trimise), (
        "prima reîncercare nu deranjează"
    )
    assert motor.asteapta_flux(job, timeout_sec=20).stare is motor.StareJob.TERMINAT, "reîncercarea a trecut"
    assert flux.incercari("k1") == 2

    asteapta_scanand(w, lambda: intrari()[0].stare == "inchisa")
    (i,) = intrari()
    assert i.motiv_inchidere == "reluat și terminat cu succes" and i.inchis_de is None


def test_jobul_care_se_blocheaza_si_a_doua_oara_intra_in_coada_si_anunta(
    porneste_executor: Pornire, admin_engine: Engine, notificari: Notificari
) -> None:
    porneste_executor()
    flux.BLOCHEAZA_PRIMELE["k2"] = 99
    job = motor.trimite(flux.capricios, client_nou(admin_engine), "k2", cheie="wd-k2")
    w = un_watchdog()
    asteapta_scanand(w, lambda: bool(intrari()) and intrari()[0].stare == "noua")

    (i,) = intrari()
    assert (i.eroare_tip, i.severitate, i.reluari) == ("TimpDepasit", "major", 1)
    assert [n[1] for n in notificari.trimise] == ["Job blocat: watchdog.capricios"]
    assert notificari.trimise[0][0] is Nivel.IMPORTANT
    st = motor.stare_flux(job)
    assert st is not None and st.stare is motor.StareJob.ANULAT, "oprit, nu lăsat să ruleze la nesfârșit"


# ---- reluarea din coada de erori -----------------------------------------------------------------------------------------------


def test_un_job_esuat_se_reia_de_la_pasul_eșuat_prin_bifurcare(
    porneste_executor: Pornire, admin_engine: Engine, notificari: Notificari
) -> None:
    """Biblioteca nu reia un job `ERROR`: bifurcarea copiază pașii dinainte și reia pasul eșuat."""
    porneste_executor()
    flux.ESUEAZA_PRIMELE["r1"] = 1  # prima rulare a pasului eșuează, a doua trece
    tenant = client_nou(admin_engine)
    stare = trimite_si_asteapta(flux.capricios, tenant, "r1", cheie="wd-r1")
    assert stare.stare is motor.StareJob.ESUAT
    w = un_watchdog()
    w.scaneaza()
    (i,) = intrari()

    continua_ca = motor.reia_job(i.workflow_id)
    assert continua_ca != "wd-r1"
    with sesiune_agentie() as db:
        coada_erori.marcheaza_reluata(
            db, db.get(IntrareEroare, i.id), reluat_ca=continua_ca, utilizator_id=None
        )  # type: ignore[arg-type]
    assert motor.asteapta_flux(continua_ca, timeout_sec=20).stare is motor.StareJob.TERMINAT
    assert flux.incercari("r1") == 2, "pasul eșuat s-a reluat o singură dată"

    rez = w.scaneaza()
    assert rez.inchise_automat == 1 and rez.ingerate == 0, (
        "originalul rămâne eșuat în bibliotecă, dar nu reintră în coadă"
    )
    (i,) = intrari()
    assert (i.stare, i.motiv_inchidere) == ("inchisa", "reluat și terminat cu succes")


def test_reluarea_unui_job_care_ruleaza_este_refuzata(
    porneste_executor: Pornire, admin_engine: Engine
) -> None:
    porneste_executor()
    trimite_si_asteapta(flux.esueaza, client_nou(admin_engine), "x1", cheie="wd-x1")
    ok = trimite_si_asteapta(flux.esueaza_alt, client_nou(admin_engine), "x2", cheie="wd-x2")
    assert ok.stare is motor.StareJob.ESUAT
    bun = motor.trimite(flux.capricios, client_nou(admin_engine), "x3", cheie="wd-x3")
    assert motor.asteapta_flux(bun, timeout_sec=20).stare is motor.StareJob.TERMINAT
    with pytest.raises(motor.JobNereluabil, match="terminat"):
        motor.reia_job(bun)
    with pytest.raises(motor.JobNereluabil, match="nu mai există"):
        motor.reia_job("nu-exista")


def test_jobul_anulat_se_reia_in_coada_lui_din_ultimul_pas(
    admin_engine: Engine, porneste_executor: Pornire
) -> None:
    """Un job anulat (cât workerul nu rulează) se reia cu același identificator, în coada originală."""
    job = motor.trimite(
        flux.capricios, client_nou(admin_engine), "y1", cheie="wd-y1", coada=motor.Coada.INVATARE
    )
    motor.anuleaza_job(job)
    assert motor.stare_flux(job).stare is motor.StareJob.ANULAT  # type: ignore[union-attr]
    assert motor.reia_job(job) == job
    porneste_executor()
    assert motor.asteapta_flux(job, timeout_sec=20).stare is motor.StareJob.TERMINAT
    final = motor.stare_flux(job)
    assert final is not None and final.coada == "invatare"


# ---- semnale de viață ----------------------------------------------------------------------------------------------------------------


def ev(admin: Engine, tip: str | None = None) -> list[str]:
    with admin.connect() as c:
        q = "SELECT tip FROM worker_evenimente WHERE worker_id = 'worker-local'" + (
            " AND tip = :t" if tip else ""
        )
        return [r[0] for r in c.execute(text(q + " ORDER BY la, id"), {"t": tip} if tip else {})]


def test_pornirea_scrie_semnalul_iar_bataia_il_innoieste(
    admin_engine: Engine, porneste_executor: Pornire
) -> None:
    w = un_watchdog()
    p = w.porneste()
    try:
        assert not p.dupa_cadere
        with sesiune_agentie() as db:
            (s,) = semnale.toate(db)
            prima = s.ultimul_semnal
            assert s.worker_id == "worker-local" and not s.oprit_curat
        time.sleep(0.05)
        w.bate()
        with sesiune_agentie() as db:
            assert semnale.toate(db)[0].ultimul_semnal > prima
        assert ev(admin_engine) == ["pornit"]
    finally:
        w.opreste()
    with sesiune_agentie() as db:
        assert semnale.toate(db)[0].oprit_curat is True
    assert ev(admin_engine) == ["pornit", "oprit_curat"]


def test_firul_watchdog_bate_singur_si_se_opreste(admin_engine: Engine, porneste_executor: Pornire) -> None:
    w = un_watchdog(bataie_sec=0.1, scanare_sec=0.1)
    w.porneste()
    try:
        with sesiune_agentie() as db:
            prima = semnale.toate(db)[0].ultimul_semnal
        limita = time.monotonic() + 5
        while time.monotonic() < limita:
            with sesiune_agentie() as db:
                if semnale.toate(db)[0].ultimul_semnal > prima:
                    break
            time.sleep(0.05)
        else:
            raise AssertionError("firul nu a bătut")
    finally:
        w.opreste()
    assert w._fir is not None and not w._fir.is_alive()


def test_repornirea_dupa_o_cadere_este_vazuta_iar_oprirea_curata_nu_conteaza(
    admin_engine: Engine, porneste_executor: Pornire, notificari: Notificari
) -> None:
    a = un_watchdog(prag_reporniri=3)
    a.porneste()
    a._stop.set()  # „cade”: nu mai bate și nu se marchează oprit curat
    b = un_watchdog(prag_reporniri=3)
    p = b.porneste()
    assert p.dupa_cadere and p.reporniri_in_fereastra == 1 and not p.alerta
    b.opreste()  # oprire curată
    c = un_watchdog(prag_reporniri=3)
    assert not c.porneste().dupa_cadere
    c.opreste()
    assert ev(admin_engine, "repornit_dupa_cadere") == ["repornit_dupa_cadere"]
    assert notificari.trimise == []


def test_a_treia_repornire_intr_o_ora_anunta_o_singura_data(
    admin_engine: Engine, porneste_executor: Pornire, notificari: Notificari
) -> None:
    ultimul: Watchdog | None = None
    for n in range(1, 6):
        w = un_watchdog(prag_reporniri=3)
        p = w.porneste()
        w._stop.set()  # fiecare instanță „cade” fără oprire curată; fixture-ul nu lasă fire de bătaie
        ultimul = w
        if n < 4:
            assert p.reporniri_in_fereastra == n - 1
    assert ultimul is not None
    anunturi = [t for t in notificari.trimise if t[1].startswith("Workerul a căzut")]
    assert len(anunturi) == 1 and anunturi[0][0] is Nivel.IMPORTANT
    assert anunturi[0][1] == "Workerul a căzut de 3 ori în 60 min", (
        "la a treia cădere, nu la fiecare următoare"
    )
    assert len(ev(admin_engine, "alerta_reporniri")) == 1


def test_un_worker_fara_semn_de_viata_este_semnalat_o_data_de_ceilalti(
    admin_engine: Engine, porneste_executor: Pornire, notificari: Notificari
) -> None:
    with admin_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO worker_semnale (worker_id, pid, ultimul_semnal) VALUES ('worker-2', 7, now() - interval '10 minutes')"
            )
        )
        c.execute(
            text(
                "INSERT INTO worker_semnale (worker_id, pid, ultimul_semnal, oprit_curat) VALUES ('worker-3', 8, now() - interval '10 minutes', true)"
            )
        )
    w = un_watchdog(timeout_sec=60)
    assert w.scaneaza().workeri_fara_semn == ["worker-2"], (
        "worker-3 s-a oprit curat; worker-local nu e verificat de el însuși"
    )
    assert w.scaneaza().workeri_fara_semn == []
    assert [t[1] for t in notificari.trimise] == ["Worker fără semn de viață"]
    with sesiune_agentie() as db:
        stari = {s.worker_id: s.viu for s in semnale.stare_workeri(db, 60)}
    assert stari == {"worker-2": False, "worker-3": False}
    assert semnale.este_viu("worker-2", 60) is False
    w.bate()  # nu există rând pentru worker-local: nu se întâmplă nimic


def test_verificarea_de_sanatate_cere_o_bataie_recenta(
    admin_engine: Engine, porneste_executor: Pornire
) -> None:
    assert semnale.este_viu("worker-local", 30) is False, "fără rând = nu a pornit"
    w = un_watchdog()
    w.porneste()
    try:
        assert semnale.este_viu("worker-local", 30) is True
        with admin_engine.begin() as c:
            c.execute(text("UPDATE worker_semnale SET ultimul_semnal = now() - interval '5 minutes'"))
        assert semnale.este_viu("worker-local", 30) is False
    finally:
        w.opreste()
    assert semnale.este_viu("worker-local", 300) is False, "oprit curat nu mai e „viu”"


def test_notificarea_trece_prin_notificari_notifica(monkeypatch: pytest.MonkeyPatch) -> None:
    primite: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        watchdog.notificari,
        "notifica",
        lambda nivel, titlu, text_, url="/alerte": primite.append((nivel, titlu, text_, url)),
    )
    watchdog._notifica(Nivel.IMPORTANT, "T", "x", "/alerte/1")
    assert primite == [(Nivel.IMPORTANT, "T", "x", "/alerte/1")]


def test_severitatile_si_starile_sunt_cele_din_baza() -> None:
    assert {s.value for s in Severitate} == {"critic", "major", "minor", "informativ"}
    assert {s.value for s in Stare} == {"noua", "reluata", "inchisa"}
