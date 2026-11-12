"""F3.3 — limitatoarele de cotă pe Postgres real: rezervare atomică, regularizare, rezerva pentru P0, antete ca
sursă de adevăr, blocaje după 429, corectitudine la concurență, persistență."""

import datetime as dt
import threading
from collections.abc import Callable

import pytest
from sqlalchemy import Engine

from app.db import reset_engine
from app.gateway import cote, limitator
from app.gateway.candidat import Candidat
from app.gateway.limitator import Refuz, Rezervare
from app.gateway.tipuri import AntetLimita
from app.operare.motor import Prioritate
from tests.gateway_utile import CeasControlat, FabricaModele, contor

pytestmark = pytest.mark.db
P1, P0 = Prioritate.P1, Prioritate.P0


@pytest.fixture
def model(fabrica_modele: FabricaModele) -> Callable[..., Candidat]:
    def fabrica(**limite: object) -> Candidat:
        f = fabrica_modele.furnizor()
        return fabrica_modele.model(f, **limite)

    return fabrica


def ok(r: Rezervare | Refuz) -> Rezervare:
    assert isinstance(r, Rezervare), r
    return r


def refuz(r: Rezervare | Refuz) -> Refuz:
    assert isinstance(r, Refuz), r
    return r


def test_apelul_se_opreste_la_limita_si_spune_cand_se_reseteaza(
    model: Callable[..., Candidat], ceas_controlat: CeasControlat
) -> None:
    m = model(cereri_minut=2)
    ok(limitator.rezerva(m, 100, P1))
    ok(limitator.rezerva(m, 100, P1))
    r = refuz(limitator.rezerva(m, 100, P1))
    assert r.pana_la == dt.datetime(2026, 11, 12, 12, 1, 1, tzinfo=dt.UTC) and not r.imposibil
    ceas_controlat.t = r.pana_la  # a început fereastra următoare
    ok(limitator.rezerva(m, 100, P1))


def test_limita_de_tokeni_pe_minut(model: Callable[..., Candidat], ceas_controlat: CeasControlat) -> None:
    m = model(tokeni_minut=1000)
    ok(limitator.rezerva(m, 600, P1))
    r = refuz(limitator.rezerva(m, 600, P1))
    assert "minut" in r.motiv and not r.imposibil
    ok(limitator.rezerva(m, 400, P1))  # încape exact în ce a rămas


def test_o_cerere_mai_mare_decat_limita_nu_se_amana_la_nesfarsit(model: Callable[..., Candidat]) -> None:
    m = model(tokeni_minut=1000)
    assert refuz(limitator.rezerva(m, 2000, P1)).imposibil


def test_zece_la_suta_din_limita_zilnica_ramane_pentru_p0(model: Callable[..., Candidat]) -> None:
    m = model(cereri_zi=10)
    for _ in range(9):
        ok(limitator.rezerva(m, 10, P1))
    r = refuz(limitator.rezerva(m, 10, Prioritate.P2))
    assert r.pana_la == dt.datetime(2026, 11, 13, 0, 0, 1, tzinfo=dt.UTC)  # resetarea zilnică, la 00:00 UTC
    ok(limitator.rezerva(m, 10, P0))  # rezerva este a lui P0
    refuz(limitator.rezerva(m, 10, P0))  # dar și P0 se oprește la limita întreagă


def test_o_rezervare_refuzata_nu_lasa_urme_pe_celelalte_contoare(
    fabrica_modele: FabricaModele, admin_engine: Engine
) -> None:
    f = fabrica_modele.furnizor(cereri_minut=1)  # contul permite o singură cerere pe minut
    a = fabrica_modele.model(f, identificator="a", cereri_minut=5)
    b = fabrica_modele.model(f, identificator="b", cereri_minut=5)
    ok(limitator.rezerva(a, 10, P1))
    refuz(limitator.rezerva(b, 10, P1))  # contul e plin
    assert contor(admin_engine, cote.cheie_model(b.model_id), "minut") == (0, 0)
    assert contor(admin_engine, cote.cheie_model(a.model_id), "minut") == (1, 10)
    assert contor(admin_engine, cote.cheie_furnizor(f), "minut") == (1, 10)


def test_regularizarea_inlocuieste_estimarea_cu_tokenii_reali(
    model: Callable[..., Candidat], admin_engine: Engine
) -> None:
    m = model(cereri_minut=10, tokeni_minut=10_000)
    rez = ok(limitator.rezerva(m, 1000, P1))
    assert contor(admin_engine, rez.cheie_model, "minut") == (1, 1000)
    limitator.regularizeaza(rez, 300)
    assert contor(admin_engine, rez.cheie_model, "minut") == (1, 300)
    rez2 = ok(limitator.rezerva(m, 100, P1))
    limitator.regularizeaza(rez2, 450)  # furnizorul a numărat mai mult decât am estimat
    assert contor(admin_engine, rez.cheie_model, "minut") == (2, 750)
    limitator.regularizeaza(ok(limitator.rezerva(m, 100, P1)), None)  # timeout: rămâne estimarea
    assert contor(admin_engine, rez.cheie_model, "minut") == (3, 850)


def test_regularizarea_ajunge_pe_fereastra_rezervarii_chiar_dupa_trecerea_minutului(
    model: Callable[..., Candidat], admin_engine: Engine, ceas_controlat: CeasControlat
) -> None:
    m = model(tokeni_minut=10_000)
    rez = ok(limitator.rezerva(m, 1000, P1))
    ceas_controlat.avanseaza(120)
    limitator.regularizeaza(rez, 200)
    assert contor(admin_engine, rez.cheie_model, "minut") == (1, 200)
    assert contor(admin_engine, rez.cheie_model, "zi") == (0, 0)  # modelul nu are limite zilnice: fără contor


def test_antetele_furnizorului_sunt_sursa_de_adevar(
    model: Callable[..., Candidat], admin_engine: Engine
) -> None:
    m = model(cereri_minut=10)
    ok(limitator.rezerva(m, 10, P1))  # noi am numărat 1
    limitator.corecteaza_din_antete(m, AntetLimita(ramas_cereri=2, limita_cereri=10))  # el spune: au rămas 2
    assert contor(admin_engine, cote.cheie_model(m.model_id), "minut")[0] == 8
    ok(limitator.rezerva(m, 10, P1))
    ok(limitator.rezerva(m, 10, P1))
    refuz(limitator.rezerva(m, 10, P1))
    # niciodată în jos: dacă el crede că a rămas mai mult decât credem noi, rămânem la numărătoarea noastră
    limitator.corecteaza_din_antete(m, AntetLimita(ramas_cereri=9, limita_cereri=10))
    assert contor(admin_engine, cote.cheie_model(m.model_id), "minut")[0] == 10


def test_antetele_pot_corecta_o_limita_pe_care_noi_nu_o_stiam(
    model: Callable[..., Candidat], admin_engine: Engine
) -> None:
    m = model()  # fără nicio limită în registru
    limitator.corecteaza_din_antete(m, AntetLimita(ramas_cereri=3, limita_cereri=10))
    assert contor(admin_engine, cote.cheie_model(m.model_id), "minut")[0] == 7


def test_ce_a_ajuns_la_zero_in_antete_blocheaza_pana_la_reset(
    model: Callable[..., Candidat], ceas_controlat: CeasControlat
) -> None:
    m = model(cereri_minut=100)
    reset = dt.datetime(2026, 11, 12, 12, 1, tzinfo=dt.UTC)  # resetul ferestrei de minut
    limitator.corecteaza_din_antete(m, AntetLimita(ramas_cereri=0, limita_cereri=100, reset_cereri_la=reset))
    r = refuz(limitator.rezerva(m, 10, P1))  # numărătoarea noastră ar fi lăsat; furnizorul a spus „gata”
    assert r.pana_la == reset + dt.timedelta(seconds=cote.MARJA_RESET_SEC)
    ceas_controlat.t = r.pana_la
    ok(limitator.rezerva(m, 10, P1))


def test_dupa_429_modelul_asteapta_cat_spune_furnizorul(
    model: Callable[..., Candidat], ceas_controlat: CeasControlat
) -> None:
    m = model(cereri_minut=100)
    pana = limitator.blocheaza_dupa_429(m, 7.0)
    assert pana == ceas_controlat.t + dt.timedelta(seconds=7 + cote.MARJA_RESET_SEC)
    assert refuz(limitator.rezerva(m, 10, P1)).pana_la == pana
    ceas_controlat.t = pana
    ok(limitator.rezerva(m, 10, P1))


def test_429_la_un_furnizor_cu_limita_pe_cont_blocheaza_toate_modelele_lui(
    fabrica_modele: FabricaModele, ceas_controlat: CeasControlat
) -> None:
    f = fabrica_modele.furnizor(parametri={"antete_cheie": "furnizor"})
    a = fabrica_modele.model(f, identificator="a")
    b = fabrica_modele.model(f, identificator="b")
    limitator.blocheaza_dupa_429(a, None)
    refuz(limitator.rezerva(b, 10, P1))  # limita e pe cont
    c = fabrica_modele.model(fabrica_modele.furnizor(), identificator="c")  # alt furnizor: neatins
    ok(limitator.rezerva(c, 10, P1))


def test_contoarele_se_reseteaza_odata_cu_fereastra_si_supravietuiesc_repornirii(
    model: Callable[..., Candidat], ceas_controlat: CeasControlat
) -> None:
    m = model(cereri_minut=1)
    ok(limitator.rezerva(m, 10, P1))
    reset_engine()  # „repornire”: conexiuni noi, același Postgres
    refuz(limitator.rezerva(m, 10, P1))
    ceas_controlat.avanseaza(60)
    ok(limitator.rezerva(m, 10, P1))


@pytest.mark.parametrize("axa", ["cereri", "tokeni"])
def test_la_concurenta_nu_se_depaseste_niciodata_limita(
    model: Callable[..., Candidat], admin_engine: Engine, axa: str
) -> None:
    """24 de fire, fiecare cu sesiunea (conexiunea) ei, ca 24 de lucrători: exact atâtea rezervări cât încap."""
    m = model(cereri_minut=7) if axa == "cereri" else model(tokeni_minut=700)
    tokeni = 10 if axa == "cereri" else 100
    rezultate: list[bool] = []
    bariera = threading.Barrier(24)

    def lucrator() -> None:
        bariera.wait()
        rezultate.append(isinstance(limitator.rezerva(m, tokeni, P1), Rezervare))

    fire = [threading.Thread(target=lucrator) for _ in range(24)]
    for f in fire:
        f.start()
    for f in fire:
        f.join()
    assert sum(rezultate) == 7 and len(rezultate) == 24
    cereri, tokeni_folositi = contor(admin_engine, cote.cheie_model(m.model_id), "minut")
    assert cereri == 7 and tokeni_folositi == 7 * tokeni


def test_curatarea_sterge_doar_ce_e_vechi(
    model: Callable[..., Candidat], ceas_controlat: CeasControlat
) -> None:
    m = model(cereri_minut=5)
    ok(limitator.rezerva(m, 10, P1))
    limitator.blocheaza_dupa_429(m, 1.0)
    assert limitator.curata() == 0
    ceas_controlat.avanseaza(4 * 24 * 3600)
    assert limitator.curata() >= 2
    assert limitator.curata() == 0
