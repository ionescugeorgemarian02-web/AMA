"""F6.1 — strategul de conținut și calendarul. „Gata când”: un brand propriu are calendar pe 30 de zile, aprobat. Brandul este
FICTIV („Cafeneaua Zorilor”), modelul este FALS (# SIMULAT); pentru brandurile reale, aprobarea e a proprietarului."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app import continut, creier, productie
from app.conturi import Rol
from app.db import sesiune_tenant
from app.operare import motor
from tests.continut_utile import calendar_valid, model_calendar
from tests.integration.conftest import Cont
from tests.integration.lant_continut import pana_la_strategie
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele, prompt_complet  # noqa: F401

pytestmark = pytest.mark.db
INCEPUT = dt.date(2026, 12, 1)


def propune(tenant: uuid.UUID, om: uuid.UUID, cheie: str) -> int:
    """Rulează fluxul și întoarce câte calendare are clientul după el."""
    job = continut.fluxuri.trimite_calendarul(tenant, om, inceput=INCEPUT, cheie=cheie)
    assert motor.asteapta_flux(job, timeout_sec=60).stare.value == "terminat"
    with sesiune_tenant(tenant) as db:
        return len(continut.calendar.calendare(db, tenant))


def test_calendar_pe_30_de_zile_din_strategia_aprobata_aprobat_de_un_om_devine_livrabile(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    pana_la_strategie(tenant, om, modele)
    vazut: list[str] = []
    model_calendar(modele)
    orig = modele.handlere["Propune calendarul de conținut"]
    modele.handlere["Propune calendarul de conținut"] = lambda c: (vazut.append(prompt_complet(c)), orig(c))[
        1
    ]
    assert propune(tenant, om, f"cal:{tenant}:1") == 1
    assert "Strategie aprobată (90 de zile)" in vazut[0] and "Etiopia Guji" in vazut[0]
    with sesiune_tenant(tenant, om) as db:
        [cal] = continut.calendar.calendare(db, tenant)
        assert cal.stare == "propus" and cal.zile == 30 and cal.strategie_versiune >= 1
        sloturi = continut.calendar.intrari(db, cal.id)
        assert len(sloturi) == 21 and all(s.livrabil_id is None for s in sloturi)
        with pytest.raises(continut.calendar.EroareCalendar, match="doar de un om"):
            continut.calendar.aproba(db, cal.id, utilizator_id=None)  # type: ignore[arg-type]
        livrabile = continut.calendar.aproba(db, cal.id, utilizator_id=om)
    with sesiune_tenant(tenant) as db:
        cal = continut.calendar.citeste(db, cal.id)
        assert cal is not None and cal.stare == "aprobat" and cal.decis_de == om
        sloturi = continut.calendar.intrari(db, cal.id)
        assert [s.livrabil_id for s in sloturi] == livrabile
        zile = {s.slot_la.astimezone(continut.calendar.FUS).date() for s in sloturi}
        assert min(zile) == INCEPUT and max(zile) >= INCEPUT + dt.timedelta(days=23)
        for s in sloturi:
            lv = productie.citeste(db, s.livrabil_id)  # type: ignore[arg-type]
            assert (
                lv is not None and lv.stare == "planificat" and lv.termen_la == s.slot_la and lv.tip == s.tip
            )
        assert {s.tip for s in sloturi} == {"postare", "script_video_scurt"}
        with pytest.raises(continut.calendar.EroareCalendar, match="se decide doar unul propus"):
            continut.calendar.aproba(db, cal.id, utilizator_id=om)


def test_fara_strategie_aprobata_nu_se_propune_si_un_calendar_invalid_e_refuzat(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    model_calendar(modele)
    assert propune(tenant, om, f"cal:{tenant}:fara") == 0  # fără strategie aprobată
    pana_la_strategie(tenant, om, modele)
    model_calendar(modele, calendar_valid(formate=[{"canal": "tiktok", "tip": "postare", "pe_saptamana": 3}]))
    assert propune(tenant, om, f"cal:{tenant}:tiktok") == 0  # canal care nu e în strategie
    with sesiune_tenant(tenant) as db:
        assert continut.calendar.calendare(db, tenant) == []
        with pytest.raises(creier.RegulaCreier):
            continut.calendar.propune(db, tenant_id=uuid.uuid4(), utilizator_id=None, inceput=INCEPUT)


def test_ecranul_calendar_aproba_si_respinge(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float],
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None,
) -> None:  # fmt: skip
    pana_la_strategie(tenant, om, modele)
    model_calendar(modele)
    propune(tenant, om, f"cal:{tenant}:a")
    propune(tenant, om, f"cal:{tenant}:b")
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    html = client.get(f"/calendar/{tenant}").text
    assert "Calendar ·" in html and "Cafea proaspătă" in html and html.count("în așteptare") == 2
    with sesiune_tenant(tenant) as db:
        a, b = continut.calendar.calendare(db, tenant)
    r = client.post(
        f"/calendar/{tenant}/{a.id}/respinge",
        data={"csrf_token": csrf(client, f"/calendar/{tenant}"), "motiv": "x"},
    )
    assert r.status_code == 422
    r = client.post(
        f"/calendar/{tenant}/{a.id}/respinge",
        data={"csrf_token": csrf(client, f"/calendar/{tenant}"), "motiv": "Prea multe postări despre preț"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    r = client.post(
        f"/calendar/{tenant}/{b.id}/aproba",
        data={"csrf_token": csrf(client, f"/calendar/{tenant}")},
        follow_redirects=False,
    )
    assert r.status_code == 303
    html = client.get(f"/calendar/{tenant}?mesaj=aprobat").text
    assert (
        "sloturile au devenit livrabile" in html
        and "Prea multe postări despre preț" in html
        and "Planificat" in html
    )
