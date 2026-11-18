"""F16.6 — contul de reclame TikTok pe Marketing API simulat (# SIMULAT): citirea cu paginare, starea contului,
clasificarea erorilor din `code`, scrierea idempotentă, tokenul doar în `Access-Token`."""

import datetime as dt
import json

import pytest

from app.connectors.contract import Token
from app.connectors.publicare.baza import DepozitInMemorie
from app.connectors.reclame import ContReclameApi
from app.connectors.reclame.tiktok import CANAL_TOKEN, ContTiktok
from app.ids import new_id
from app.operare.motor import EroareAutentificare, EroareDefinitiva, EroareTemporara
from tests.platforme.tiktok_ads import TiktokAdsSimulat

CREARE = {"platforma": "tiktok", "cont_extern": "7000123", "actiune": "creeaza_campanie", "nume": "Audit · scalare",
          "obiectiv": "lead", "buget_zilnic_bani": 6400,
          "reclame": [{"nume": "r1", "titlu": "Audit gratuit", "text": "Află unde pierzi clienți.",
                       "link": "https://agentie.example/audit"}]}  # fmt: skip


def mediu() -> tuple[ContTiktok, TiktokAdsSimulat, object, str]:
    sim, d, t = TiktokAdsSimulat(), DepozitInMemorie(), new_id()
    tok = sim.token_nou("act")
    d.pune(t, CANAL_TOKEN, Token(acces=tok))
    return ContTiktok(depozit=d, transport=sim.transport), sim, t, tok


def test_citirea_pe_pagini_in_bani() -> None:
    c, sim, t, tok = mediu()
    for i, zi in enumerate(("2026-11-15", "2026-11-16", "2026-11-17")):
        sim.adauga_rand("campanie", "111", zi, f"{10 + i}.25", 1000, 30, 2, nume="Audit")
    sim.adauga_rand("reclama", "222", "2026-11-17", "3.10", 400, 9, 1, nume="r1", campanie="111")
    r = c.rezultate(t, "7000123", dt.date(2026, 11, 15), dt.date(2026, 11, 17))  # type: ignore[arg-type]
    camp = [x for x in r if x.nivel == "campanie"]
    assert [x.cheltuiala_bani for x in camp] == [1025, 1125, 1225], "trei rânduri, pe două pagini"
    [rc] = [x for x in r if x.nivel == "reclama"]
    assert (rc.id_extern, rc.parinte_extern, rc.rezultate, rc.cheltuiala_bani) == ("222", "111", 1, 310)
    assert all(tok not in a for a in sim.adrese)
    assert c.stare_cont(t, "7000123").activ  # type: ignore[arg-type]
    sim.stare_cont = "STATUS_DISABLE"
    assert not c.stare_cont(t, "7000123").activ  # type: ignore[arg-type]


def test_scrierea_e_idempotenta_si_campania_porneste_oprita() -> None:
    c, sim, t, _ = mediu()
    assert isinstance(c, ContReclameApi)
    r = c.scrie(t, CREARE)  # type: ignore[arg-type]
    assert (
        sim.campanii[r.id_extern]["operation_status"] == "DISABLE"
        and sim.campanii[r.id_extern]["budget"] == 64.0
    )
    assert c.scrie(t, CREARE).id_extern == r.id_extern and len(sim.reclame) == 1, "reîncercarea nu dublează"  # type: ignore[arg-type]
    assert set(json.loads(r.link)["reclame"]) == {"r1"}
    baza = {"platforma": "tiktok", "cont_extern": "7000123", "obiect_extern": r.id_extern}
    c.scrie(t, baza | {"actiune": "stare_campanie", "stare": "activa"})  # type: ignore[arg-type]
    c.scrie(t, baza | {"actiune": "buget_campanie", "buget_zilnic_bani": 5000})  # type: ignore[arg-type]
    assert (
        sim.campanii[r.id_extern]["operation_status"] == "ENABLE"
        and sim.campanii[r.id_extern]["budget"] == 50.0
    )
    a = c.scrie(
        t,
        baza
        | {"actiune": "creeaza_anunt", "nume": "r2", "titlu": "T", "text": "X", "link": "https://a.example"},
    )  # type: ignore[arg-type]
    c.scrie(t, baza | {"actiune": "stare_anunt", "obiect_extern": a.id_extern, "stare": "pauza"})  # type: ignore[arg-type]
    assert sim.reclame[a.id_extern]["operation_status"] == "DISABLE"


@pytest.mark.parametrize(
    ("defect", "eroare"), [("temporar", EroareTemporara), ("definitiv", EroareDefinitiva)]
)
def test_erorile_din_code(defect: str, eroare: type[Exception]) -> None:
    c, sim, t, _ = mediu()
    sim.injecteaza(defect)
    with pytest.raises(eroare):
        c.scrie(t, CREARE)  # type: ignore[arg-type]


def test_tokenul_revocat_e_autentificare() -> None:
    c, sim, t, _ = mediu()
    sim.expira_tokenul()
    with pytest.raises(EroareAutentificare):
        c.stare_cont(t, "7000123")  # type: ignore[arg-type]
