"""F10.1 — colectorul de metrici. „Gata când”: metricile unei postări apar la fiecare interval (1 oră,
24 de ore, 72 de ore, 7 zile, 28 de zile). Postarea pleacă prin executorul de efecte pe platforma FALSĂ
(# SIMULAT), cifrele le dă cititorul fals, iar ceasul colectorului e controlat din test."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from app import productie
from app.analiza import colector
from app.analiza.colector import MetriciRefuzate
from app.connectors import metrici as registru_metrici
from app.connectors import registru
from app.connectors.metrici.fals import CititorFals, MetriciFalse
from app.connectors.publicare import DepozitBaza
from app.connectors.publicare.fals import ConectorFalsPublicare, PlatformaFalsa
from app.db import sesiune_tenant
from app.operare import efecte, motor
from app.operare.efecte import autorizare
from tests.integration.publicare_utile import autorizeaza, cere, efect, livrabil_stare
from tests.integration.utile_productie import (  # noqa: F401
    fabrica_clienti,
    livrabil_in_publicare,
    om,
    tenant,
)

pytestmark = pytest.mark.db
H = dt.timedelta(hours=1)
Z = dt.timedelta(days=1)


@dataclass
class Lume:
    platforma: PlatformaFalsa
    cifre: MetriciFalse


@pytest.fixture
def lume() -> Iterator[Lume]:
    registru.uita_tot()
    registru_metrici.uita_tot()
    p, m = PlatformaFalsa(), MetriciFalse()
    registru.inregistreaza("facebook", ConectorFalsPublicare(p, DepozitBaza(), canal="facebook"))
    registru_metrici.inregistreaza("facebook", CititorFals(m, DepozitBaza(), canal="facebook"))
    yield Lume(p, m)
    registru.uita_tot()
    registru_metrici.uita_tot()


def publica(tenant: uuid.UUID, om: uuid.UUID, lume: Lume, text: str = "Cafeneaua Zorilor") -> efecte.Efect:
    """O postare plecată prin API: livrabilul ajunge „publicat”, efectul are identificatorul platformei."""
    with sesiune_tenant(tenant) as db:
        from app.publicare import canale

        if canale.cont(db, tenant, "facebook") is None:
            autorizat = False
        else:
            autorizat = canale.token_pentru(tenant, "facebook") is not None
    if not autorizat:
        autorizeaza(tenant, om, "facebook", lume.platforma.cod_valid())
    lid = livrabil_in_publicare(tenant, om, canal="facebook")
    eid = cere(tenant, lid, {"text": text})
    assert efecte.incearca_efect(tenant, eid) == "trimis"
    e = efect(tenant, eid)
    assert e.id_extern and e.trimis_la is not None
    return e


def randuri(tenant: uuid.UUID, lid: uuid.UUID) -> dict[str, tuple[str, dict[str, int]]]:
    with sesiune_tenant(tenant) as db:
        return {r.interval: (r.stare, dict(r.valori)) for r in colector.ale_livrabilului(db, lid)}


def test_metricile_unei_postari_apar_la_fiecare_interval(
    tenant: uuid.UUID, om: uuid.UUID, lume: Lume
) -> None:
    e = publica(tenant, om, lume)
    t0, ext = e.trimis_la, str(e.id_extern)
    assert t0 is not None
    colector.colecteaza(t0 + 30 * dt.timedelta(minutes=1))
    assert randuri(tenant, e.livrabil_id) == {}, "înainte de prima oră nu se citește nimic"
    assert livrabil_stare(tenant, e.livrabil_id) == "publicat"

    asteptat: dict[str, tuple[str, dict[str, int]]] = {}
    pasi = [
        ("1h", H, 120),
        ("24h", 24 * H, 900),
        ("72h", 72 * H, 1400),
        ("7z", 7 * Z, 1900),
        ("28z", 28 * Z, 2300),
    ]
    for cod, dupa, afisari in pasi:
        lume.cifre.pune(ext, afisari=afisari, aprecieri=afisari // 20, comentarii=3)
        acum = t0 + dupa + 5 * dt.timedelta(minutes=1)
        colector.colecteaza(acum)
        asteptat[cod] = ("citit", {"afisari": afisari, "aprecieri": afisari // 20, "comentarii": 3})
        assert randuri(tenant, e.livrabil_id) == asteptat
        n = len(lume.cifre.citiri)
        colector.colecteaza(acum + 10 * dt.timedelta(minutes=1))
        assert len(lume.cifre.citiri) == n, "un interval citit nu se mai citește"
    assert livrabil_stare(tenant, e.livrabil_id) == "in_masurare", "prima citire mută livrabilul în măsurare"
    with sesiune_tenant(tenant) as db:
        toate = colector.ale_livrabilului(db, e.livrabil_id)
        assert [r.interval for r in toate] == ["1h", "24h", "72h", "7z", "28z"]
        assert all(r.sursa == "api" and r.intarziere_s == 300 and r.id_extern == ext for r in toate)
        assert colector.ultimele(db, e.livrabil_id, "facebook")["afisari"] == 2300
        assert colector.completitudine(db, tenant) == {"citit": 5, "ratat": 0, "indisponibil": 0}
    colector.colecteaza(t0 + 40 * Z)
    assert len(randuri(tenant, e.livrabil_id)) == 5


def test_un_interval_ratat_nu_primeste_cifre_tarzii(tenant: uuid.UUID, om: uuid.UUID, lume: Lume) -> None:
    e = publica(tenant, om, lume)
    t0 = e.trimis_la
    assert t0 is not None
    lume.cifre.pune(str(e.id_extern), afisari=700)
    # colectorul a fost oprit în primele 26 de ore
    colector.colecteaza(t0 + 26 * H)
    assert randuri(tenant, e.livrabil_id) == {"1h": ("ratat", {}), "24h": ("citit", {"afisari": 700})}
    with sesiune_tenant(tenant) as db:
        r24 = next(r for r in colector.ale_livrabilului(db, e.livrabil_id) if r.interval == "24h")
        assert r24.intarziere_s == 2 * 3600
        assert colector.completitudine(db, tenant) == {"citit": 1, "ratat": 1, "indisponibil": 0}


def test_eroarea_temporara_se_reincearca_iar_postarea_stearsa_e_indisponibila(
    tenant: uuid.UUID, om: uuid.UUID, lume: Lume
) -> None:
    e = publica(tenant, om, lume)
    t0, ext = e.trimis_la, str(e.id_extern)
    assert t0 is not None
    lume.cifre.pune(ext, afisari=50)
    lume.cifre.injecteaza("temporar")
    assert colector.citeste_postarea(tenant, e.livrabil_id, "facebook", ext, t0, t0 + H) == "amanat"
    assert randuri(tenant, e.livrabil_id) == {}
    assert (
        colector.citeste_postarea(
            tenant, e.livrabil_id, "facebook", ext, t0, t0 + H + 10 * dt.timedelta(minutes=1)
        )
        == "citit:1h"
    )
    # la 24 de ore postarea a fost ștearsă de pe platformă
    lume.cifre.valori.clear()
    assert (
        colector.citeste_postarea(tenant, e.livrabil_id, "facebook", ext, t0, t0 + 24 * H)
        == "indisponibil:24h"
    )
    r = randuri(tenant, e.livrabil_id)
    assert r["1h"] == ("citit", {"afisari": 50}) and r["24h"] == ("indisponibil", {})
    n = len(lume.cifre.citiri)
    assert colector.citeste_postarea(tenant, e.livrabil_id, "facebook", ext, t0, t0 + 25 * H) == "nimic"
    assert len(lume.cifre.citiri) == n, "o întrebare pe interval, nu una la fiecare rulare"


def test_canalul_pe_pauza_si_tokenul_respins_nu_se_citesc(
    tenant: uuid.UUID, om: uuid.UUID, lume: Lume
) -> None:
    e = publica(tenant, om, lume)
    t0, ext = e.trimis_la, str(e.id_extern)
    assert t0 is not None
    lume.cifre.pune(ext, afisari=10)
    lume.cifre.injecteaza("autentificare")
    assert colector.citeste_postarea(tenant, e.livrabil_id, "facebook", ext, t0, t0 + H) == "amanat"
    with sesiune_tenant(tenant) as db:
        assert autorizare.pune_pe_pauza(db, tenant, "facebook", "test")
    assert colector.citeste_postarea(tenant, e.livrabil_id, "facebook", ext, t0, t0 + H) == "amanat"
    assert lume.cifre.citiri == [] and randuri(tenant, e.livrabil_id) == {}


def test_canalul_fara_cititor_primeste_cifre_introduse_de_om(
    tenant: uuid.UUID, om: uuid.UUID, lume: Lume
) -> None:
    e = publica(tenant, om, lume)
    t0 = e.trimis_la
    assert t0 is not None
    registru_metrici.uita_tot()  # canal fără citire prin API (ca unul asistat)
    colector.colecteaza(t0 + 2 * H)
    assert randuri(tenant, e.livrabil_id) == {}
    with sesiune_tenant(tenant) as db:
        r = colector.inregistreaza_manual(
            db, e.livrabil_id, "facebook", "24h", {"afisari": 310, "clicuri": 12}, utilizator_id=om,
            acum=t0 + 30 * H,
        )  # fmt: skip
        assert (r.stare, r.sursa, r.introdus_de, r.intarziere_s) == ("citit", "manual", om, 6 * 3600)
        # corectarea unei cifre introduse greșit e permisă
        colector.inregistreaza_manual(
            db, e.livrabil_id, "facebook", "24h", {"afisari": 320}, utilizator_id=om
        )
        for gresit in ({"afisari": -5}, {"inventata": 1}, {}):
            with pytest.raises(MetriciRefuzate):
                colector.inregistreaza_manual(db, e.livrabil_id, "facebook", "24h", gresit, utilizator_id=om)
        with pytest.raises(MetriciRefuzate):
            colector.inregistreaza_manual(
                db, e.livrabil_id, "facebook", "2h", {"afisari": 1}, utilizator_id=om
            )
        with pytest.raises(MetriciRefuzate):  # nepublicat pe acest canal
            colector.inregistreaza_manual(
                db, e.livrabil_id, "instagram", "24h", {"afisari": 1}, utilizator_id=om
            )
    assert randuri(tenant, e.livrabil_id) == {"24h": ("citit", {"afisari": 320})}
    assert livrabil_stare(tenant, e.livrabil_id) == "in_masurare"


def test_cifrele_citite_prin_api_nu_se_inlocuiesc_de_mana(
    tenant: uuid.UUID, om: uuid.UUID, lume: Lume
) -> None:
    e = publica(tenant, om, lume)
    t0 = e.trimis_la
    assert t0 is not None
    lume.cifre.pune(str(e.id_extern), afisari=99)
    colector.colecteaza(t0 + H)
    with sesiune_tenant(tenant) as db, pytest.raises(MetriciRefuzate):
        colector.inregistreaza_manual(
            db, e.livrabil_id, "facebook", "1h", {"afisari": 5000}, utilizator_id=om
        )
    assert randuri(tenant, e.livrabil_id)["1h"] == ("citit", {"afisari": 99})


def test_fiecare_client_isi_vede_doar_metricile_lui(
    fabrica_clienti: object, om: uuid.UUID, lume: Lume
) -> None:
    a, b = fabrica_clienti(), fabrica_clienti()  # type: ignore[operator]
    ea, eb = publica(a, om, lume, "postarea A"), publica(b, om, lume, "postarea B")
    assert ea.trimis_la is not None and eb.trimis_la is not None
    lume.cifre.pune(str(ea.id_extern), afisari=11)
    lume.cifre.pune(str(eb.id_extern), afisari=22)
    colector.colecteaza(max(ea.trimis_la, eb.trimis_la) + H)
    assert randuri(a, ea.livrabil_id) == {"1h": ("citit", {"afisari": 11})}
    assert randuri(b, eb.livrabil_id) == {"1h": ("citit", {"afisari": 22})}
    assert randuri(a, eb.livrabil_id) == {}, "clientul A nu vede citirile clientului B"
    with sesiune_tenant(a) as db:
        assert colector.completitudine(db, a)["citit"] == 1


def test_jobul_este_declarat_si_incarcat_de_worker() -> None:
    from app import worker

    assert "app.analiza.colector" in worker.MODULE_FLUXURI
    colector.declara_programari()
    p = next(p for p in motor.programari_declarate() if p.nume == colector.NUME)
    assert "/10" in p.cron, "colectorul rulează la 10 minute"
    assert productie.Stare.IN_MASURARE in productie.stari.TABEL[productie.Stare.PUBLICAT]
