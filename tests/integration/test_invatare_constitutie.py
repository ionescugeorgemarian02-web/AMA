"""F11.5 — Constituția. „Gata când”: o încercare de a modifica un pachet de reguli din fluxul de învățare
este refuzată. Refuzul vine din bază (declanșator), nu din bunăvoința codului. Plus: o promovare pe
săptămână pe domeniu și butonul de înghețare."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.conturi import Rol
from app.db import sesiune_agentie, sesiune_tenant
from app.ids import new_id
from app.invatare import Lectie, constitutie, curator
from app.invatare.constitutie import ConstitutieIncalcata
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401

pytestmark = pytest.mark.db
REGULA = (
    "INSERT INTO reguli_client (id, tenant_id, regula_id, versiune, definitie, creat_de) "
    "VALUES (:i, :t, :r, 1, CAST('{}' AS jsonb), :u)"
)
ACUM = dt.datetime.now(dt.UTC)


@pytest.fixture(autouse=True)
def _dezghetat(admin_engine: Engine) -> Iterator[None]:
    yield
    with admin_engine.begin() as c:
        c.execute(text("UPDATE invatare_stare SET inghetat = false WHERE id = 1"))


def propune(t: uuid.UUID, cheie: str, domeniu: str = "") -> uuid.UUID:
    with sesiune_tenant(t) as db:
        r = Lectie(
            tenant_id=t, cheie=cheie, domeniu_tip="canal" if domeniu else "client", domeniu=domeniu,
            text=f"Lecție de probă pentru Constituție: {cheie}.", dovezi=[{"x": 1}], sursa="rezultate",
        )  # fmt: skip
        db.add(r)
        db.flush()
        return r.id


def test_fluxul_de_invatare_nu_poate_modifica_regulile_validatorilor(
    tenant: uuid.UUID, om: uuid.UUID
) -> None:
    with sesiune_tenant(tenant) as db:  # în afara învățării, regula clientului se poate scrie
        db.execute(text(REGULA), {"i": new_id(), "t": tenant, "r": "regula-de-proba", "u": om})
    with (
        pytest.raises(DBAPIError, match="Constituția"),
        sesiune_tenant(tenant) as db,
        constitutie.flux_invatare(db),
    ):
        db.execute(text(REGULA), {"i": new_id(), "t": tenant, "r": "regula-din-invatare", "u": om})
    with sesiune_tenant(tenant) as db:
        assert (
            db.execute(
                text("SELECT count(*) FROM reguli_client WHERE tenant_id = :t"), {"t": tenant}
            ).scalar_one()
            == 1
        )
        # marcajul se reface la ieșirea din flux: aceeași tranzacție poate scrie din nou regulile
        with constitutie.flux_invatare(db):
            assert db.execute(text("SELECT current_setting('app.flux', true)")).scalar_one() == "invatare"
        db.execute(text(REGULA), {"i": new_id(), "t": tenant, "r": "regula-dupa-flux", "u": om})
        # iar învățarea își poate scrie propriile tabele
        with constitutie.flux_invatare(db):
            db.add(
                Lectie(
                    tenant_id=tenant,
                    cheie="in-flux",
                    domeniu_tip="client",
                    text="Lecție scrisă în flux.",
                    dovezi=[{"x": 1}],
                    sursa="rezultate",
                )
            )
            db.flush()


def test_o_promovare_pe_saptamana_pe_domeniu(tenant: uuid.UUID, om: uuid.UUID) -> None:
    a, b, pe_canal = (
        propune(tenant, "lectia-a"),
        propune(tenant, "lectia-b"),
        propune(tenant, "lectia-c", "facebook"),
    )
    with sesiune_tenant(tenant) as db:
        curator.aproba(db, a, utilizator_id=om, rol=Rol.PROPRIETAR, acum=ACUM)
        with pytest.raises(ConstitutieIncalcata, match="ultimele 7 zile"):
            curator.aproba(db, b, utilizator_id=om, rol=Rol.PROPRIETAR, acum=ACUM + dt.timedelta(days=6))
        curator.aproba(db, pe_canal, utilizator_id=om, rol=Rol.PROPRIETAR, acum=ACUM)  # alt domeniu: permis
        assert (
            curator.aproba(
                db, b, utilizator_id=om, rol=Rol.PROPRIETAR, acum=ACUM + dt.timedelta(days=7, minutes=1)
            ).stare
            == "activa"
        )


def test_inghetarea_opreste_toate_promovarile(tenant: uuid.UUID, om: uuid.UUID) -> None:
    lid = propune(tenant, "de-inghetat")
    with sesiune_tenant(tenant) as db, pytest.raises(ConstitutieIncalcata):
        constitutie.ingheata(db, activ=True, utilizator_id=om)  # un client nu poate îngheța
    with sesiune_agentie() as db:
        constitutie.ingheata(db, activ=True, utilizator_id=om, motiv="verificăm un incident")
    with sesiune_tenant(tenant) as db:
        assert constitutie.inghetat(db)
        with pytest.raises(ConstitutieIncalcata, match="înghețată"):
            curator.aproba(db, lid, utilizator_id=om, rol=Rol.PROPRIETAR)
        assert curator.retrage is not None  # retragerea rămâne posibilă cât e înghețat (reversibilitate)
    with sesiune_agentie() as db:
        constitutie.ingheata(db, activ=False, utilizator_id=om)
    with sesiune_tenant(tenant) as db:
        assert curator.aproba(db, lid, utilizator_id=om, rol=Rol.PROPRIETAR).stare == "activa"
