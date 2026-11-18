"""F12.1 — CRM-ul minimal. „Gata când”: un lead din formular apare cu sursă și temei, iar același lead trimis
de două ori nu se dublează. Plus: etapele, istoricul consimțământului, unirea duplicatelor, sarcinile de
urmărire, ecranul și exportul."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text

from app import worker
from app.connectors.email import CutiePostalaSimulata
from app.conturi import Rol
from app.crm import Activitate, Consimtamant, Contact, CrmRefuzat, Firma, LeadCrm, Sarcina, registru
from app.db import sesiune_agentie
from app.operare import motor
from tests.integration.conftest import Cont
from tests.integration.test_site_audit import date as date_formular
from tests.integration.utile_crm import TABELE_CRM
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_site import asteapta, cutie, link_din  # noqa: F401

pytestmark = pytest.mark.db
TABELE = TABELE_CRM
ACUM = dt.datetime.now(dt.UTC)


@pytest.fixture(autouse=True)
def _curat(admin_engine: Engine) -> None:
    with admin_engine.begin() as c:  # CRM-ul e al agenției, comun pe sesiunea de teste
        for t in TABELE:
            c.execute(text(f"DELETE FROM {t}"))


def numar() -> dict[str, int]:
    with sesiune_agentie() as db:
        return {
            m.__tablename__.removeprefix("crm_"): db.execute(select(func.count()).select_from(m)).scalar_one()
            for m in (Firma, Contact, LeadCrm, Consimtamant, Activitate)
        }


def primeste(**kw: object) -> uuid.UUID:
    date: dict[str, object] = {"email": "ana@zorilor.example", "firma": "Cafeneaua Zorilor", "sursa": "formular_audit"}  # fmt: skip
    with sesiune_agentie() as db:
        return registru.primeste(db, **{**date, **kw})[0].id  # type: ignore[arg-type]


def lead(lid: uuid.UUID) -> LeadCrm:
    with sesiune_agentie() as db:
        r = db.get(LeadCrm, lid)
        assert r is not None
        db.expunge(r)
        return r


def test_un_lead_din_formular_apare_cu_sursa_si_temei_si_nu_se_dubleaza(
    client: TestClient, cutie: CutiePostalaSimulata, executor: None, fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float], admin_engine: Engine,
) -> None:  # fmt: skip
    email = f"crm-{uuid.uuid4().hex[:8]}@zorilor.example"
    assert client.post("/site/audit", data=date_formular(client, email=email)).status_code == 200
    assert numar()["leaduri"] == 0, "fără confirmarea adresei, lead-ul nu intră în CRM"
    [confirmare] = asteapta(lambda: cutie.catre(email))
    cale = urlsplit(link_din(confirmare.text, "/audit/confirma/")).path
    assert client.get(cale).status_code == 200
    with sesiune_agentie() as db:
        [(l1, contact, firma)] = registru.lista(db)
        assert (l1.sursa, l1.temei, l1.etapa) == ("formular_audit", "solicitare_si_opt_in", "nou")
        assert l1.lead_site_id is not None and contact.email == email
        assert (firma.nume, firma.domeniu) == ("Cafeneaua Zorilor", "zorilor.example")
        [c] = db.execute(select(Consimtamant)).scalars()
        assert (c.scop, c.acordat, c.sursa, c.temei) == ("email_audit", True, "formular_audit", "solicitare_si_opt_in")  # fmt: skip
        assert "opt-in dublu" in c.dovada
    inainte = numar()
    assert inainte == {"firme": 1, "contacte": 1, "leaduri": 1, "consimtamant": 1, "activitati": 1}

    # același lead trimis a doua oară: din formular, din linkul de confirmare și direct, pe aceeași ușă
    assert client.post("/site/audit", data=date_formular(client, email=email)).status_code == 200
    client.get(cale)
    primeste(email=email.upper(), firma="Cafeneaua Zorilor SRL", site_url="https://www.zorilor.example/")
    primeste(email=email, lead_site_id=l1.lead_site_id)
    assert numar() == inainte, "nimic nu se dublează"

    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    assert 'href="/crm"' in client.get("/meniu").text
    h = client.get("/crm").text
    assert (
        "Cafeneaua Zorilor" in h
        and "formularul de audit" in h
        and "a cerut auditul și a confirmat adresa" in h
    )
    h = client.get(f"/crm/lead/{l1.id}").text
    assert "Istoricul consimțământului" in h and "<strong>acordat</strong>" in h and email in h
    with admin_engine.connect() as c:
        assert c.execute(
            text("SELECT detalii->>'temei' FROM jurnal_audit WHERE actiune = 'crm.lead_primit' AND obiect_id = :i"),
            {"i": str(l1.id)},
        ).scalar_one() == "solicitare_si_opt_in"  # fmt: skip


def test_firma_se_recunoaste_dupa_domeniu_sau_nume_dar_omonimele_raman_separate() -> None:
    primeste()
    primeste(
        email="dan@zorilor.example", firma="Zorilor Cafe", site_url="www.zorilor.example"
    )  # alt nume, nu contează: fără domeniu la prima
    primeste(email="ion@alt.example", firma="cafeneaua zorilor s.r.l.")
    assert numar()["firme"] == 2 and numar()["contacte"] == 3
    with sesiune_agentie() as db:
        assert db.execute(select(func.count()).select_from(Firma).where(Firma.domeniu == "zorilor.example")).scalar_one() == 1  # fmt: skip
    # același nume, alt domeniu: altă firmă
    primeste(email="eva@zorilor-cluj.example", firma="Zorilor Cafe", site_url="zorilor-cluj.example")
    assert numar()["firme"] == 3
    for gresit in ({"email": "nu-e-email"}, {"firma": "x"}, {"sursa": "lista_tinta"}):
        with pytest.raises(CrmRefuzat):
            primeste(**gresit)


def test_etapele_motivul_la_pierdut_si_un_singur_lead_deschis(admin_engine: Engine) -> None:
    lid = primeste()
    with sesiune_agentie() as db:
        with pytest.raises(CrmRefuzat, match="nu se poate trece"):
            registru.muta_etapa(db, lid, "castigat", utilizator_id=None)
        with pytest.raises(CrmRefuzat, match="de ce s-a pierdut"):
            registru.muta_etapa(db, lid, "pierdut", utilizator_id=None)
        for etapa in ("calificat", "apel_programat", "oferta_trimisa"):
            registru.muta_etapa(db, lid, etapa, utilizator_id=None)
    assert primeste(sursa="recomandare") == lid, "cât lead-ul e deschis, o nouă intrare îl regăsește"
    assert numar()["leaduri"] == 1
    with sesiune_agentie() as db:
        registru.muta_etapa(db, lid, "pierdut", utilizator_id=None, motiv="a ales altă agenție")
        with pytest.raises(CrmRefuzat):
            registru.muta_etapa(db, lid, "calificat", utilizator_id=None)
    assert (lead(lid).etapa, lead(lid).motiv_pierdere) == ("pierdut", "a ales altă agenție")
    with admin_engine.connect() as c:  # 17.9: motivul ajunge la învățare, ca eveniment
        assert c.execute(
            text("SELECT date->>'motiv' FROM jurnal_evenimente WHERE tip = 'lead.pierdut' AND obiect_id = :i"),
            {"i": str(lid)},
        ).scalar_one() == "a ales altă agenție"  # fmt: skip
    nou = primeste(sursa="recomandare")
    assert nou != lid and numar()["leaduri"] == 2 and numar()["contacte"] == 1
    with sesiune_agentie() as db:
        f = registru.fisa(db, nou)
        assert f is not None and [a.tip for a in f["activitati"]] == ["intrare"]
        f_vechi = registru.fisa(db, lid)
        assert f_vechi is not None
        assert [a.tip for a in f_vechi["activitati"]] == [
            "intrare",
            "etapa",
            "etapa",
            "etapa",
            "intrare",
            "etapa",
        ]


def test_consimtamantul_e_un_istoric_iar_recomandarea_nu_aduce_acord() -> None:
    lid = primeste()
    with sesiune_agentie() as db:
        cid = lead(lid).contact_id
        assert registru.are_consimtamant(db, cid, "email_audit")
        assert registru.noteaza_consimtamant(
            db, cid, "email_audit", acordat=False, sursa="panou", temei="retragere_la_cerere", dovada="a scris pe email"
        )  # fmt: skip
        assert not registru.noteaza_consimtamant(
            db, cid, "email_audit", acordat=False, sursa="panou", temei="retragere_la_cerere"
        ), "aceeași stare nu se scrie de două ori"
        assert not registru.are_consimtamant(db, cid, "email_audit")
        assert registru.scopuri_acordate(db, cid) == []
    primeste(sursa="recomandare")  # o recomandare ulterioară nu reface acordul retras
    with sesiune_agentie() as db:
        assert not registru.are_consimtamant(db, cid, "email_audit")
        f = registru.fisa(db, lid)
        assert f is not None and [c.acordat for c in f["consimtamant"]] == [False, True], "istoricul rămâne"
    rid = primeste(email="maria@recomandata.example", firma="Florăria Mariei", sursa="recomandare")
    with sesiune_agentie() as db:
        assert registru.scopuri_acordate(db, lead(rid).contact_id) == []
        assert lead(rid).temei == "introducere_personala"


def test_unirea_duplicatelor_nu_sterge_nimic_si_pastreaza_retragerea(admin_engine: Engine) -> None:
    a = primeste(email="ana@zorilor.example", firma="Cafeneaua Zorilor", site_url="zorilor.example")
    with admin_engine.begin() as c:  # o firmă duplicat, cum ar rămâne după un import vechi
        fid = uuid.uuid4()
        c.execute(
            text("INSERT INTO crm_firme (id, nume, nume_norm) VALUES (:i, 'Cafeneaua Zorilor SRL', 'cafeneaua zorilor')"),
            {"i": fid},
        )  # fmt: skip
        cid = uuid.uuid4()
        c.execute(
            text(
                "INSERT INTO crm_contacte (id, firma_id, email, sursa, temei) "
                "VALUES (:i, :f, 'ana.personal@alt.example', 'formular_audit', 'solicitare_si_opt_in')"
            ),
            {"i": cid, "f": fid},
        )
        c.execute(
            text("INSERT INTO crm_firme (id, nume, nume_norm, domeniu) VALUES (:i, 'Hotel Central', 'hotel central', 'central-iasi.example')"),
            {"i": uuid.uuid4()},
        )  # fmt: skip
        c.execute(
            text("INSERT INTO crm_firme (id, nume, nume_norm, domeniu) VALUES (:i, 'Hotel Central', 'hotel central', 'central-cluj.example')"),
            {"i": uuid.uuid4()},
        )  # fmt: skip
    b = primeste(email="ana.personal@alt.example", firma="Cafeneaua Zorilor SRL")
    assert b != a
    with sesiune_agentie() as db:
        assert registru.uneste_firme_duplicate(db) == 1, "omonimele cu domenii diferite rămân separate"
        assert registru.uneste_firme_duplicate(db) == 0
        duplicat = db.get(Firma, fid)
        assert duplicat is not None and duplicat.unita_in == lead(a).firma_id
    assert lead(b).firma_id == lead(a).firma_id and numar()["firme"] == 4, "rândul duplicat rămâne, marcat"

    # aceeași persoană cu două adrese: omul unește; retragerea de pe adresa duplicat se păstrează
    om = None
    with admin_engine.connect() as c:
        om = c.execute(text("SELECT id FROM utilizatori LIMIT 1")).scalar_one_or_none()
    with sesiune_agentie() as db:
        registru.noteaza_consimtamant(
            db, cid, "email_audit", acordat=False, sursa="panou", temei="retragere_la_cerere"
        )
        pastrat = lead(a).contact_id
        with pytest.raises(CrmRefuzat):
            registru.uneste_contacte(db, pastrat, pastrat, utilizator_id=om)  # type: ignore[arg-type]
        registru.uneste_contacte(db, pastrat, cid, utilizator_id=om)  # type: ignore[arg-type]
        assert not registru.are_consimtamant(db, pastrat, "email_audit"), "retragerea câștigă"
        with pytest.raises(CrmRefuzat):
            registru.uneste_contacte(db, pastrat, cid, utilizator_id=om)  # type: ignore[arg-type]
    assert lead(b).contact_id == pastrat and (lead(b).etapa, lead(b).motiv_pierdere) == ("pierdut", "duplicat al altui lead")  # fmt: skip
    assert lead(a).etapa == "nou" and numar()["contacte"] == 2
    assert primeste(email="ana.personal@alt.example", firma="Cafeneaua Zorilor") != b, "adresa unită e liberă pentru un contact nou"  # fmt: skip


def test_sarcinile_de_urmarire_apar_o_singura_data_si_se_anuleaza_la_schimbarea_etapei() -> None:
    vechi = primeste(acum=ACUM - dt.timedelta(days=2))
    primeste(email="azi@proaspat.example", firma="Firma de Azi")
    with sesiune_agentie() as db:
        assert registru.urmarire(db, ACUM) == 1 and registru.urmarire(db, ACUM) == 0
        [(s, firma)] = registru.sarcini_deschise(db)
        assert (
            s.lead_id == vechi
            and s.titlu == "Ia legătura cu lead-ul nou"
            and firma.nume == "Cafeneaua Zorilor"
        )
        registru.muta_etapa(db, vechi, "calificat", utilizator_id=None, acum=ACUM)
        assert registru.sarcini_deschise(db) == []
        assert (
            registru.urmarire(db, ACUM + dt.timedelta(days=4)) == 2
        )  # „propune un apel” + lead-ul de azi, rămas nou
        assert registru.creeaza_sarcina(db, vechi, "Trimite exemplele promise", ACUM.date())
        with pytest.raises(CrmRefuzat):
            registru.creeaza_sarcina(db, vechi, "x", ACUM.date())
        manuala = next(s for s, _ in registru.sarcini_deschise(db) if s.cheie.startswith("manual:"))
        registru.inchide_sarcina(db, manuala.id)
        with pytest.raises(CrmRefuzat):
            registru.inchide_sarcina(db, manuala.id)
        assert db.get(Sarcina, manuala.id).stare == "facuta"  # type: ignore[union-attr]
    assert "app.crm" in worker.MODULE_FLUXURI
    registru.declara_programari()
    assert any(p.nume == registru.NUME_JOB for p in motor.programari_declarate())
    assert registru.igiena(ACUM + dt.timedelta(days=4)) == (0, 0)


def test_ecranul_recomandarea_etapa_si_exportul(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float]
) -> None:
    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    jeton = csrf(client, "/crm")
    date = {
        "csrf_token": jeton, "firma": "=Florăria Mariei", "email": "maria@florarie.example",
        "nume": "Maria Pop", "telefon": "+40 700 000 000", "dovada": "prezentată de Dan, la târg",
    }  # fmt: skip
    assert client.post("/crm/lead", data={**date, "email": "gresit"}).status_code == 422
    assert (
        client.post("/crm/lead", data={k: v for k, v in date.items() if k != "csrf_token"}).status_code == 403
    )
    r = client.post("/crm/lead", data=date, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("mesaj=adaugat")
    cale = r.headers["location"].split("?")[0]
    r = client.post("/crm/lead", data=date, follow_redirects=False)
    assert r.headers["location"] == f"{cale}?mesaj=existent", "aceeași recomandare nu se dublează"
    h = client.get(cale).text
    assert "introducere personală" in h and "prezentată de Dan, la târg" in h and "Niciun rând." in h

    assert client.post(f"{cale}/etapa", data={"csrf_token": jeton, "etapa": "castigat"}).status_code == 422
    assert client.post(f"{cale}/etapa", data={"csrf_token": jeton, "etapa": "pierdut"}).status_code == 422
    assert client.post(f"{cale}/etapa", data={"csrf_token": jeton, "etapa": "calificat"}, follow_redirects=False).status_code == 303  # fmt: skip
    assert client.post(f"{cale}/nota", data={"csrf_token": jeton, "nota": "Vrea ofertă în martie."}, follow_redirects=False).status_code == 303  # fmt: skip
    assert client.post(f"{cale}/sarcina", data={"csrf_token": jeton, "titlu": "Sună joi", "scadenta": "nu-e-data"}).status_code == 422  # fmt: skip
    assert client.post(f"{cale}/sarcina", data={"csrf_token": jeton, "titlu": "Sună joi", "scadenta": "2031-01-09"}, follow_redirects=False).status_code == 303  # fmt: skip
    h = client.get(cale).text
    assert "Etapă: nou → calificat." in h and "Vrea ofertă în martie." in h and "Sună joi · 09.01.2031" in h
    h = client.get("/crm?etapa=calificat").text
    assert "Florăria Mariei" in h and "Calificat (1)" in h and "Sună joi" in h
    assert "Florăria Mariei" not in client.get("/crm?etapa=nou").text.split('id="leaduri"')[1]
    with sesiune_agentie() as db:
        [(s, _)] = registru.sarcini_deschise(db)
    assert client.post(f"/crm/sarcina/{s.id}/inchide", data={"csrf_token": jeton}, follow_redirects=False).status_code == 303  # fmt: skip
    assert client.post(f"/crm/sarcina/{s.id}/inchide", data={"csrf_token": jeton}).status_code == 422

    r = client.get("/crm/export.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    randuri = r.text.strip().splitlines()
    assert randuri[0].startswith("firma,domeniu,email,nume,telefon,sursa,temei,etapa")
    assert (
        "'=Florăria Mariei" in randuri[1]
        and "'+40 700 000 000" in randuri[1]
        and "introducere_personala" in randuri[1]
    )
    for gresit in ("/crm?etapa=altceva", "/crm/lead/nu-e-id", f"/crm/lead/{uuid.uuid4()}"):
        assert client.get(gresit).status_code == 404
    assert client.post(f"{cale}/altceva", data={"csrf_token": jeton}).status_code == 404


def test_operatorul_nu_are_crm(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float]
) -> None:
    autentifica(client, fabrica_conturi(Rol.OPERATOR, cu_totp=True), ceas)
    assert client.get("/crm").status_code == 403 and client.get("/crm/export.csv").status_code == 403
    assert 'href="/crm"' not in client.get("/meniu").text
