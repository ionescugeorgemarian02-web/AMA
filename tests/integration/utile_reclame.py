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

TABELE: tuple[str, ...] = (
    "reclame_teste",
    "reclame_dosare",
    "reclame_decizii",
    "reclame_propuneri",
    "reclame_anunturi",
    "reclame_campanii",
    "reclame_planuri",
    "reclame_rezultate",
    "reclame_conturi",
)
PAGINI: dict[str, bool] = {}
TEXT_PAGINA = (
    "Audit gratuit de marketing pentru firma ta. Unde pierzi clienți, trei greșeli de pe site și exemplul unei "
    "cafenele care a crescut. Cerere de audit în 48 de ore."
)


def pagina_simulata(url: str) -> str | None:
    """# SIMULAT: pagina de audit a agenției (fără rețea); `PAGINI[url] = False` o face să nu răspundă."""
    return TEXT_PAGINA if PAGINI.get(url.split("?")[0], True) else None


AZI = dt.datetime.now(dt.UTC).date()  # panoul citește ceasul real; restul primește `acum` explicit
ACUM = dt.datetime.combine(AZI, dt.time(18), dt.UTC)


def curata(admin: Engine, tabele: tuple[str, ...] = TABELE) -> None:
    with admin.begin() as c:
        c.execute(text("UPDATE reclame_propuneri SET efect_id = NULL, anuleaza_id = NULL"))
        c.execute(text("DELETE FROM efecte_sistem WHERE tip = 'reclama'"))
        for t in tabele:
            c.execute(text(f"DELETE FROM {t}"))
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
    fabrica_clienti: Callable[[], uuid.UUID], admin_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[..., tuple[uuid.UUID, uuid.UUID]]]:
    """Fabrică: (tenant, cont_id) pentru contul de reclame al agenției, cu plafoane mici [I]. Pagina de
    destinație „răspunde” (fără rețea); testele de urgență schimbă `PAGINI`."""
    from app.reclame import urgenta, verificare

    curata(admin_engine)
    monkeypatch.setattr(urgenta, "VERIFICA_PAGINA", lambda url: PAGINI.get(url, True))
    monkeypatch.setattr(verificare, "CITESTE_PAGINA", pagina_simulata)

    def creeaza(
        platforma: str = "meta", cont_extern: str = "act_1001", **plafoane: int
    ) -> tuple[uuid.UUID, uuid.UUID]:
        tenant = fabrica_clienti()
        p = {
            "plafon_zilnic_bani": 10_000,
            "plafon_lunar_bani": 300_000,
            "plafon_campanie_bani": 8_000,
        } | plafoane
        with sesiune_agentie() as db:
            c = rezultate.adauga_cont(
                db,
                tenant_id=tenant,
                platforma=platforma,
                cont_extern=cont_extern,
                nume="Agenția – cont de test",
                al_agentiei=True,
                **p,
            )
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


def executa_efecte() -> list[str]:
    """Rulează pe loc efectele `reclama` în așteptare (ca jobul executorului) și reconciliază campaniile."""
    from sqlalchemy import select

    from app.operare import motor
    from app.operare.efecte import EfectSistemRand, sistem
    from app.reclame import propuneri

    with sesiune_agentie() as db:
        ids = list(
            db.execute(
                select(EfectSistemRand.id)
                .where(EfectSistemRand.tip == "reclama", EfectSistemRand.stare == "in_asteptare")
                .order_by(EfectSistemRand.creat_la)
            ).scalars()
        )
    rez = []
    for i in ids:
        try:
            rez.append(sistem.incearca(i))
        except motor.EroareTemporara:
            rez.append("temporar")
    with sesiune_agentie() as db:
        propuneri.reconciliaza(db)
    return rez


PARAMETRI_PLAN = {
    "obiectiv": "lead",
    "pagina_destinatie": "https://agentie.example/audit",
    "buget_lunar_bani": 240_000,
    "public": "Proprietari de IMM-uri din România, 25–60 de ani",
    "cost_tinta_bani": 4_000,
    "unghiuri": ["Unde pierzi clienți", "Trei greșeli de pe site", "Exemplu: o cafenea"],
    "nume": "Audit gratuit",
}


def plan_aprobat(cont_id: uuid.UUID, om: uuid.UUID, **kw: object) -> uuid.UUID:
    from app.reclame import plan

    with sesiune_agentie() as db:
        r = plan.propune(db, cont_id, **(PARAMETRI_PLAN | kw))
        plan.decide(db, r.id, aprobat=True, utilizator_id=om)
        return r.id


def creative(plan_id: uuid.UUID) -> dict[str, object]:
    from app.reclame.constructor import Creativ

    return {
        "scalare": Creativ("Audit gratuit de marketing", "Află în 48 de ore unde pierzi clienți."),
        "Unde pierzi clienți": Creativ("Unde pierzi clienți?", "Auditul îți arată pașii care lipsesc."),
        "Trei greșeli de pe site": Creativ("Trei greșeli de pe site", "Cele mai dese, explicate simplu."),
        "Exemplu: o cafenea": Creativ("Cum a crescut o cafenea", "Un exemplu concret, pas cu pas."),
    }


def construieste(cont_id: uuid.UUID, om: uuid.UUID, **kw: object) -> list[uuid.UUID]:
    from app.reclame import constructor

    pid = plan_aprobat(cont_id, om, **kw)
    with sesiune_agentie() as db:
        ids = [c.id for c in constructor.construieste(db, pid, creative(pid))]  # type: ignore[arg-type]
    executa_efecte()
    return ids
