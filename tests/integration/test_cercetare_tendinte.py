"""F10.7 — cercetătorul de tendințe. „Gata când”: în fiecare dimineață apar fișe pentru nișa unui brand
propriu, iar un link lipit în inbox devine fișă și propunere de calendar. Sursele sunt SIMULATE (semnale și
pagini date de test, fără rețea)."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app import worker
from app.cercetare import tendinte
from app.cercetare.tendinte import Semnal
from app.conturi import Rol
from app.db import sesiune_tenant
from app.media import tendinte as inbox
from app.operare import motor
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401

pytestmark = pytest.mark.db
ZI = dt.date(2026, 11, 13)  # vineri
GENERALE = [
    Semnal("Prețul cafelei crește din nou", "google_tendinte", "https://trends.exemplu.test/1"),
    Semnal("Campionatul de fotbal", "google_tendinte"),
    Semnal("Accident la o prăjitorie de cafea", "google_tendinte"),
]
FLUX = b"""<rss><channel><item><title>Cre\xc8\x99te pre\xc8\x9bul cafelei</title>
<link>https://stiri.exemplu.test/cafea</link></item></channel></rss>"""
PAGINA = b"<html><head><title>Espresso tonic, bautura verii</title></head></html>"


def citeste(url: str) -> bytes:
    if url == "https://stiri.exemplu.test/flux.xml":
        return FLUX
    if url == "https://www.instagram.com/reel/abc":
        return PAGINA
    raise RuntimeError("adresă necunoscută în test")


def profil(t: uuid.UUID, om: uuid.UUID) -> None:
    with sesiune_tenant(t) as db:
        tendinte.seteaza_profil(
            db,
            t,
            termeni=["cafea", "espresso"],
            fluxuri=["https://stiri.exemplu.test/flux.xml"],
            utilizator_id=om,
        )


def test_dimineata_apar_fise_pentru_nisa_iar_linkul_din_inbox_devine_fisa_si_propunere(
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
    fabrica_clienti: Callable[[], uuid.UUID],
    om: uuid.UUID,
) -> None:
    cafenea, fara_profil = fabrica_clienti(), fabrica_clienti()
    profil(cafenea, om)
    with sesiune_tenant(cafenea) as db:
        legat = inbox.adauga(
            db, cafenea, "https://www.instagram.com/reel/abc formatul ăsta merge acum", utilizator_id=om
        )
        trist = inbox.adauga(db, cafenea, "să facem ceva despre tragedia de ieri", utilizator_id=om)
        ids = (legat.id, trist.id)

    numar = tendinte.ruleaza(ZI, generale=GENERALE, citeste=citeste)
    assert numar["fise"] >= 2 and numar["inbox"] >= 1
    with sesiune_tenant(cafenea) as db:
        fise = {f.subiect: f for f in tendinte.ale_clientului(db, cafenea)}
        stari_inbox = {t.id: t.stare for t in inbox.ale_clientului(db, cafenea)}
    pret = fise["Prețul cafelei crește din nou"]
    assert (pret.semnal, pret.risc, pret.origine, pret.stare) == ("confirmat", "scazut", "surse", "noua")
    assert {d["sursa"] for d in pret.dovezi} == {"google_tendinte", "rss:stiri.exemplu.test"}
    assert pret.valabil_pana == ZI + dt.timedelta(days=7) and pret.termeni_potriviti == ["cafea"]
    assert "Campionatul de fotbal" not in fise, "în afara nișei nu se scrie fișă"
    exclus = fise["Accident la o prăjitorie de cafea"]
    assert (exclus.risc, exclus.stare, exclus.unghi) == ("sensibil", "exclusa", "")
    din_link = fise["Espresso tonic, bautura verii"]
    assert (din_link.origine, din_link.semnal, din_link.risc) == ("inbox", "slab", "drepturi")
    assert din_link.inbox_id == ids[0] and din_link.dovezi[0]["url"] == "https://www.instagram.com/reel/abc"
    assert din_link.propunere == {
        "subiect": "Espresso tonic, bautura verii",
        "unghi": din_link.unghi,
        "zi": "2026-11-16",
        "tip": "postare",
    }
    assert stari_inbox == {ids[0]: "folosita", ids[1]: "ignorata"}, "observația despre o tragedie e exclusă"
    with sesiune_tenant(fara_profil) as db:
        assert tendinte.ale_clientului(db, fara_profil) == [], (
            "fără profil de nișă nu apar fișe; clienții sunt separați"
        )
    # a doua rulare în aceeași zi nu dublează nimic
    assert tendinte.ruleaza(ZI, generale=GENERALE, citeste=citeste) == {"fise": 0, "inbox": 0}

    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    h = client.get(f"/analiza/tendinte?client={cafenea}").text
    assert "Prețul cafelei crește din nou" in h and "confirmat" in h and "semnal slab" in h
    assert "exclus: subiect sensibil" in h and "atenție la drepturi" in h
    assert "<strong>Propunere de calendar:</strong> postare pe 2026-11-16" in h
    assert 'rel="noopener noreferrer nofollow"' in h
    cale = f"/analiza/tendinte/{cafenea}"
    jeton = csrf(client, f"/analiza/tendinte?client={cafenea}")
    r = client.post(
        f"{cale}/inbox", data={"csrf_token": jeton, "text": "cold brew la doză"}, follow_redirects=False
    )
    assert r.status_code == 303
    r = client.post(
        f"{cale}/profil",
        data={
            "csrf_token": jeton,
            "termeni": "cafea, cold brew",
            "fluxuri": "https://stiri.exemplu.test/flux.xml",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    with sesiune_tenant(cafenea) as db:
        p = tendinte.profil(db, cafenea)
        assert p is not None and p.termeni == ["cafea", "cold brew"]
    r = client.post(f"{cale}/profil", data={"csrf_token": jeton, "termeni": "cafea", "fluxuri": "ftp://x"})
    assert r.status_code == 422
    assert client.post(f"{cale}/profil", data={"termeni": "x"}).status_code == 403, "fără CSRF, refuz"
    assert client.get(f"/analiza/tendinte?client={uuid.uuid4()}").status_code == 404


def test_fluxul_cazut_nu_opreste_fisele_iar_jobul_e_declarat(tenant: uuid.UUID, om: uuid.UUID) -> None:
    with sesiune_tenant(tenant) as db:
        tendinte.seteaza_profil(
            db, tenant, termeni=["cafea"], fluxuri=["https://cazut.exemplu.test/rss"], utilizator_id=om
        )
    assert tendinte.ruleaza_client(tenant, ZI, GENERALE[:1], citeste=citeste) == 1
    with sesiune_tenant(tenant) as db:
        [f] = tendinte.ale_clientului(db, tenant)
        assert f.semnal == "slab", "o singură sursă = semnal slab"
    assert "app.cercetare.tendinte" in worker.MODULE_FLUXURI
    tendinte.declara_programari()
    assert any(p.nume == tendinte.NUME for p in motor.programari_declarate())
