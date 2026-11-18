"""F12.4 — calificare și scor. „Gata când”: lead-urile de test sunt împărțite corect în cele trei grupe."""

import datetime as dt
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, select, text

from app.crm import CrmRefuzat, Sarcina, calificare, registru, secventa
from app.db import sesiune_agentie
from tests.integration.utile_crm import curata_crm

pytestmark = pytest.mark.db
LEADURI = {  # adresa → răspunsuri, grupa așteptată
    "ana@cafenea.example": ({"nisa": "horeca", "buget": "3000_10000", "termen": "imediat", "decident": "da"}, "suna_azi"),
    "ion@salon.example": ({"nisa": "sanatate_frumusete", "buget": "nu_stiu", "termen": "1_3_luni", "decident": "da"}, "hraneste"),
    "eva@fabrica.example": ({"nisa": "alta", "buget": "1000_3000", "termen": "imediat", "decident": "da"}, "nepotrivit"),
    "dan@mic.example": ({"nisa": "comert_local", "buget": "sub_1000", "termen": "imediat", "decident": "da"}, "nepotrivit"),
    "mara@lant.example": ({"nisa": "horeca", "buget": "peste_10000", "termen": "peste_3_luni", "decident": "impreuna"}, "suna_azi"),
}  # fmt: skip


@pytest.fixture(autouse=True)
def _curat(admin_engine: Engine) -> Iterator[None]:
    curata_crm(admin_engine)
    yield
    curata_crm(admin_engine)


def test_leadurile_de_test_sunt_impartite_corect_in_cele_trei_grupe(admin_engine: Engine) -> None:
    acum = dt.datetime.now(dt.UTC)
    leaduri: dict[str, uuid.UUID] = {}
    with sesiune_agentie() as db:
        for adresa in LEADURI:
            lead, _ = registru.primeste(db, email=adresa, firma=f"Firma {adresa[:4]}", sursa="formular_audit")
            secventa.inscrie(db, lead.contact_id, lead_id=lead.id, acum=acum)
            leaduri[adresa] = lead.id
    with sesiune_agentie() as db:
        for adresa, (raspunsuri, _) in LEADURI.items():
            calificare.califica(db, leaduri[adresa], raspunsuri, acum=acum)
    with sesiune_agentie() as db:
        for adresa, (_, grupa) in LEADURI.items():
            c = calificare.curenta(db, leaduri[adresa])
            assert c is not None and c.grupa == grupa, adresa
            lead = registru.fisa(db, leaduri[adresa])
            assert lead is not None
            etapa, contact = lead["lead"].etapa, lead["contact"].id
            s = secventa.stare(db, contact)
            assert s is not None
            if grupa == "suna_azi":
                assert etapa == "calificat"
                [sarcina] = db.scalars(select(Sarcina).where(Sarcina.lead_id == leaduri[adresa]))
                assert sarcina.scadenta == acum.date() and "sună azi" in sarcina.titlu.lower()
            elif grupa == "nepotrivit":
                assert (etapa, s.stare, s.motiv_oprire) == ("nou", "oprita", "nepotrivit"), "fără presiune"
            else:
                assert (etapa, s.stare) == ("nou", "activa"), "cel de hrănit rămâne în secvență"
        mare = calificare.curenta(db, leaduri["mara@lant.example"])
        assert mare is not None and mare.la_om
        [s_mare] = db.scalars(select(Sarcina).where(Sarcina.lead_id == leaduri["mara@lant.example"]))
        assert "direct la om" in s_mare.titlu

    # recalificarea e un rând nou; starea curentă e ultimul rând; istoricul nu se poate schimba
    with sesiune_agentie() as db:
        calificare.califica(
            db, leaduri["ion@salon.example"], {**LEADURI["ion@salon.example"][0], "buget": "1000_3000"},
            sursa="manual", acum=acum + dt.timedelta(minutes=1),
        )  # fmt: skip
    with sesiune_agentie() as db:
        c = calificare.curenta(db, leaduri["ion@salon.example"])
        assert c is not None and (c.grupa, c.sursa) == ("suna_azi", "manual")
        with pytest.raises(CrmRefuzat):
            calificare.califica(db, leaduri["ion@salon.example"], {"nisa": "horeca"})
    with admin_engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM crm_calificari")).scalar_one() == 6
        assert (
            conn.execute(
                text("SELECT count(*) FROM urme WHERE componenta = 'crm' AND actiune = 'calificare'")
            ).scalar_one()
            >= 6
        )
        assert (
            conn.execute(
                text("SELECT has_table_privilege('ama_app', 'crm_calificari', 'UPDATE')")
            ).scalar_one()
            is False
        )
