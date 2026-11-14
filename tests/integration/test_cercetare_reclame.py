"""F10.8 — analistul de reclame ale concurenței. „Gata când”: pentru concurenții unui brand există harta
unghiurilor, cu reclamele care rulează de cel mai mult timp, iar un text prea apropiat de o reclamă observată
este blocat de G7. Biblioteca de reclame e SIMULATĂ (`httpx.MockTransport`)."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable

import httpx
import pytest
from fastapi.testclient import TestClient

from app import worker
from app.cercetare import reclame_concurenta as rc
from app.conturi import Rol
from app.db import sesiune_tenant
from app.operare import motor
from app.productie import Stare
from tests.gateway_utile import cheie_proba, fabrica_modele, fals  # noqa: F401
from tests.integration.conftest import Cont
from tests.integration.test_creier_cautare import Model, _mediu, indexeaza, model  # noqa: F401
from tests.integration.utile_panou import autentifica, config, csrf  # noqa: F401
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.validare_utile import LA, livrabil_in_validare, registru_doar, ruleaza

pytestmark = pytest.mark.db
TOKEN = "token-de-test-biblioteca"
RECLAMA_VECHE = (
    "Prăjim cafeaua în fiecare dimineață și o trimitem la ușa ta în cel mult două zile, cu reducere de "
    "douăzeci la sută pentru prima comandă făcută pe site."
)
BIBLIOTECA = {
    "111111": [
        {"id": "a1", "ad_creative_bodies": [RECLAMA_VECHE], "ad_delivery_start_time": "2026-06-01"},
        {
            "id": "a2",
            "ad_creative_bodies": ["Ultimele locuri la atelierul de sâmbătă"],
            "ad_delivery_start_time": "2026-11-01",
            "ad_delivery_stop_time": "2026-11-08",
        },
    ],
    "222222": [
        {
            "id": "b1",
            "ad_creative_bodies": ["Cafea de specialitate, proaspăt prăjită"],
            "ad_delivery_start_time": "2026-09-01",
        },
    ],
}


def biblioteca(cerere: httpx.Request) -> httpx.Response:
    assert cerere.headers["authorization"] == f"Bearer {TOKEN}" and TOKEN not in str(cerere.url)
    assert cerere.url.path.endswith("/ads_archive") and cerere.url.params["ad_reached_countries"] == '["RO"]'
    pagina = cerere.url.params["search_page_ids"]
    if pagina == "333333":
        return httpx.Response(500, json={"error": {"message": "eroare"}})
    return httpx.Response(200, json={"data": BIBLIOTECA.get(pagina, [])})


def test_harta_unghiurilor_si_blocarea_textului_prea_apropiat(
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
    config: Callable[..., None],
    fabrica_clienti: Callable[[], uuid.UUID],
    om: uuid.UUID,
) -> None:
    brand, alt_client = fabrica_clienti(), fabrica_clienti()
    config(meta_ad_library_token=TOKEN)
    with sesiune_tenant(brand) as db:
        rc.adauga_concurent(db, brand, nume="Prăjitoria Nordului", pagina_meta="111111", utilizator_id=om)
        rc.adauga_concurent(db, brand, nume="Cafeneaua Sud", pagina_meta="222222", utilizator_id=om)
        rc.adauga_concurent(db, brand, nume="Pagină Căzută", pagina_meta="333333", utilizator_id=om)
        for gresit in (
            {"nume": "X", "pagina_meta": "111111"},
            {"nume": "Dublură", "pagina_meta": "111111"},
            {"nume": "Litere", "pagina_meta": "abc"},
        ):
            with pytest.raises(rc.ConcurentInvalid):
                rc.adauga_concurent(db, brand, utilizator_id=om, **gresit)
    numar = rc.ruleaza(httpx.MockTransport(biblioteca))
    assert numar["reclame_noi"] >= 3 and numar["necititi"] >= 1, "o pagină căzută nu le oprește pe celelalte"
    assert rc.ruleaza(httpx.MockTransport(biblioteca))["reclame_noi"] == 0, "a doua rulare nu dublează"

    azi = dt.date(2026, 11, 14)
    with sesiune_tenant(brand) as db:
        h = rc.harta(db, brand, azi)
    assert h.pe_concurent == {
        "Prăjitoria Nordului": {"pret": 1, "urgenta": 1},
        "Cafeneaua Sud": {"calitate": 1},
    }
    assert [(c, r.id_extern, z) for c, r, z in h.de_durata][:2] == [
        ("Prăjitoria Nordului", "a1", 167),
        ("Cafeneaua Sud", "b1", 75),
    ]
    assert "garantie" in h.spatii_libere and "pret" not in h.spatii_libere
    with sesiune_tenant(alt_client) as db:
        assert rc.harta(db, alt_client, azi).reclame == 0, "clienții sunt separați"

    # G7: un text prea apropiat de reclama observată este blocat; unul original trece
    with registru_doar("G7"):
        copie = livrabil_in_validare(brand, "Noutate la noi! " + RECLAMA_VECHE + " Te așteptăm.")
        r = ruleaza(brand, copie, la=LA, judecatori=False, v4=False)
        assert r.stare is Stare.IN_REPARATIE
        [v] = [x for x in r.verdicte if x.validator == "G7" and x.treapta.value == "V1"]
        assert v.dovezi[0].regula == "G7.copiat_din_sursa" and "Prăjim cafeaua" in v.dovezi[0].fragment
        original = livrabil_in_validare(
            brand,
            "Sâmbătă la 11:00 facem degustare la cafenea: vino să guști trei origini și să alegi una pentru acasă.",
        )
        assert ruleaza(brand, original, la=LA, judecatori=False, v4=False).stare is Stare.VALIDAT

    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    h_html = client.get(f"/analiza/concurenta?client={brand}").text
    assert "Harta unghiurilor" in h_html and '<th scope="row">Prăjitoria Nordului</th>' in h_html
    assert "<strong>Spații libere</strong>" in h_html and "Garanție" in h_html
    assert "încă rulează" in h_html and "Prăjim cafeaua în fiecare dimineață" in h_html
    jeton = csrf(client, f"/analiza/concurenta?client={brand}")
    cale = f"/analiza/concurenta/{brand}/concurent"
    r2 = client.post(
        cale,
        data={"csrf_token": jeton, "nume": "Brutăria Est", "pagina_meta": "444444"},
        follow_redirects=False,
    )
    assert r2.status_code == 303
    assert (
        client.post(cale, data={"csrf_token": jeton, "nume": "Brutăria Est", "pagina_meta": "x"}).status_code
        == 422
    )
    assert client.post(cale, data={"nume": "Fără jeton", "pagina_meta": "555555"}).status_code == 403
    assert "/analiza/concurenta" in client.get("/analiza").text


def test_fara_token_nu_se_citeste_nimic_iar_jobul_e_declarat(
    tenant: uuid.UUID, om: uuid.UUID, config: Callable[..., None]
) -> None:
    config(meta_ad_library_token="")
    with sesiune_tenant(tenant) as db:
        rc.adauga_concurent(db, tenant, nume="Prăjitoria Nordului", pagina_meta="777777", utilizator_id=om)
    apeluri: list[httpx.Request] = []

    def nu_trebuie(cerere: httpx.Request) -> httpx.Response:
        apeluri.append(cerere)
        return httpx.Response(200, json={"data": []})

    numar = rc.ruleaza(httpx.MockTransport(nu_trebuie))
    assert numar["reclame_noi"] == 0 and numar["necititi"] >= 1 and apeluri == []
    assert "app.cercetare.reclame_concurenta" in worker.MODULE_FLUXURI
    rc.declara_programari()
    assert any(p.nume == rc.NUME for p in motor.programari_declarate())
