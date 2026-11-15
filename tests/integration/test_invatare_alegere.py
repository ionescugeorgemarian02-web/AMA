"""F11.3 — alegerea adaptivă citește recompensele reale ale clientului (postările etichetate, F10.3) și se
vede în preferința de tipar dată autorului de hook-uri."""

# ruff: noqa: F811, S311
import random
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import Engine, text

from app import productie
from app.continut import scriere
from app.db import sesiune_tenant
from app.ids import new_id
from app.invatare import alegere
from tests.integration.utile_productie import fabrica_clienti, livrabil, om, tenant  # noqa: F401

pytestmark = pytest.mark.db
SQL = (
    "INSERT INTO etichete_postari (id, tenant_id, livrabil_id, canal, publicat_la, tipar_hook, format, zi_saptamana, ora, "
    "recompensa, recompensa_tip, recompensa_interval) VALUES (:i, :t, :l, 'facebook', now() - make_interval(days => :z), "
    ":h, 'postare', :zi, 9, :r, 'interactiuni_pe_afisari', '72h')"
)


def postare(admin: Engine, t: uuid.UUID, tipar: str, r: float, *, zile: int = 5, zi: int = 2) -> None:
    lid = livrabil(t)
    with admin.begin() as c:
        c.execute(text(SQL), {"i": new_id(), "t": t, "l": lid, "h": tipar, "r": r, "z": zile, "zi": zi})


def test_variantele_clientului_si_preferinta_data_autorului(
    fabrica_clienti: Callable[[], uuid.UUID], admin_engine: Engine
) -> None:
    t, alt = fabrica_clienti(), fabrica_clienti()
    for _ in range(12):
        postare(admin_engine, t, "intrebare", 0.30, zi=4)
        postare(admin_engine, t, "cifra", 0.01, zi=2)
    postare(admin_engine, t, "poveste", 0.90, zile=200)  # mai veche de 90 de zile: nu contează
    with sesiune_tenant(t) as db:
        v = alegere.variante_client(db, t, "tipar_hook")
        assert [(x.valoare, x.publicari, x.de_incredere) for x in v] == [
            ("intrebare", 12, True),
            ("cifra", 12, True),
        ]
        assert v[0].medie > 0.2 > 0.05 > v[1].medie
        sloturi = alegere.variante_client(db, t, "slot")
        assert [s.valoare for s in sloturi] == ["joi, ora 09", "marți, ora 09"], "slotul bun întâi"
        alese = [
            alegere.recomanda(db, t, "tipar_hook", ["intrebare", "cifra"], random.Random(i))
            for i in range(200)
        ]
        assert alese.count("intrebare") > 150, "pe datele clientului, tiparul bun e recomandat mult mai des"
        assert alegere.recomanda(db, t, "tipar_hook", []) is None
        with pytest.raises(ValueError):
            alegere.variante_client(db, t, "inventata")
        # punctul de extensie din F6.3 primește preferința
        lv = productie.citeste(db, livrabil(t))
    with sesiune_tenant(t) as db:
        lv = productie.citeste(db, lv.id) if lv else None
        assert lv is not None
        preferinte = {scriere._tipar_preferat(db, lv, ["intrebare", "cifra"]) for _ in range(30)}
        assert "intrebare" in preferinte and preferinte <= {"intrebare", "cifra"}
    with sesiune_tenant(alt) as db:
        assert alegere.variante_client(db, alt, "tipar_hook") == [], "datele unui client nu ajung la altul"
        [noua] = alegere.variante_client(db, alt, "tipar_hook", ["intrebare"])
        assert noua.publicari == 0 and noua.medie == pytest.approx(alegere.MEDIE_NISA), "pornire la rece"
        lv_alt = productie.citeste(db, livrabil(alt))
    with sesiune_tenant(alt) as db:
        lv_alt = productie.citeste(db, lv_alt.id) if lv_alt else None
        assert lv_alt is not None
        assert scriere._tipar_preferat(db, lv_alt, ["intrebare", "cifra"]) is None, (
            "fără date, fără preferință"
        )
