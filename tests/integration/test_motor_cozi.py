"""F2.2 — cozile din 7.5: culoare grele, `io`, `urgent`, `învățare`, limite de rată, priorități.

Executorul rulează în procesul testului; joburile se coordonează cu testul prin evenimente (nu prin pauze).
Starea „al treilea așteaptă” se verifică după câteva sondări ale cozii (polling 0,1 s), apoi se eliberează un
culoar și se vede că a pornit.
"""

import datetime as dt
import time
from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import Engine, text

from app.operare import motor
from app.operare.motor import Coada, Prioritate
from tests.integration import fluxuri_cozi as cozi

pytestmark = pytest.mark.db

Pornire = Callable[..., None]
SONDARI = 0.6  # ≈ 6 sondări ale cozii: dacă un job putea porni, ar fi pornit


@pytest.fixture(autouse=True)
def _curat(porneste_executor: Pornire) -> Iterator[None]:
    """Depinde de `porneste_executor` ca să se închidă ÎNAINTE de el: joburile blocate se eliberează cât
    executorul încă rulează (altfel scriu rezultatul într-o bibliotecă oprită, iar procesul nu iese)."""
    cozi.reseteaza()
    yield
    cozi.elibereaza_tot()
    cozi.reseteaza()


def trimite(nume: str, coada: Coada | str, **kw: object) -> str:
    cozi.blocheaza(nume)
    return motor.trimite(cozi.job, nume, coada=coada, cheie=f"cozi-{nume}", **kw)  # type: ignore[arg-type]


def asteapta_toate(*ids: str) -> None:
    for i in ids:
        assert motor.asteapta_flux(i, timeout_sec=20).stare is motor.StareJob.TERMINAT


# ---- „Gata când”: două culoare grele, trei joburi --------------------------------------------------------------------------


def test_cu_doua_culoare_din_trei_joburi_grele_doua_ruleaza_iar_al_treilea_asteapta(
    porneste_executor: Pornire,
) -> None:
    porneste_executor(culoare_greu=2)
    ids = [trimite(n, Coada.GREU) for n in ("g1", "g2", "g3")]  # trimise unul după altul, fără pauză

    cozi.asteapta_pornirea("g1")
    cozi.asteapta_pornirea("g2")
    time.sleep(SONDARI)
    assert sorted(cozi.pornite()) == ["g1", "g2"], (
        "două culoare = două joburi în paralel, al treilea așteaptă"
    )
    assert motor.stare_flux(ids[2]).stare is motor.StareJob.IN_COADA  # type: ignore[union-attr]

    cozi.elibereaza("g1")  # se eliberează un culoar
    cozi.asteapta_pornirea("g3")
    assert sorted(cozi.pornite()) == ["g1", "g2", "g3"]
    cozi.elibereaza("g2", "g3")
    asteapta_toate(*ids)


def test_un_singur_culoar_inseamna_un_singur_job_greu(porneste_executor: Pornire) -> None:
    porneste_executor(culoare_greu=1)
    ids = [trimite(n, Coada.GREU) for n in ("u1", "u2")]
    cozi.asteapta_pornirea("u1")
    time.sleep(SONDARI)
    assert cozi.pornite() == ["u1"]
    cozi.elibereaza("u1")
    cozi.asteapta_pornirea("u2")
    cozi.elibereaza("u2")
    asteapta_toate(*ids)


def test_joburile_grele_nu_ocupa_celelalte_cozi(porneste_executor: Pornire) -> None:
    """Culoarele grele sunt ale cozii `greu`: un job `io` și unul `urgent` pornesc cu ambele culoare ocupate."""
    porneste_executor(culoare_greu=2)
    grele = [trimite(n, Coada.GREU) for n in ("h1", "h2")]
    cozi.asteapta_pornirea("h1")
    cozi.asteapta_pornirea("h2")
    urgent = motor.trimite(
        cozi.job, "urgent1", coada=Coada.URGENT, prioritate=Prioritate.P0, cheie="cozi-urgent1"
    )
    io = motor.trimite(cozi.job, "io1", coada=Coada.IO, cheie="cozi-io1")
    asteapta_toate(urgent, io)
    cozi.elibereaza("h1", "h2")
    asteapta_toate(*grele)


# ---- io, învățare ----------------------------------------------------------------------------------------------------------


def test_coada_io_respecta_numarul_de_joburi_in_paralel(porneste_executor: Pornire) -> None:
    porneste_executor(io_paralel=3)
    ids = [trimite(f"i{n}", Coada.IO) for n in range(4)]
    for n in range(3):
        cozi.asteapta_pornirea(f"i{n}")
    time.sleep(SONDARI)
    assert len(cozi.pornite()) == 3
    cozi.elibereaza("i0")
    cozi.asteapta_pornirea("i3")
    cozi.elibereaza("i1", "i2", "i3")
    asteapta_toate(*ids)


def test_invatarea_ruleaza_cate_un_job_implicit(porneste_executor: Pornire) -> None:
    porneste_executor()
    ids = [trimite(n, Coada.INVATARE, prioritate=Prioritate.P3) for n in ("l1", "l2")]
    cozi.asteapta_pornirea("l1")
    time.sleep(SONDARI)
    assert cozi.pornite() == ["l1"]
    cozi.elibereaza("l1")
    cozi.asteapta_pornirea("l2")
    cozi.elibereaza("l2")
    asteapta_toate(*ids)


# ---- priorități ------------------------------------------------------------------------------------------------------------


def test_prioritatile_si_termenele_hotarasc_ordinea_pornirii(porneste_executor: Pornire) -> None:
    """Un culoar, ocupat de un job de blocare; în coadă intră, amestecate, joburi de toate clasele. Când culoarul se
    eliberează, pornesc P0, apoi P1 în ordinea termenelor (cu termen înaintea celor fără), apoi P2, apoi P3."""
    porneste_executor(culoare_greu=1)
    acum = dt.datetime.now(dt.UTC)
    ids = [trimite("blocaj", Coada.GREU)]
    cozi.asteapta_pornirea("blocaj")
    intrari = [  # (nume, prioritate, termen) în ordine „greșită” intenționat
        ("p3", Prioritate.P3, None),
        ("p1_fara_termen", Prioritate.P1, None),
        ("p1_peste_2h", Prioritate.P1, acum + dt.timedelta(hours=2)),
        ("p2", Prioritate.P2, acum + dt.timedelta(hours=1)),
        ("p1_peste_1h", Prioritate.P1, acum + dt.timedelta(hours=1)),
        ("p0_peste_20h", Prioritate.P0, acum + dt.timedelta(hours=20)),
        ("p0_peste_3h", Prioritate.P0, acum + dt.timedelta(hours=3)),
    ]
    for nume, prio, termen in intrari:
        ids.append(trimite(nume, Coada.GREU, prioritate=prio, termen=termen))
    cozi.elibereaza_tot()  # blocajul pleacă; ceilalți se execută pe rând (un singur culoar)
    asteapta_toate(*ids)
    assert cozi.pornite() == [
        "blocaj",
        "p0_peste_3h",
        "p0_peste_20h",
        "p1_peste_1h",
        "p1_peste_2h",
        "p1_fara_termen",
        "p2",
        "p3",
    ]


def test_in_aceeasi_prioritate_si_acelasi_termen_ordinea_este_a_sosirii(porneste_executor: Pornire) -> None:
    porneste_executor(culoare_greu=1)
    termen = dt.datetime.now(dt.UTC) + dt.timedelta(hours=5)
    ids = [trimite("blocaj", Coada.GREU)]
    cozi.asteapta_pornirea("blocaj")
    nume = [f"s{n}" for n in range(4)]
    for n in nume:
        ids.append(trimite(n, Coada.GREU, termen=termen))
        time.sleep(0.02)
    cozi.elibereaza_tot()
    asteapta_toate(*ids)
    assert cozi.pornite() == ["blocaj", *nume]


# ---- limite de rată și cozile de furnizor ----------------------------------------------------------------------------------


def test_coada_de_furnizor_aplica_limita_de_rata(porneste_executor: Pornire) -> None:
    """Cel mult 2 porniri pe fereastră de 1,5 s: primele două imediat, următoarele abia după ce fereastra trece."""
    motor.declara_coada(motor.coada_furnizor("proba", cereri=2, perioada_sec=1.5))
    porneste_executor()
    ids = [motor.trimite(cozi.job, f"r{n}", coada="furnizor_proba", cheie=f"cozi-r{n}") for n in range(4)]
    cozi.asteapta_pornirea("r0")
    cozi.asteapta_pornirea("r1")
    time.sleep(SONDARI)
    assert len(cozi.pornite()) == 2, "limita de rată oprește al treilea job în fereastra curentă"
    asteapta_toate(*ids)
    primul = cozi.MOMENTE["r0"]
    assert cozi.MOMENTE["r2"] - primul >= 1.4, "al treilea a pornit abia după trecerea ferestrei"
    assert len(cozi.pornite()) == 4


def test_o_coada_declarata_dupa_pornire_se_inregistreaza_pe_loc(porneste_executor: Pornire) -> None:
    porneste_executor()
    motor.declara_coada(motor.coada_platforma("proba", cereri=50, perioada_sec=60, paralel=1))
    asteapta_toate(motor.trimite(cozi.job, "plat1", coada="platforma_proba", cheie="cozi-plat1"))


def test_cozile_fixe_nu_se_pot_redeclara() -> None:
    with pytest.raises(ValueError, match="fixe"):
        motor.declara_coada(motor.DefinitieCoada("greu", paralel_global=99))


# ---- configurarea din bază -------------------------------------------------------------------------------------------------


def randuri_cozi(admin: Engine) -> dict[str, tuple[int | None, int | None]]:
    with admin.connect() as c:
        return {
            r[0]: (r[1], r[2])
            for r in c.execute(text("SELECT name, concurrency, worker_concurrency FROM dbos.queues"))
        }


def test_cozile_standard_sunt_scrise_in_baza_si_se_actualizeaza_la_repornire(
    porneste_executor: Pornire, admin_engine: Engine
) -> None:
    porneste_executor(culoare_greu=2)
    r = randuri_cozi(admin_engine)
    assert (
        r["greu"] == (2, 2)
        and r["io"] == (24, 24)
        and r["invatare"] == (1, 1)
        and r["urgent"] == (None, None)
    )
    motor.opreste(0)
    porneste_executor(culoare_greu=3)  # schimbarea configurării se aplică la repornirea workerului
    assert randuri_cozi(admin_engine)["greu"] == (3, 3)
