"""F11.4 — registrul de experimente. „Gata când”: un experiment simplu rulează cap-coadă: declarat cu ipoteză,
variante, indicator și regulă de oprire; adună postările măsurate de după pornire; se încheie singur."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app import worker
from app.db import sesiune_tenant
from app.ids import new_id
from app.invatare import experimente
from app.invatare.experimente import ExperimentRefuzat
from app.operare import motor
from tests.integration.utile_productie import fabrica_clienti, livrabil, om, tenant  # noqa: F401

pytestmark = pytest.mark.db
SQL = (
    "INSERT INTO etichete_postari (id, tenant_id, livrabil_id, canal, publicat_la, tipar_hook, format, zi_saptamana, ora, "
    "recompensa, recompensa_tip, recompensa_interval) VALUES (:i, :t, :l, 'facebook', :la, :h, 'postare', 2, 9, :r, "
    "'interactiuni_pe_afisari', '72h')"
)
T0 = dt.datetime.now(dt.UTC) - dt.timedelta(days=30)


def postare(admin: Engine, t: uuid.UUID, tipar: str, r: float, la: dt.datetime) -> None:
    lid = livrabil(t)
    with admin.begin() as c:
        c.execute(text(SQL), {"i": new_id(), "t": t, "l": lid, "h": tipar, "r": r, "la": la})


def declara(t: uuid.UUID, om: uuid.UUID, **kw: object) -> uuid.UUID:
    with sesiune_tenant(t) as db:
        return experimente.declara(
            db,
            t,
            ipoteza="Hook-urile cu întrebare aduc mai multe interacțiuni decât cele cu cifră.",
            dimensiune="tipar_hook",
            varianta_a="intrebare",
            varianta_b="cifra",
            minim_pe_varianta=5,
            prag_diferenta=0.2,
            durata_maxima_zile=20,
            utilizator_id=om,
            acum=T0,
            **kw,  # type: ignore[arg-type]
        ).id


def test_un_experiment_simplu_ruleaza_cap_coada(
    fabrica_clienti: Callable[[], uuid.UUID], om: uuid.UUID, admin_engine: Engine
) -> None:
    t, alt = fabrica_clienti(), fabrica_clienti()
    postare(admin_engine, t, "intrebare", 0.50, T0 - dt.timedelta(days=3))  # dinaintea pornirii: nu intră
    eid = declara(t, om)
    with sesiune_tenant(t) as db:
        with pytest.raises(ExperimentRefuzat, match="o schimbare o dată"):
            experimente.declara(
                db, t, ipoteza="Alt experiment pe aceeași dimensiune.", dimensiune="tipar_hook",
                varianta_a="poveste", varianta_b="cifra", utilizator_id=om,
            )  # fmt: skip
        for gresit in ({"varianta_b": "intrebare"}, {"ipoteza": "scurt"}, {"dimensiune": "inventata"}):
            args = {
                "ipoteza": "O ipoteză destul de lungă.",
                "dimensiune": "slot",
                "varianta_a": "intrebare",
                "varianta_b": "cifra",
            }
            with pytest.raises(ExperimentRefuzat):
                experimente.declara(db, t, utilizator_id=om, **{**args, **gresit})  # type: ignore[arg-type]
    # săptămâna 1: date puține → continuă
    for i in range(3):
        postare(admin_engine, t, "intrebare", 0.08 + i * 0.005, T0 + dt.timedelta(days=1 + i))
        postare(admin_engine, t, "cifra", 0.03, T0 + dt.timedelta(days=1 + i))
    with sesiune_tenant(t) as db:
        e = experimente.evalueaza(db, eid, acum=T0 + dt.timedelta(days=7))
        assert (e.stare, e.concluzie, e.rezultat["n_a"], e.rezultat["n_b"]) == ("in_curs", None, 3, 3)
    # săptămâna 2: minimul e atins → se încheie singur, prin jobul zilnic
    for i in range(3):
        postare(admin_engine, t, "intrebare", 0.09 - i * 0.005, T0 + dt.timedelta(days=8 + i))
        postare(admin_engine, t, "cifra", 0.025 + i * 0.005, T0 + dt.timedelta(days=8 + i))
    postare(admin_engine, alt, "cifra", 0.99, T0 + dt.timedelta(days=9))  # alt client: nu intră
    assert experimente.ruleaza(T0 + dt.timedelta(days=12)) >= 1
    with sesiune_tenant(t) as db:
        [e] = experimente.ale_clientului(db, t)
        assert (e.stare, e.concluzie) == ("incheiat", "castiga_a")
        assert (e.rezultat["n_a"], e.rezultat["n_b"]) == (6, 6) and e.rezultat["medie_a"] > e.rezultat[
            "medie_b"
        ]
        assert e.incheiat_la == T0 + dt.timedelta(days=12)
        neschimbat = experimente.evalueaza(db, eid, acum=T0 + dt.timedelta(days=15))
        assert neschimbat.incheiat_la == T0 + dt.timedelta(days=12), "un experiment încheiat rămâne cum e"
    with sesiune_tenant(alt) as db:
        assert experimente.ale_clientului(db, alt) == []
    # după încheiere se poate declara altul pe aceeași dimensiune
    assert declara(t, om) != eid


def test_regulile_declarate_nu_se_schimba_iar_termenul_fara_date_e_neconcludent(
    tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    eid = declara(tenant, om)
    with pytest.raises(DBAPIError), admin_engine.begin() as c:  # nici măcar ca proprietar al bazei
        c.execute(text("UPDATE experimente SET minim_pe_varianta = 2 WHERE id = :i"), {"i": eid})
    postare(admin_engine, tenant, "intrebare", 0.09, T0 + dt.timedelta(days=2))
    with sesiune_tenant(tenant) as db:
        e = experimente.evalueaza(db, eid, acum=T0 + dt.timedelta(days=21))
        assert (e.stare, e.concluzie) == ("incheiat", "neconcludent") and e.rezultat["n_a"] == 1
    alt = declara(tenant, om)
    with sesiune_tenant(tenant) as db:
        with pytest.raises(ExperimentRefuzat):
            experimente.opreste(db, alt, utilizator_id=om, motiv="")
        assert experimente.opreste(db, alt, utilizator_id=om, motiv="schimbăm strategia").stare == "oprit"
        with pytest.raises(ExperimentRefuzat):
            experimente.opreste(db, alt, utilizator_id=om, motiv="încă o dată")
    assert "app.invatare" in worker.MODULE_FLUXURI
    experimente.declara_programari()
    assert any(p.nume == experimente.NUME for p in motor.programari_declarate())
