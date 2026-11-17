"""Ajutoare pentru testele reclamelor (F13): contul agenției, platformele simulate înregistrate, curățenia."""

import datetime as dt
import uuid
from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import Engine, text

from app.connectors import reclame as registru_reclame
from app.connectors.contract import Token
from app.connectors.publicare.baza import DepozitInMemorie
from app.connectors.reclame.meta import CANAL_TOKEN, ContMeta
from app.db import sesiune_agentie
from app.reclame import rezultate
from tests.platforme.google_ads import DEV_TOKEN, GoogleAdsSimulat
from tests.platforme.meta_ads import MarketingSimulat

TABELE: tuple[str, ...] = ("reclame_rezultate", "reclame_conturi")
AZI = dt.date(2026, 11, 17)
ACUM = dt.datetime(2026, 11, 17, 18, 0, tzinfo=dt.UTC)


def curata(admin: Engine, tabele: tuple[str, ...] = TABELE) -> None:
    with admin.begin() as c:
        for t in tabele:
            c.execute(text(f"DELETE FROM {t}"))
        c.execute(text("DELETE FROM efecte_sistem WHERE tip = 'reclama'"))
        c.execute(text("DELETE FROM opriri WHERE tip = 'reclame'"))


@pytest.fixture
def depozit() -> DepozitInMemorie:
    return DepozitInMemorie()


@pytest.fixture
def meta(depozit: DepozitInMemorie) -> Iterator[MarketingSimulat]:
    sim = MarketingSimulat()
    registru_reclame.inregistreaza("meta", ContMeta(depozit=depozit, transport=sim.transport))
    yield sim
    registru_reclame.uita_tot()


def autorizeaza(
    depozit: DepozitInMemorie, sim: MarketingSimulat, tenant: uuid.UUID, canal: str = CANAL_TOKEN
) -> None:
    depozit.pune(tenant, canal, Token(acces=sim.token_nou("EAAL")))


@pytest.fixture
def cont_agentie(
    fabrica_clienti: Callable[[], uuid.UUID], admin_engine: Engine
) -> Iterator[Callable[..., tuple[uuid.UUID, uuid.UUID]]]:
    """Fabrică: (tenant, cont_id) pentru contul de reclame al agenției, cu plafoane mici [I]."""
    curata(admin_engine)

    def creeaza(
        platforma: str = "meta", cont_extern: str = "act_1001", **plafoane: int
    ) -> tuple[uuid.UUID, uuid.UUID]:
        tenant = fabrica_clienti()
        p = {
            "plafon_zilnic_bani": 10_000,
            "plafon_lunar_bani": 200_000,
            "plafon_campanie_bani": 5_000,
        } | plafoane
        with sesiune_agentie() as db:
            c = rezultate.adauga_cont(db, tenant_id=tenant, platforma=platforma, cont_extern=cont_extern,
                                      nume="Agenția – cont de test", al_agentiei=True, **p)  # fmt: skip
            return tenant, c.id

    yield creeaza
    curata(admin_engine)


@pytest.fixture
def google(depozit: DepozitInMemorie) -> Iterator[GoogleAdsSimulat]:
    from app.connectors.reclame.google import ContGoogle

    sim = GoogleAdsSimulat()
    registru_reclame.inregistreaza(
        "google", ContGoogle(developer_token=DEV_TOKEN, depozit=depozit, transport=sim.transport)
    )
    yield sim
    registru_reclame.uita_tot()
