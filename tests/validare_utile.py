"""Ajutoare pentru testele validării (F5): un livrabil adus LEGITIM în `în validare` (toate mutările trec
prin
`productie.muta`), cu conținut scris prin `validare.continut.scrie`, plus un registru gol pentru testele
cadrului.
# SIMULAT: autorul reparațiilor din teste este scriptat (nu cheamă niciun model)."""

import contextlib
import datetime as dt
import json
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app import cercetare, creier, productie, validare
from app.creier import fapte, oferte
from app.creier.compartimente import SursaTip
from app.creier.versiuni import Sursa
from app.db import sesiune_tenant
from app.productie import Stare
from app.validare import registru
from app.validare.autor import ContinutNou, SarcinaReparatie
from tests.furnizor_fals import CerereInregistrata, FurnizorFals
from tests.gateway_utile import FabricaModele
from tests.onboarding_utile import prompt_complet


def livrabil_in_validare(
    tenant: uuid.UUID,
    text: str,
    *,
    campuri: dict[str, Any] | None = None,
    active: list[dict[str, Any]] | None = None,
    tip: str = "postare",
    canal: str = "facebook",
    model_autor: str | None = None,
    autor: str = "E4",
    termen_la: dt.datetime | None = None,
) -> uuid.UUID:
    with sesiune_tenant(tenant) as db:
        lid = productie.creeaza(db, tenant_id=tenant, tip=tip, canal=canal, termen_la=termen_la).id
        parcurs = Stare.PLANIFICAT
        for s in (Stare.BRIEFAT, Stare.IN_SCRIERE):
            productie.muta(db, lid, parcurs, s, componenta="test")
            parcurs = s
        validare.continut.scrie(
            db, lid, text=text, campuri=campuri, active=active, autor=autor, model_autor=model_autor
        )
        productie.muta(db, lid, Stare.IN_SCRIERE, Stare.IN_VALIDARE, componenta=autor)
    return lid


def ruleaza(tenant: uuid.UUID, lid: uuid.UUID, **kw: Any) -> validare.RezultatRunda:
    with sesiune_tenant(tenant) as db:
        return validare.ruleaza_runda(db, lid, **kw)


def verdicte(tenant: uuid.UUID, lid: uuid.UUID, **kw: Any) -> list[validare.VerdictSalvat]:
    with sesiune_tenant(tenant) as db:
        return validare.verdicte(db, lid, **kw)


@pytest.fixture
def registru_gol() -> Iterator[None]:
    """Fără validatorii reali: testele cadrului își înregistrează propriii validatori de probă."""
    with registru.izolat():
        yield


@pytest.fixture
def autor_scriptat() -> Iterator[
    Callable[[Callable[[SarcinaReparatie], ContinutNou]], list[SarcinaReparatie]]
]:
    """Înregistrează un autor de reparații scriptat; întoarce lista sarcinilor primite. La final îl scoate."""
    primite: list[SarcinaReparatie] = []

    def seteaza(f: Callable[[SarcinaReparatie], ContinutNou]) -> list[SarcinaReparatie]:
        def autor(_db: Session, sarcina: SarcinaReparatie) -> ContinutNou:
            primite.append(sarcina)
            return f(sarcina)

        validare.autor.inregistreaza(autor)
        return primite

    yield seteaza
    validare.autor.inregistreaza(None)


def registru_doar(*coduri: str) -> contextlib.AbstractContextManager[None]:
    """Registrul restrâns la validatorii REALI cu aceste coduri (ceilalți nu se aplică în testul respectiv)."""
    return registru.izolat(coduri)


# --- judecători (V3 / V4) cu model FALS
# ---------------------------------------------------------------------------


def raspuns(criteriu: str, da: bool, fragment: str = "", motiv: str = "") -> dict[str, Any]:
    return {"criteriu": criteriu, "da": da, "fragment": fragment, "motiv": motiv}


def rubrica(*raspunsuri: dict[str, Any]) -> str:
    return json.dumps(
        {"raspunsuri": list(raspunsuri), "dovezi": ["scriptat"], "incredere": 0.9}, ensure_ascii=False
    )


class JudecatorFals:
    """# SIMULAT: modelul judecătorilor. `handlere[fraza]` primește cererea și întoarce JSON-ul rubricii;
    alege handlerul
    după o frază care apare doar în promptul judecătorului respectiv. Nicio rețea, nicio cheie reală."""

    def __init__(self, cod: str) -> None:
        self.cod = cod  # `furnizor/identificator` al modelului judecătorului
        self.gazda = f"{cod.split('/')[0]}.exemplu.test"  # gazda furnizorului de probă (pentru scenarii)
        self.cod_autor = "autor/alt-model"  # un alt model, pentru `alt_model_decat`
        self.handlere: dict[str, Callable[[CerereInregistrata], str]] = {}
        self.cereri: list[CerereInregistrata] = []

    def raspunde(self, fraza: str, raspuns_json: str | Callable[[CerereInregistrata], str]) -> None:
        self.handlere[fraza] = raspuns_json if callable(raspuns_json) else (lambda _c, r=raspuns_json: r)  # type: ignore[misc]

    def __call__(self, c: CerereInregistrata) -> str:
        p = prompt_complet(c)
        self.cereri.append(c)
        for fraza, h in self.handlere.items():
            if fraza in p:
                return h(c)
        raise AssertionError("prompt necunoscut judecătorului fals: " + p[:200])

    def prompturi(self) -> list[str]:
        return [prompt_complet(c) for c in self.cereri]


@pytest.fixture
def judecator(
    fabrica_modele: FabricaModele, admin_engine: Engine, cheie_proba: str, fals: FurnizorFals
) -> Iterator[JudecatorFals]:
    """Profilul `judecata` (V3) și `consiliu` (V4) trec pe un singur model de probă, servit de furnizorul fals."""
    m = fabrica_modele.model(
        fabrica_modele.furnizor(), identificator="judecator", nivel="T3", capabilitati=["iesire_structurata"]
    )
    j = JudecatorFals(m.cod)
    fals.text = j
    profiluri = ("judecata",)
    with admin_engine.connect() as c:
        originale = {
            p: list(
                c.execute(text("SELECT lant FROM gateway_profiluri WHERE nume = :n"), {"n": p}).scalar_one()
            )
            for p in profiluri
        }
    with admin_engine.begin() as c:
        for p in profiluri:
            c.execute(text("UPDATE gateway_profiluri SET lant = :l WHERE nume = :n"), {"l": [m.cod], "n": p})
    yield j
    with admin_engine.begin() as c:
        for p in profiluri:
            c.execute(
                text("UPDATE gateway_profiluri SET lant = :l WHERE nume = :n"), {"l": originale[p], "n": p}
            )
        c.execute(text("DELETE FROM gateway_prompturi WHERE nume LIKE 'validare.%'"))


# --- registrul de fapte (Creier) pentru testele validatorilor
# --------------------------------------------------------
# Momentele sunt FIXE (nu depind de ceasul real): faptele se aprobă la T_APROB, textul se validează la LA.

LA = dt.datetime(2026, 11, 12, 12, 0, tzinfo=dt.UTC)
T_APROB = LA - dt.timedelta(days=1)


def fapt_aprobat(
    tenant: uuid.UUID,
    om: uuid.UUID,
    tip: str,
    subiect: str,
    afirmatie: str,
    *,
    valoare: dict[str, Any] | None = None,
    valabil_de_la: dt.datetime | None = None,
    valabil_pana_la: dt.datetime | None = None,
    aprobat_la: dt.datetime = T_APROB,
) -> uuid.UUID:
    continut: dict[str, Any] = {"tip": tip, "subiect": subiect, "afirmatie": afirmatie}
    if valoare:
        continut["valoare"] = valoare
    with sesiune_tenant(tenant, om) as db:
        i, v, _ = fapte.propune_fapt(
            db, tenant_id=tenant, continut=continut, sursa=Sursa(SursaTip.DECLARATIE_CLIENT), utilizator_id=om,
            valabil_de_la=valabil_de_la, valabil_pana_la=valabil_pana_la, acum=aprobat_la,
        )  # fmt: skip
        fapte.aproba_fapt(db, i.id, v.nr, utilizator_id=om, acum=aprobat_la)
        return i.id


def oferta_aprobata(
    tenant: uuid.UUID,
    om: uuid.UUID,
    nume: str,
    pret: str,
    *,
    tip: str = "produs",
    pret_referinta: str | None = None,
    valabil_pana_la: dt.datetime | None = None,
    aprobat_la: dt.datetime = T_APROB,
    **campuri: Any,
) -> uuid.UUID:
    continut: dict[str, Any] = {"tip": tip, "nume": nume, "pret": {"numar": pret, "moneda": "RON"}, **campuri}
    if pret_referinta:
        continut["pret_referinta"] = {"numar": pret_referinta, "moneda": "RON"}
    with sesiune_tenant(tenant, om) as db:
        i, v, _ = oferte.propune_oferta(
            db, tenant_id=tenant, continut=continut, sursa=Sursa(SursaTip.DECLARATIE_CLIENT), utilizator_id=om,
            valabil_pana_la=valabil_pana_la, acum=aprobat_la,
        )  # fmt: skip
        oferte.aproba_oferta(db, i.id, v.nr, utilizator_id=om, acum=aprobat_la)
        return i.id


def sursa_cu_pasaje(
    tenant: uuid.UUID, texte: list[str], *, statut: str = "material_client", nume: str = "Surse de probă"
) -> tuple[uuid.UUID, list[creier.Pasaj]]:
    """O sursă manuală cu aceste texte, tăiate în pasaje (fără vectori). Întoarce sursa și pasajele ei."""
    from sqlalchemy import select

    with sesiune_tenant(tenant) as db:
        sid = cercetare.creeaza_sursa(db, tenant_id=tenant, tip="manual", statut_cod=statut, nume=nume).id
        for i, t in enumerate(texte):
            cercetare.adauga_text(db, tenant_id=tenant, sursa_id=sid, titlu=f"Document {i}", text=t)
        creier.pregateste_sursa(db, sid)
        pasaje = list(db.execute(select(creier.Pasaj).where(creier.Pasaj.sursa_id == sid)).scalars())
        db.expunge_all()
    return sid, pasaje


def profil_aprobat(
    tenant: uuid.UUID,
    om: uuid.UUID,
    continut: dict[str, Any],
    *,
    aprobat_la: dt.datetime = T_APROB,
    cheie: str = "profil",
) -> uuid.UUID:
    """O intrare din profilul de brand al clientului (`profil` sau `ghid`), aprobată de un om la un moment fix."""
    from app.creier.compartimente import Compartiment

    with sesiune_tenant(tenant, om) as db:
        i, v = creier.creeaza_intrare(
            db, tenant_id=tenant, compartiment=Compartiment.PROFIL_BRAND, cheie=cheie, continut=continut,
            sursa=Sursa(SursaTip.OM), utilizator_id=om, acum=aprobat_la,
        )  # fmt: skip
        creier.aproba(db, i.id, v.nr, utilizator_id=om, acum=aprobat_la)
        return i.id
