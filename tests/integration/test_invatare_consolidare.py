"""F14.6 — Consolidarea nocturnă a memoriei. „Gata când”: duplicatele dispar și intrările vechi ies din rotație."""

# ruff: noqa: F811
import datetime as dt
import uuid

import pytest
from sqlalchemy import Engine, select, text

from app.db import sesiune_tenant
from app.ids import new_id
from app.invatare import Lectie, LectieFolosita, consolidare
from tests.integration.utile_productie import fabrica_clienti, livrabil, om, tenant  # noqa: F401

pytestmark = pytest.mark.db
ACUM = dt.datetime.now(dt.UTC)


def lectie(t: uuid.UUID, cheie: str, txt: str, *, stare: str = "propusa", zile: int = 0,
           ajutat: int = 0, domeniu: str = "facebook") -> uuid.UUID:  # fmt: skip
    with sesiune_tenant(t) as db:
        r = Lectie(
            tenant_id=t, cheie=cheie, domeniu_tip="canal", domeniu=domeniu, text=txt, dovezi=[{"x": 1}],
            sursa="rezultate", stare=stare, a_ajutat=ajutat, creat_la=ACUM - dt.timedelta(days=zile + 1),
            decis_la=ACUM - dt.timedelta(days=zile) if stare == "activa" else None,
        )  # fmt: skip
        db.add(r)
        db.flush()
        return r.id


def stari(t: uuid.UUID) -> dict[str, tuple[str, int]]:
    with sesiune_tenant(t) as db:
        return {
            r.cheie: (r.stare, r.a_ajutat)
            for r in db.execute(select(Lectie).where(Lectie.tenant_id == t)).scalars()
        }


def test_duplicatele_dispar_si_intrarile_vechi_ies_din_rotatie(
    tenant: uuid.UUID, admin_engine: Engine
) -> None:
    lectie(
        tenant,
        "a-veche",
        "Întrebările din hook aduc mai multe comentarii.",
        stare="activa",
        zile=20,
        ajutat=2,
    )
    lectie(
        tenant, "a-noua", "intrebarile din HOOK aduc mai multe comentarii", stare="activa", zile=3, ajutat=1
    )
    lectie(tenant, "p-dubla", "Întrebările din hook aduc mai multe comentarii!", ajutat=4)
    lectie(
        tenant,
        "alt-canal",
        "Întrebările din hook aduc mai multe comentarii.",
        stare="activa",
        domeniu="tiktok",
    )
    folosita = lectie(
        tenant, "folosita", "Postările de seară au rezultate mai bune.", stare="activa", zile=200
    )
    lectie(tenant, "uitata", "Carusele cu cifre merg bine.", stare="activa", zile=120)
    lectie(tenant, "prop-unu", "Videoclipurile scurte rețin mai bine.", zile=5)
    lectie(tenant, "prop-doi", "Videoclipurile scurte  rețin mai bine", zile=1)
    with sesiune_tenant(tenant) as db:
        db.add(
            LectieFolosita(
                tenant_id=tenant,
                livrabil_id=livrabil(tenant),
                lectie_id=folosita,
                folosita_la=ACUM - dt.timedelta(days=10),
            )
        )
    with sesiune_tenant(tenant) as db:
        r = consolidare.consolideaza(db, tenant, acum=ACUM)
    assert r == {"unite": 3, "scoase": 1, "verificate": 8}
    s = stari(tenant)
    assert s["a-noua"] == ("activa", 7)  # aprobată cel mai recent: rămâne, cu contoarele adunate
    assert s["a-veche"][0] == "retrasa" and s["p-dubla"][0] == "respinsa"
    assert s["alt-canal"][0] == "activa"  # alt domeniu: nu e dublură
    assert s["folosita"][0] == "activa"  # aprobată demult, dar folosită acum 10 zile
    assert s["uitata"][0] == "retrasa"  # nefolosită de 90 de zile
    assert (
        s["prop-unu"][0] == "propusa" and s["prop-doi"][0] == "respinsa"
    )  # între propuneri rămâne cea mai veche
    # a doua rulare nu mai găsește nimic
    with sesiune_tenant(tenant) as db:
        assert consolidare.consolideaza(db, tenant, acum=ACUM) == {"unite": 0, "scoase": 0, "verificate": 4}
    with admin_engine.connect() as c:
        actiuni = c.execute(
            text("SELECT actiune FROM jurnal_audit WHERE tenant_id = :t AND actiune LIKE 'invatare.lectie_%'"),
            {"t": tenant},
        ).scalars().all()  # fmt: skip
        urme = c.execute(
            text("SELECT rezultat FROM urme WHERE componenta = 'invatare.consolidare' AND tenant_id = :t ORDER BY la"),
            {"t": tenant},
        ).scalars().all()  # fmt: skip
    assert sorted(actiuni) == ["invatare.lectie_scoasa_din_rotatie"] + ["invatare.lectie_unita"] * 3
    assert urme == ["ok", "info"]


def test_jobul_trece_prin_toti_clientii_izolat(fabrica_clienti: object) -> None:
    t1, t2 = fabrica_clienti(), fabrica_clienti()  # type: ignore[operator]
    for t in (t1, t2):
        lectie(t, f"x-{new_id().hex[:6]}", "Aceeași lecție.", stare="activa", zile=2)
        lectie(t, f"y-{new_id().hex[:6]}", "aceeasi lectie", stare="activa", zile=1)
    total = consolidare.ruleaza(acum=ACUM)
    assert total["unite"] >= 2
    assert [v[0] for v in stari(t1).values()].count("activa") == 1
    assert [v[0] for v in stari(t2).values()].count("activa") == 1


def test_normalizarea() -> None:
    assert consolidare.normalizeaza("  Întrebările, din HOOK!  ") == "intrebarile din hook"
