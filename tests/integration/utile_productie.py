"""Ajutoare pentru testele producției (F2.3–F2.10): clienți și utilizatori creați direct în bază."""

import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import Engine, text

from app import productie
from app.db import sesiune_tenant
from app.ids import new_id
from app.operare import notificari
from app.operare.notificari import Nivel
from app.productie.stari import Stare
from tests.conftest import BazaTest

PAROLA_HASH = "hash-de-proba"  # nu este verificat în aceste teste


@pytest.fixture
def fabrica_clienti(baza: BazaTest, admin_engine: Engine) -> Callable[[], uuid.UUID]:
    def creeaza() -> uuid.UUID:
        cid = new_id()
        with admin_engine.begin() as c:
            c.execute(
                text("INSERT INTO clienti (id, nume) VALUES (:i, :n)"),
                {"i": cid, "n": f"Firma {cid.hex[:6]}"},
            )
        return cid

    return creeaza


@pytest.fixture
def tenant(fabrica_clienti: Callable[[], uuid.UUID]) -> uuid.UUID:
    return fabrica_clienti()


@pytest.fixture
def om(admin_engine: Engine) -> uuid.UUID:
    """Un utilizator (de agenție) pentru deciziile umane."""
    uid = new_id()
    with admin_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO utilizatori (id, email, nume_afisat, parola_hash) VALUES (:i, :e, 'Ana Test', :p)"
            ),
            {"i": uid, "e": f"{uid}@exemplu.test", "p": PAROLA_HASH},
        )
    return uid


class AnunturiFalse:
    """SIMULAT: ține locul canalelor push/Telegram; înregistrează ce s-ar fi trimis (nivel, titlu, text, url)."""

    def __init__(self) -> None:
        self.trimise: list[tuple[Nivel, str, str, str]] = []

    def __call__(self, nivel: Nivel, titlu: str, text_: str, url: str = "/alerte") -> dict[object, bool]:
        self.trimise.append((nivel, titlu, text_, url))
        return {}

    def titluri(self) -> list[str]:
        return [t[1] for t in self.trimise]

    def nivele(self) -> list[Nivel]:
        return [t[0] for t in self.trimise]


@pytest.fixture
def anunturi(monkeypatch: pytest.MonkeyPatch) -> AnunturiFalse:
    """Anunțurile producției pleacă prin `notificari.notifica`; aici nu ajung la nicio rețea."""
    f = AnunturiFalse()
    monkeypatch.setattr(notificari, "notifica", f)
    return f


def livrabil(tenant: uuid.UUID, *, tip: str = "postare", canal: str = "facebook", **kw: object) -> uuid.UUID:
    with sesiune_tenant(tenant) as db:
        return productie.creeaza(db, tenant_id=tenant, tip=tip, canal=canal, **kw).id  # type: ignore[arg-type]


def muta(tenant: uuid.UUID, lid: uuid.UUID, din: Stare, la: Stare, **kw: object) -> productie.Rezultat:
    with sesiune_tenant(tenant) as db:
        return productie.muta(db, lid, din, la, componenta=str(kw.pop("componenta", "test")), **kw)  # type: ignore[arg-type]


def stare(tenant: uuid.UUID, lid: uuid.UUID) -> Stare:
    with sesiune_tenant(tenant) as db:
        livr = productie.citeste(db, lid)
        assert livr is not None
        return Stare(livr.stare)


def randuri(admin: Engine, lid: uuid.UUID) -> list[dict[str, object]]:
    with admin.connect() as c:
        return [
            dict(r._mapping)
            for r in c.execute(
                text(
                    "SELECT rezultat, din, in_stare, componenta, actor_tip, motiv, detalii FROM livrabile_tranzitii "
                    "WHERE livrabil_id = :i ORDER BY creat_la, id"
                ),
                {"i": lid},
            )
        ]


def livrabil_programat(
    tenant: uuid.UUID, om_id: uuid.UUID, *, canal: str = "fals", tip: str = "postare"
) -> uuid.UUID:
    """Un livrabil ajuns LEGITIM în `programat`: toate mutările trec prin `productie.muta`, cu aprobare de om."""
    from app.conturi import Rol
    from app.productie import Hotarare, aprobari

    lid = livrabil(tenant, canal=canal, tip=tip)
    curenta = Stare.PLANIFICAT
    for s in (Stare.BRIEFAT, Stare.IN_SCRIERE, Stare.IN_VALIDARE, Stare.VALIDAT):
        muta(tenant, lid, curenta, s)
        curenta = s
    with sesiune_tenant(tenant) as db:
        ap = aprobari.cere(db, lid)
        aprobari.decide(db, ap.id, Hotarare.APROBAT, utilizator_id=om_id, rol=Rol.PROPRIETAR, versiune=1)
    muta(tenant, lid, Stare.APROBAT, Stare.PROGRAMAT)
    return lid


def livrabil_in_publicare(
    tenant: uuid.UUID, om_id: uuid.UUID, *, canal: str = "fals", tip: str = "postare"
) -> uuid.UUID:
    lid = livrabil_programat(tenant, om_id, canal=canal, tip=tip)
    muta(tenant, lid, Stare.PROGRAMAT, Stare.IN_PUBLICARE)
    return lid
