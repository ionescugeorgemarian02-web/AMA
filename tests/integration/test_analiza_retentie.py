"""F10.2 — curba de retenție YouTube. „Gata când”: curba unui clip propriu se vede în panou. Clipul pleacă
prin executor pe platforma FALSĂ (# SIMULAT); cifrele și curba le dau cititorii falși; ceasul colectorului e
controlat. Tot aici: ecranul „Rapoarte și analiză” cu cifrele pe intervale și introducerea lor de mână."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.analiza import colector, retentie
from app.connectors import metrici as registru_metrici
from app.connectors import registru
from app.connectors.metrici.fals import CititorFals, CititorRetentieFals, MetriciFalse, RetentieFalsa
from app.connectors.publicare import DepozitBaza
from app.connectors.publicare.fals import ConectorFalsPublicare, PlatformaFalsa
from app.conturi import Rol
from app.db import sesiune_tenant
from app.operare import efecte
from tests.integration.conftest import Cont
from tests.integration.publicare_utile import autorizeaza, cere, efect
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import (  # noqa: F401
    fabrica_clienti,
    livrabil_in_publicare,
    om,
    tenant,
)

pytestmark = pytest.mark.db
H = dt.timedelta(hours=1)
CURBA = [(i / 100, round(1.0 - 0.5 * (i / 100) ** 0.5, 4)) for i in range(1, 101)]


@dataclass
class Lume:
    platforma: PlatformaFalsa
    cifre: MetriciFalse
    curbe: RetentieFalsa


@pytest.fixture
def lume() -> Iterator[Lume]:
    registru.uita_tot()
    registru_metrici.uita_tot()
    p, m, r = PlatformaFalsa(), MetriciFalse(), RetentieFalsa()
    registru.inregistreaza("youtube", ConectorFalsPublicare(p, DepozitBaza(), canal="youtube"))
    registru_metrici.inregistreaza("youtube", CititorFals(m, DepozitBaza(), canal="youtube"))
    registru_metrici.inregistreaza_retentie("youtube", CititorRetentieFals(r, DepozitBaza()))
    yield Lume(p, m, r)
    registru.uita_tot()
    registru_metrici.uita_tot()


def publica(tenant: uuid.UUID, om: uuid.UUID, lume: Lume) -> efecte.Efect:
    autorizeaza(tenant, om, "youtube", lume.platforma.cod_valid())
    lid = livrabil_in_publicare(tenant, om, canal="youtube", tip="video")
    eid = cere(tenant, lid, {"text": "Cafeneaua Zorilor: flat white în 30 de secunde"})
    assert efecte.incearca_efect(tenant, eid) == "trimis"
    return efect(tenant, eid)


def curba_tinuta(tenant: uuid.UUID, lid: uuid.UUID) -> tuple[str, int] | None:
    with sesiune_tenant(tenant) as db:
        c = retentie.a_livrabilului(db, lid)
        return None if c is None else (c.interval, len(c.puncte))


def test_curba_unui_clip_se_vede_in_panou(
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
    tenant: uuid.UUID,
    om: uuid.UUID,
    lume: Lume,
) -> None:
    e = publica(tenant, om, lume)
    t0, ext, lid = e.trimis_la, str(e.id_extern), e.livrabil_id
    assert t0 is not None
    lume.cifre.pune(ext, vizualizari=40, aprecieri=3)
    lume.curbe.curbe[ext] = CURBA
    colector.colecteaza(t0 + H)
    colector.colecteaza(t0 + 24 * H)
    assert lume.curbe.citiri == [] and curba_tinuta(tenant, lid) is None, (
        "la 1 oră și 24 de ore nu există curbă"
    )
    lume.cifre.pune(ext, vizualizari=900, aprecieri=61, comentarii=7)
    colector.colecteaza(t0 + 72 * H)
    assert curba_tinuta(tenant, lid) == ("72h", 100)

    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    r = client.get(f"/analiza/livrabil/{lid}")
    assert r.status_code == 200
    h = r.text
    assert "Curba de retenție" in h and "<polyline" in h and 'role="img"' in h
    linie, _ = retentie.linie_svg(CURBA)
    assert f'points="{linie}"' in h, "linia desenată e chiar curba citită"
    rez = retentie.rezumat(CURBA)
    assert (
        f"<strong>{rez.medie * 100:.0f}%</strong>" in h and f"<strong>{rez.la_final * 100:.0f}%</strong>" in h
    )
    assert "100 puncte" in h
    # cifrele pe intervale, pe aceeași pagină
    assert '<th scope="row">Vizualizări</th><td>40</td><td>40</td><td>900</td>' in h
    assert '<th scope="row">Comentarii</th><td>–</td><td>–</td><td>7</td>' in h, "cifra lipsă nu e zero"
    assert "urmează" in h
    # lista postărilor măsurate duce la pagină
    lista = client.get("/analiza").text
    assert f"/analiza/livrabil/{lid}" in lista and "vizualizări 900" in lista
    assert "/analiza" in client.get("/meniu").text
    assert client.get(f"/analiza/livrabil/{uuid.uuid4()}").status_code == 404
    assert client.get("/analiza/livrabil/nu-e-id").status_code == 404


def test_curba_se_improspateaza_iar_esecul_ei_nu_strica_cifrele(
    tenant: uuid.UUID, om: uuid.UUID, lume: Lume
) -> None:
    e = publica(tenant, om, lume)
    t0, ext, lid = e.trimis_la, str(e.id_extern), e.livrabil_id
    assert t0 is not None
    lume.cifre.pune(ext, vizualizari=10)
    # la 72 de ore platforma nu are încă destule puncte: cifrele se țin, curba nu
    lume.curbe.curbe[ext] = CURBA[:4]
    assert colector.citeste_postarea(tenant, lid, "youtube", ext, t0, t0 + 72 * H) == "citit:72h"
    assert curba_tinuta(tenant, lid) is None
    # la 7 zile curba există
    lume.curbe.curbe[ext] = CURBA
    assert colector.citeste_postarea(tenant, lid, "youtube", ext, t0, t0 + 7 * 24 * H) == "citit:7z"
    assert curba_tinuta(tenant, lid) == ("7z", 100)
    # la 28 de zile citirea curbei eșuează: rămâne cea veche, cifrele de la 28 de zile se țin
    lume.curbe.defecte.append("definitiv")
    assert colector.citeste_postarea(tenant, lid, "youtube", ext, t0, t0 + 28 * 24 * H) == "citit:28z"
    assert curba_tinuta(tenant, lid) == ("7z", 100)
    with sesiune_tenant(tenant) as db:
        assert [r.interval for r in colector.ale_livrabilului(db, lid) if r.stare == "citit"] == [
            "72h",
            "7z",
            "28z",
        ]
        assert retentie.numar(db, tenant) == 1


def test_cifrele_introduse_de_mana_din_panou(
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
    tenant: uuid.UUID,
    om: uuid.UUID,
    lume: Lume,
) -> None:
    e = publica(tenant, om, lume)
    lid = e.livrabil_id
    registru_metrici.uita_tot()  # canal fără citire prin API
    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    cale = f"/analiza/livrabil/{lid}"
    assert "Nicio citire încă" in client.get(cale).text
    jeton = csrf(client, cale)
    r = client.post(f"{cale}/metrici", data={"interval": "24h", "vizualizari": "1.250", "aprecieri": "40"})
    assert r.status_code == 403, "fără CSRF, refuz"
    r = client.post(
        f"{cale}/metrici",
        data={
            "csrf_token": jeton,
            "interval": "24h",
            "vizualizari": "1.250",
            "aprecieri": "40",
            "comentarii": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == f"{cale}?mesaj=salvat"
    h = client.get(r.headers["location"]).text
    assert "Cifrele au fost salvate." in h
    assert '<th scope="row">Vizualizări</th><td>–</td><td>1250</td>' in h and "de om" in h
    for gresit in (
        {"interval": "24h", "vizualizari": "multe"},
        {"interval": "24h"},
        {"interval": "2h", "vizualizari": "5"},
    ):
        r = client.post(f"{cale}/metrici", data={"csrf_token": jeton, **gresit})
        assert r.status_code == 422 and 'role="alert"' in r.text
    with sesiune_tenant(tenant) as db:
        [rand] = colector.ale_livrabilului(db, lid)
        assert (rand.sursa, rand.valori) == ("manual", {"vizualizari": 1250, "aprecieri": 40})


def test_analistul_citeste_dar_nu_introduce_cifre(
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
    tenant: uuid.UUID,
    om: uuid.UUID,
    lume: Lume,
) -> None:
    e = publica(tenant, om, lume)
    autentifica(client, fabrica_conturi(Rol.ANALIST, cu_totp=True), ceas)
    assert client.get("/analiza").status_code == 200
    jeton = csrf(client, "/analiza")
    r = client.post(
        f"/analiza/livrabil/{e.livrabil_id}/metrici",
        data={"csrf_token": jeton, "interval": "24h", "vizualizari": "5"},
    )
    assert r.status_code == 403
