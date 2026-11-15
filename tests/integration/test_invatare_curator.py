"""F11.2 — Curatorul și playbook-ul. „Gata când”: o lecție aprobată apare în contextul sarcinii următoare și
contorul ei se actualizează. Contextul este cel real al autorului (`continut.scriere.exemple_text`), iar
contoarele se mișcă la decizia reală a omului din biroul de aprobări."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable

import pytest

from app import productie
from app.continut import scriere
from app.conturi import Rol
from app.db import sesiune_tenant
from app.invatare import Lectie, curator
from app.invatare.curator import CuratorRefuzat
from app.productie import Hotarare, Stare, aprobari
from tests.integration.utile_productie import fabrica_clienti, livrabil, muta, om, tenant  # noqa: F401

pytestmark = pytest.mark.db
TEXT = "Folosește mai des hook-urile de tip „întrebare”: 9,0 interacțiuni la 100 de afișări."


def propune(t: uuid.UUID, cheie: str, *, text_: str = TEXT, sensibila: bool = False, **kw: str) -> uuid.UUID:
    with sesiune_tenant(t) as db:
        r = Lectie(
            tenant_id=t,
            cheie=cheie,
            domeniu_tip=kw.get("domeniu_tip", "client"),
            domeniu=kw.get("domeniu", ""),
            text=text_,
            dovezi=[{"livrabil_id": "x"}],
            sursa="rezultate",
            sensibila=sensibila,
        )
        db.add(r)
        db.flush()
        return r.id


def context(t: uuid.UUID, lid: uuid.UUID) -> str:
    with sesiune_tenant(t) as db:
        lv = productie.citeste(db, lid)
        assert lv is not None
        return scriere.exemple_text(db, lv)


def decide(t: uuid.UUID, lid: uuid.UUID, om: uuid.UUID, hotarare: Hotarare) -> None:
    curenta = Stare.PLANIFICAT
    for s in (Stare.BRIEFAT, Stare.IN_SCRIERE, Stare.IN_VALIDARE, Stare.VALIDAT):
        muta(t, lid, curenta, s)
        curenta = s
    with sesiune_tenant(t) as db:
        ap = aprobari.cere(db, lid)
        extra = {"motiv_standard": "hook_slab"} if hotarare is Hotarare.RESPINS else {}
        aprobari.decide(db, ap.id, hotarare, utilizator_id=om, rol=Rol.PROPRIETAR, versiune=1, **extra)


def lectie(t: uuid.UUID, lectie_id: uuid.UUID) -> Lectie:
    with sesiune_tenant(t) as db:
        r = db.get(Lectie, lectie_id)
        assert r is not None
        db.expunge(r)
        return r


def test_lectia_aprobata_apare_in_contextul_sarcinii_urmatoare_si_contorul_se_actualizeaza(
    fabrica_clienti: Callable[[], uuid.UUID], om: uuid.UUID
) -> None:
    t, alt = fabrica_clienti(), fabrica_clienti()
    lid_lectie = propune(t, "rezultate:tipar_hook:intrebare:mai_des")
    pe_alt_canal = propune(
        t,
        "canal:linkedin",
        text_="Pe LinkedIn, prima frază spune rezultatul.",
        domeniu_tip="canal",
        domeniu="linkedin",
    )
    primul = livrabil(t, canal="facebook")
    assert "Lecții din playbook" not in context(t, primul), "o lecție doar propusă nu ajunge în context"
    with sesiune_tenant(t) as db:
        curator.aproba(db, lid_lectie, utilizator_id=om, rol=Rol.OPERATOR)
        curator.aproba(db, pe_alt_canal, utilizator_id=om, rol=Rol.OPERATOR)
        with pytest.raises(CuratorRefuzat):
            curator.aproba(db, lid_lectie, utilizator_id=om, rol=Rol.OPERATOR)  # deja activă

    urmatorul = livrabil(t, canal="facebook")
    c = context(t, urmatorul)
    assert "Lecții din playbook (ține cont de ele):" in c and f"- {TEXT}" in c
    assert "LinkedIn" not in c, "lecția unui alt canal nu intră"
    with sesiune_tenant(t) as db:
        assert curator.folosite_la(db, urmatorul) == [lid_lectie]
    assert "Lecții din playbook" not in context(alt, livrabil(alt, canal="facebook")), "clienți separați"

    decide(t, urmatorul, om, Hotarare.APROBAT)
    r = lectie(t, lid_lectie)
    assert (r.a_ajutat, r.a_daunat, r.stare) == (1, 0, "activa")
    with sesiune_tenant(t) as db:  # aceeași decizie nu se socotește de două ori
        lv = productie.citeste(db, urmatorul)
        ap = aprobari.ale_livrabilului(db, urmatorul)[-1]
        assert lv is not None
        curator._dupa_decizie(db, ap, lv, Hotarare.APROBAT)
    assert lectie(t, lid_lectie).a_ajutat == 1

    # două respingeri: „a dăunat” depășește „a ajutat” → retragere automată, lecția iese din context
    for _ in range(2):
        lid = livrabil(t, canal="facebook")
        assert TEXT in context(t, lid)
        decide(t, lid, om, Hotarare.RESPINS)
    r = lectie(t, lid_lectie)
    assert (r.a_ajutat, r.a_daunat, r.stare) == (1, 2, "retrasa") and "a dăunat" in r.motiv
    assert TEXT not in context(t, livrabil(t, canal="facebook"))


def test_lectiile_sensibile_limita_si_respingerea(tenant: uuid.UUID, om: uuid.UUID) -> None:
    sensibila = propune(
        tenant, "verdicte:G2.pret_fara_fapt", sensibila=True, domeniu_tip="agent", domeniu="autor"
    )
    de_respins = propune(tenant, "decizii:prea_lung")
    with sesiune_tenant(tenant) as db:
        with pytest.raises(CuratorRefuzat, match="proprietarul"):
            curator.aproba(db, sensibila, utilizator_id=om, rol=Rol.OPERATOR)
        assert curator.aproba(db, sensibila, utilizator_id=om, rol=Rol.PROPRIETAR).stare == "activa"
        with pytest.raises(CuratorRefuzat):
            curator.respinge(db, de_respins, utilizator_id=om, motiv="")
        assert curator.respinge(db, de_respins, utilizator_id=om, motiv="nu se aplică").stare == "respinsa"
        with pytest.raises(CuratorRefuzat):
            curator.retrage(db, de_respins, utilizator_id=om, motiv="x")  # nu e activă
        assert curator.retrage(db, sensibila, utilizator_id=om, motiv="anulez promovarea").stare == "retrasa"
    # limita de lecții active pe domeniu
    ids = [
        propune(tenant, f"limita:{i}", text_=f"Lecția de probă numărul {i} pentru limită.")
        for i in range(curator.MAX_ACTIVE + 1)
    ]
    with sesiune_tenant(tenant) as db:
        # Constituția (F11.5) permite o promovare pe săptămână pe domeniu: aprobările sunt la 8 zile distanță
        baza = dt.datetime.now(dt.UTC) - dt.timedelta(days=8 * (len(ids) + 1))
        for n, i in enumerate(ids[:-1]):
            curator.aproba(db, i, utilizator_id=om, rol=Rol.PROPRIETAR, acum=baza + dt.timedelta(days=8 * n))
        with pytest.raises(CuratorRefuzat, match="retrage una"):
            curator.aproba(db, ids[-1], utilizator_id=om, rol=Rol.PROPRIETAR)
        assert len(curator.active(db, tenant, "client")) == curator.MAX_ACTIVE
        lv = productie.citeste(db, livrabil(tenant))
    with sesiune_tenant(tenant) as db:
        lv = productie.citeste(db, lv.id) if lv else None
        assert lv is not None and len(curator.pentru_livrabil(db, lv)) == curator.MAX_IN_CONTEXT
    assert curator.de_retras(1, 2) and not curator.de_retras(2, 2) and not curator.de_retras(0, 0)
