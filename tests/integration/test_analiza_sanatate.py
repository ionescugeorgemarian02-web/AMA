"""F10.4 — tablourile de bord și scorul de sănătate. „Gata când”: indicatorii din 4.13 se văd pentru fiecare
client, iar un client de test cu aprobări întârziate apare semnalat."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.analiza import sanatate
from app.conturi import Rol
from app.db import sesiune_agentie, sesiune_tenant
from app.finante.modele import Abonament
from app.operare import audit
from app.productie import Hotarare, Stare, aprobari
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica
from tests.integration.utile_productie import (  # noqa: F401
    fabrica_clienti,
    livrabil,
    muta,
    om,
)

pytestmark = pytest.mark.db
Z = dt.timedelta(days=1)


@pytest.fixture(autouse=True)
def _fara_cereri_ramase(admin_engine: Engine) -> Iterator[None]:
    """Cererile și abonamentele lăsate de aceste teste ar apărea în alte teste (baza e comună pe
    sesiune): la final se anulează, ca superutilizator, cu declanșatoarele oprite doar în tranzacție."""
    yield
    with admin_engine.begin() as c:
        c.execute(text("SET LOCAL session_replication_role = replica"))
        c.execute(text("UPDATE aprobari SET stare = 'anulat', decis_la = now() WHERE stare = 'in_asteptare'"))
        # abonamentele de probă (restante, suspendate) le-ar găsi jobul de restanțe din testele de facturare
        c.execute(text("DELETE FROM abonamente WHERE email_facturare = 'facturi@exemplu.test'"))


def numeste(admin: Engine, tenant: uuid.UUID, nume: str, *, vechime_zile: int = 90) -> None:
    with admin.begin() as c:
        c.execute(
            text("UPDATE clienti SET nume = :n, creat_la = now() - make_interval(days => :z) WHERE id = :i"),
            {"n": nume, "z": vechime_zile, "i": tenant},
        )


def cerere_la_client(admin: Engine, tenant: uuid.UUID, *, veche_de_zile: int) -> uuid.UUID:
    """Un livrabil validat cu o cerere de aprobare la client, creată acum `veche_de_zile` zile."""
    lid = livrabil(tenant)
    curenta = Stare.PLANIFICAT
    for s in (Stare.BRIEFAT, Stare.IN_SCRIERE, Stare.IN_VALIDARE, Stare.VALIDAT):
        muta(tenant, lid, curenta, s)
        curenta = s
    with sesiune_tenant(tenant) as db:
        ap = aprobari.cere(db, lid)
    with admin.begin() as c:
        # Garda din bază nu lasă schimbată o cerere (corect). Testul are nevoie de o cerere VECHE: o
        # îmbătrânim ca superutilizator, cu declanșatoarele oprite doar în această tranzacție.
        c.execute(text("SET LOCAL session_replication_role = replica"))
        c.execute(
            text(
                "UPDATE aprobari SET decident = 'client', creat_la = now() - make_interval(days => :z), "
                "termen_la = now() + interval '5 days' WHERE id = :i"
            ),
            {"z": veche_de_zile, "i": ap.id},
        )
    return ap.id


def autentificare_in_portal(tenant: uuid.UUID, om: uuid.UUID) -> None:
    with sesiune_tenant(tenant) as db:
        audit.record(db, "autentificare.reusita", utilizator_id=om, tenant_id=tenant)


def abonament(tenant: uuid.UUID, stare: str, suma: int = 1490) -> None:
    with sesiune_tenant(tenant) as db:
        db.add(
            Abonament(
                tenant_id=tenant,
                plan="start",
                suma=suma,
                email_facturare="facturi@exemplu.test",
                stare=stare,
                jeton_hash=uuid.uuid4().hex,
                restant_de_la=dt.datetime.now(dt.UTC) - 3 * Z if stare == "restant" else None,
            )
        )


def test_indicatorii_se_vad_pentru_fiecare_client_iar_cel_cu_aprobari_intarziate_e_semnalat(
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
    fabrica_clienti: Callable[[], uuid.UUID],
    om: uuid.UUID,
    admin_engine: Engine,
) -> None:
    bun, intarziat = fabrica_clienti(), fabrica_clienti()
    numeste(admin_engine, bun, "Cafeneaua Zorilor")
    numeste(admin_engine, intarziat, "Brutăria de Probă")
    for t in (bun, intarziat):
        autentificare_in_portal(t, om)
    abonament(bun, "activ")
    abonament(intarziat, "restant")
    # clientul bun: o aprobare decisă din prima de operator
    lid = livrabil(bun)
    curenta = Stare.PLANIFICAT
    for s in (Stare.BRIEFAT, Stare.IN_SCRIERE, Stare.IN_VALIDARE, Stare.VALIDAT):
        muta(bun, lid, curenta, s)
        curenta = s
    with sesiune_tenant(bun) as db:
        ap = aprobari.cere(db, lid)
        aprobari.decide(db, ap.id, Hotarare.APROBAT, utilizator_id=om, rol=Rol.PROPRIETAR, versiune=1)
    # clientul de test: două cereri la client, vechi de 3 zile, și una proaspătă (care nu se numără)
    cerere_la_client(admin_engine, intarziat, veche_de_zile=3)
    cerere_la_client(admin_engine, intarziat, veche_de_zile=4)
    cerere_la_client(admin_engine, intarziat, veche_de_zile=0)

    with sesiune_agentie() as db:
        tablou = sanatate.situatie(db)
        fise = {f.tenant_id: f for f in tablou.fise}
    fb, fi = fise[bun], fise[intarziat]
    assert (fb.scor, fb.nivel, fb.semnale) == (100, "bun", [])
    assert fb.indicatori.venit_lunar == 1490 and fb.indicatori.aprobare_din_prima == 1.0
    assert fb.indicatori.minute_om == sanatate.MINUTE_APROBARE and fb.indicatori.livrare_la_timp is None
    assert [s.cod for s in fi.semnale] == ["aprobari_intarziate", "facturi_restante"]
    assert (fi.scor, fi.nivel) == (55, "atentie")
    assert "2 aprobări așteaptă la client de peste 48 de ore" in fi.semnale[0].text
    assert fi.indicatori.aprobare_din_prima is None, "fără decizii nu se afișează un procent"
    pozitii = [f.tenant_id for f in tablou.fise if f.tenant_id in (bun, intarziat)]
    assert pozitii == [intarziat, bun], "clientul cu probleme apare primul"

    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    r = client.get("/analiza/clienti")
    assert r.status_code == 200
    h = r.text
    assert h.index("Brutăria de Probă") < h.index("Cafeneaua Zorilor")
    sectiune = h[h.index('aria-label="Brutăria de Probă"') : h.index('aria-label="Cafeneaua Zorilor"')]
    assert "De urmărit · 55/100" in sectiune
    assert "2 aprobări așteaptă la client de peste 48 de ore" in sectiune and "Factură restantă" in sectiune
    buna = h[h.index('aria-label="Cafeneaua Zorilor"') :]
    assert "În regulă · 100/100" in buna and "Niciun semnal de risc." in buna
    for indicator in (
        "Venit lunar recurent",
        "Minute de om (estimare)",
        "Aprobare din prima",
        "Livrare la timp",
        "Cotă de modele folosită",
    ):
        assert sectiune.count(indicator) == 1 and indicator in buna, indicator
    assert "Churn lunar" in h and "indisponibil până la CRM" in h
    assert "1490 lei" in buna and "100%" in buna
    assert "/analiza/clienti" in client.get("/analiza").text


def test_livrarea_la_timp_si_churnul(
    fabrica_clienti: Callable[[], uuid.UUID], om: uuid.UUID, admin_engine: Engine
) -> None:
    t = fabrica_clienti()
    acum = dt.datetime.now(dt.UTC)
    la_timp = livrabil(t, termen_la=acum + dt.timedelta(minutes=30))
    nelivrat = livrabil(t, termen_la=acum - 2 * Z)
    with admin_engine.begin() as c:  # un livrabil ajuns „publicat” înaintea termenului (urma tranziției)
        c.execute(
            text(
                "INSERT INTO livrabile_tranzitii (id, tenant_id, livrabil_id, rezultat, din, in_stare, componenta, "
                "actor_tip, versiune) VALUES (:i, :t, :l, 'aplicata', 'in_publicare', 'publicat', 'B7', 'componenta', 1)"
            ),
            {"i": uuid.uuid4(), "t": t, "l": la_timp},
        )
    abonament(t, "suspendat")
    with admin_engine.begin() as c:
        c.execute(
            text("UPDATE abonamente SET suspendat_la = now() - interval '2 days' WHERE tenant_id = :t"),
            {"t": t},
        )
    with sesiune_agentie() as db:
        tablou = sanatate.situatie(db, acum + dt.timedelta(hours=1))
        f = next(x for x in tablou.fise if x.tenant_id == t)
    assert f.indicatori.livrabile_cu_termen == 2 and f.indicatori.livrare_la_timp == 0.5
    assert nelivrat != la_timp and f.indicatori.venit_lunar == 0
    assert "facturi_restante" in [s.cod for s in f.semnale] and f.semnale[-1].puncte == 40
    assert tablou.churn_lunar is not None and tablou.churn_lunar > 0


def test_operatorul_vede_doar_clientii_alocati_lui(
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
    fabrica_clienti: Callable[[], uuid.UUID],
    admin_engine: Engine,
) -> None:
    strain = fabrica_clienti()
    numeste(admin_engine, strain, "Client Nealocat")
    autentifica(client, fabrica_conturi(Rol.OPERATOR, cu_totp=True), ceas)
    r = client.get("/analiza/clienti")
    assert r.status_code == 200 and "Client Nealocat" not in r.text
