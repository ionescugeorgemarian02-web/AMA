"""F10.3 — legarea de etichete. „Gata când”: poți sorta postările după tiparul de hook. Trei postări cu
tipare diferite pleacă prin executor (platformă FALSĂ, # SIMULAT), primesc cifre la 72 de ore și apar în
panou grupate pe tipar, cel mai bun primul."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app import continut
from app.analiza import colector, etichete
from app.connectors import metrici as registru_metrici
from app.connectors import registru
from app.connectors.metrici.fals import CititorFals, MetriciFalse
from app.connectors.publicare import DepozitBaza
from app.connectors.publicare.fals import ConectorFalsPublicare, PlatformaFalsa
from app.conturi import Rol
from app.db import sesiune_tenant
from app.ids import new_id
from app.operare import efecte
from tests.integration.conftest import Cont
from tests.integration.publicare_utile import autorizeaza, cere, efect
from tests.integration.utile_panou import autentifica
from tests.integration.utile_productie import (  # noqa: F401
    fabrica_clienti,
    livrabil_in_publicare,
    om,
    tenant,
)

pytestmark = pytest.mark.db
H = dt.timedelta(hours=1)


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


def calendar(tenant: uuid.UUID, om: uuid.UUID) -> uuid.UUID:
    with sesiune_tenant(tenant) as db:
        c = continut.Calendar(
            tenant_id=tenant,
            inceput=dt.date(2026, 11, 2),
            zile=28,
            strategie_intrare_id=new_id(),
            strategie_versiune=1,
            propunere={},
            creat_de=om,
        )
        db.add(c)
        db.flush()
        return c.id


def publica(
    tenant: uuid.UUID,
    om: uuid.UUID,
    lume: Lume,
    cal: uuid.UUID,
    nr: int,
    *,
    tipar: str,
    pilon: str,
    unghi: str,
) -> efecte.Efect:
    """O postare cu hook ales și intrare de calendar, plecată prin API."""
    lid = livrabil_in_publicare(tenant, om, canal="facebook")
    with sesiune_tenant(tenant) as db:
        db.add(
            continut.VariantaHook(
                tenant_id=tenant,
                livrabil_id=lid,
                nr=1,
                text=f"Deschiderea numărul {nr}",
                tipar=tipar,
                scor=10,
                ales=True,
            )
        )
        db.add(
            continut.VariantaHook(
                tenant_id=tenant,
                livrabil_id=lid,
                nr=2,
                text=f"Varianta nealeasă {nr}",
                tipar="poveste",
                scor=5,
            )
        )
        db.add(
            continut.IntrareCalendar(
                tenant_id=tenant,
                calendar_id=cal,
                nr=nr,
                slot_la=dt.datetime(2026, 11, 2 + nr, 7, 0, tzinfo=dt.UTC),
                canal="facebook",
                tip="postare",
                pilon=pilon,
                subiect=f"Subiectul postării {nr}",
                unghi=unghi,
                livrabil_id=lid,
            )
        )
    eid = cere(tenant, lid, {"text": f"Cafeneaua Zorilor, postarea {nr}"})
    assert efecte.incearca_efect(tenant, eid) == "trimis"
    return efect(tenant, eid)


def test_postarile_se_sorteaza_dupa_tiparul_de_hook(
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
    tenant: uuid.UUID,
    om: uuid.UUID,
    lume: Lume,
) -> None:
    autorizeaza(tenant, om, "facebook", lume.platforma.cod_valid())
    cal = calendar(tenant, om)
    date = [
        ("cifra", "Educație", "prețul corect", 1000, 20),  # 2 la 100
        ("intrebare", "Culise", "de ce prăjim local", 1000, 80),  # 8 la 100
        ("intrebare", "Educație", "prețul corect", 1000, 60),  # 6 la 100
        ("greseala", "Educație", "greșeli la espresso", 1000, 40),  # 4 la 100
    ]
    postari = []
    for nr, (tipar, pilon, unghi, afisari, aprecieri) in enumerate(date, start=1):
        e = publica(tenant, om, lume, cal, nr, tipar=tipar, pilon=pilon, unghi=unghi)
        lume.cifre.pune(str(e.id_extern), afisari=afisari, aprecieri=aprecieri, comentarii=0)
        postari.append(e)
    t0 = max(e.trimis_la for e in postari if e.trimis_la is not None)
    colector.colecteaza(t0 + 24 * H)
    with sesiune_tenant(tenant) as db:
        e1 = etichete.a_postarii(db, postari[0].livrabil_id, "facebook")
        assert e1 is not None and (e1.tipar_hook, e1.format, e1.pilon, e1.unghi) == (
            "cifra",
            "postare",
            "Educație",
            "prețul corect",
        )
        assert e1.recompensa is None, "înainte de 72 de ore există etichetele, dar nu și recompensa"
        assert (e1.zi_saptamana, e1.ora) == etichete.slot(e1.publicat_la)
    colector.colecteaza(t0 + 72 * H)
    with sesiune_tenant(tenant) as db:
        e1 = etichete.a_postarii(db, postari[0].livrabil_id, "facebook")
        assert e1 is not None
        assert (e1.recompensa, e1.recompensa_tip, e1.recompensa_interval) == (
            0.02,
            "interactiuni_pe_afisari",
            "72h",
        )
        grupuri = etichete.grupeaza(db, "tipar_hook", tenant_id=tenant)
        assert [(g.valoare, len(g.postari)) for g in grupuri] == [
            ("întrebare", 2),
            ("greșeală frecventă", 1),
            ("cifră", 1),
        ]
        assert grupuri[0].medii() == {"interactiuni_pe_afisari": (2, 0.07)}
        assert [p.recompensa for p in grupuri[0].postari] == [0.08, 0.06], "în grup, cea mai bună prima"
        pe_pilon = etichete.grupeaza(db, "pilon", tenant_id=tenant)
        assert [(g.valoare, len(g.postari)) for g in pe_pilon] == [("Culise", 1), ("Educație", 3)]
        assert [g.valoare for g in etichete.grupeaza(db, "format", tenant_id=tenant)] == ["postare"]
        with pytest.raises(ValueError):
            etichete.grupeaza(db, "inventata")

    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    r = client.get(f"/analiza/etichete?dupa=tipar_hook&client={tenant}")
    assert r.status_code == 200
    h = r.text
    pozitii = [h.index(f"<h2>{nume} ") for nume in ("întrebare", "greșeală frecventă", "cifră")]
    assert pozitii == sorted(pozitii), "grupurile apar de la cel mai bun tipar la cel mai slab"
    assert "Media: <strong>7.0 interacțiuni la 100 de afișări</strong> (din 2)" in h
    assert h.index("8.0 interacțiuni la 100 de afișări") < h.index("6.0 interacțiuni la 100 de afișări")
    assert f"/analiza/livrabil/{postari[1].livrabil_id}" in h
    assert '<option value="tipar_hook" selected>' in h
    h_slot = client.get(f"/analiza/etichete?dupa=slot&client={tenant}").text
    assert etichete.eticheta_slot(*etichete.slot(t0)) in h_slot
    assert client.get("/analiza/etichete?dupa=inventata").status_code == 422
    assert client.get("/analiza/etichete?client=nu-e-id").status_code == 422
    assert "/analiza/etichete" in client.get("/analiza").text


def test_recompensa_vine_din_prima_citire_de_dupa_72_de_ore_daca_aceea_lipseste(
    tenant: uuid.UUID, om: uuid.UUID, lume: Lume
) -> None:
    autorizeaza(tenant, om, "facebook", lume.platforma.cod_valid())
    e = publica(tenant, om, lume, calendar(tenant, om), 1, tipar="rezultat", pilon="Oferte", unghi="")
    t0, ext, lid = e.trimis_la, str(e.id_extern), e.livrabil_id
    assert t0 is not None
    lume.cifre.pune(ext, afisari=400, aprecieri=10, distribuiri=2)
    assert colector.citeste_postarea(tenant, lid, "facebook", ext, t0, t0 + 24 * H) == "citit:24h"
    # colectorul lipsește la 72 de ore; revine la 8 zile
    assert colector.citeste_postarea(tenant, lid, "facebook", ext, t0, t0 + 8 * 24 * H) == "citit:7z"
    with sesiune_tenant(tenant) as db:
        et = etichete.a_postarii(db, lid, "facebook")
        assert et is not None
        assert (et.recompensa, et.recompensa_interval) == (0.03, "7z")
        assert et.unghi == "" and etichete.valoare(et, "unghi") == etichete.NECUNOSCUT


def test_postarea_fara_hook_si_fara_calendar_ramane_fara_eticheta_iar_clientii_sunt_separati(
    fabrica_clienti: Callable[[], uuid.UUID], om: uuid.UUID, lume: Lume
) -> None:
    a, b = fabrica_clienti(), fabrica_clienti()
    rezultate = {}
    for t in (a, b):
        autorizeaza(t, om, "facebook", lume.platforma.cod_valid())
        lid = livrabil_in_publicare(t, om, canal="facebook")
        eid = cere(t, lid, {"text": f"postare {t}"})
        assert efecte.incearca_efect(t, eid) == "trimis"
        e = efect(t, eid)
        lume.cifre.pune(str(e.id_extern), aprecieri=4)  # fără afișări: nu există recompensă
        assert e.trimis_la is not None
        assert (
            colector.citeste_postarea(t, lid, "facebook", str(e.id_extern), e.trimis_la, e.trimis_la + 72 * H)
            == "citit:72h"
        )
        rezultate[t] = lid
    with sesiune_tenant(a) as db:
        [g] = etichete.grupeaza(db, "tipar_hook")
        assert g.valoare == etichete.NECUNOSCUT and [p.livrabil_id for p in g.postari] == [rezultate[a]]
        assert g.postari[0].recompensa is None and g.medii() == {}
        assert etichete.a_postarii(db, rezultate[b], "facebook") is None, "A nu vede etichetele lui B"
