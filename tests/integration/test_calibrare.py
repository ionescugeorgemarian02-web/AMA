"""F5.8 — calibrarea judecătorilor (G14). „Gata când”: acordul cu etichetele umane este măsurat pentru
fiecare judecător.
Verdictele sunt REALE (salvate de cascadă, cu judecătorul de limbă G10@V3 servit de un model FALS); etichetele
umane
sunt SIMULATE în test (o parte prin ecranul din panou, cu CSRF)."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.conturi import Rol
from app.db import sesiune_agentie
from app.operare import motor, notificari
from app.operare.motor import Coada
from app.validare import calibrare, exemple, fluxuri
from app.validare.modele import EtichetaCalibrare
from tests.furnizor_fals import CerereInregistrata
from tests.gateway_utile import ceas_controlat, cheie_proba, fabrica_modele, fals  # noqa: F401
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import prompt_complet
from tests.validare_utile import (  # noqa: F401
    JudecatorFals,
    judecator,
    livrabil_in_validare,
    raspuns,
    registru_doar,
    rubrica,
    ruleaza,
)

pytestmark = pytest.mark.db
FRAZA = "Ești un corector de limba română"
GRESEALA = "Cafelele noastră"
BUN = "Sâmbătă la 11:00 facem degustare la cafenea. Vino să guști cafeaua proaspăt prăjită, varianta {i}."
DE_LA, PANA_LA = dt.datetime(2000, 1, 1, tzinfo=dt.UTC), dt.datetime(2100, 1, 1, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def _ceas(ceas_controlat: object) -> None:
    """Gateway-ul (jurnalul de apeluri, contoarele) merge pe ceasul controlat, nu pe cel real."""


def _raspuns_judecator(c: CerereInregistrata) -> str:
    if GRESEALA in prompt_complet(c):
        return rubrica(raspuns("acord", False, GRESEALA, "acord greșit"), raspuns("registru", True))
    return rubrica(raspuns("acord", True), raspuns("registru", True))


@pytest.fixture
def verdicte_reale(
    tenant: uuid.UUID, judecator: JudecatorFals, admin_engine: Engine
) -> dict[str, list[uuid.UUID]]:
    """10 texte pe care judecătorul le blochează și 12 pe care le trece, prin cascada reală (G1 + G10, cu
    V3)."""
    with (
        admin_engine.begin() as c
    ):  # alte teste pot fi lăsat verdicte V3: eșantionul de aici e doar al acestui client
        c.execute(text("DELETE FROM calibrare_etichete"))
    judecator.raspunde(FRAZA, _raspuns_judecator)
    ids: dict[str, list[uuid.UUID]] = {"blocate": [], "trecute": []}
    with registru_doar("G1", "G10"):
        for i in range(22):
            blocat = i < 10
            t = BUN.format(i=i) + (f" {GRESEALA} sunt gustoase." if blocat else "")
            lid = livrabil_in_validare(tenant, t, model_autor=judecator.cod_autor)
            ruleaza(tenant, lid, judecatori=True)
            ids["blocate" if blocat else "trecute"].append(lid)
    return ids


def _ale_clientului(tenant: uuid.UUID) -> list[EtichetaCalibrare]:
    with sesiune_agentie() as db:
        noi = calibrare.esantioneaza(db, DE_LA, PANA_LA, n=100, saminta="test")
        return [e for e in noi if e.tenant_id == tenant]


def test_acordul_cu_etichetele_umane_este_masurat_pe_judecator(
    tenant: uuid.UUID, verdicte_reale: dict[str, list[uuid.UUID]], monkeypatch: pytest.MonkeyPatch
) -> None:
    trimise: list[str] = []
    monkeypatch.setattr(notificari, "notifica", lambda _n, _t, txt, **_k: trimise.append(txt) or {})
    coada = _ale_clientului(tenant)
    assert len(coada) == 22 and {e.judecator for e in coada} == {"G10@V3"}
    assert sum(e.judecator_esec for e in coada) == 10
    assert all("validare.g10_limba@1" in e.versiune for e in coada)
    with sesiune_agentie() as db:  # a doua rulare nu dublează coada
        assert [e for e in calibrare.esantioneaza(db, DE_LA, PANA_LA, n=100) if e.tenant_id == tenant] == []
    om_id = _proprietar_id()
    gresite = [e for e in coada if e.judecator_esec][:4]
    with sesiune_agentie(om_id) as db:
        for e in coada:
            gresit = e in gresite
            _, propus = calibrare.eticheteaza(
                db,
                e.id,
                eticheta="gresit" if gresit else "corect",
                motiv="acordul era corect" if gresit else "",
                utilizator_id=om_id,
                acum=dt.datetime(2026, 11, 16, 9, tzinfo=dt.UTC),
            )
            assert (propus is not None) is gresit
        s = calibrare.statistici(db)["G10@V3"]
        assert (s["etichete"], s["corecte"], s["procent"]) == (22, 18, pytest.approx(0.8182, abs=1e-4))
        assert s["kappa"] is not None and s["interval"][0] < s["procent"] < s["interval"][1]
        assert s["sub_prag"] is True and s["de_etichetat"] == 0
        alerte = calibrare.verifica_si_anunta(db, DE_LA, PANA_LA)
        propuse = [x for x in exemple.listeaza(db) if x.tenant_id == tenant]
    assert any("G10@V3" in a and "82%" in a for a in alerte) and trimise == alerte
    # verdictul greșit devine exemplu PROPUS (nu scris în seturi): eticheta corectă este opusul judecătorului
    assert len(propuse) == 4 and all(p.sursa == "eticheta" and p.asteptat == "trece" for p in propuse)
    with sesiune_agentie(om_id) as db, pytest.raises(calibrare.EtichetaInvalida):
        calibrare.eticheteaza(db, coada[0].id, eticheta="corect", motiv="", utilizator_id=om_id)


def _proprietar_id() -> uuid.UUID:
    from app.conturi.servicii import Actor, creeaza_utilizator

    with sesiune_agentie() as db:
        return creeaza_utilizator(
            db,
            email=f"o{uuid.uuid4().hex[:8]}@exemplu.test",
            parola="parola-de-proba-1",
            nume_afisat="Om",
            rol=Rol.PROPRIETAR,
            tenant_id=None,
            actor=Actor.cli(),
        ).id


def test_ecranul_de_etichetare_din_panou(
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
    tenant: uuid.UUID,
    verdicte_reale: dict[str, list[uuid.UUID]],
    admin_engine: Engine,
) -> None:
    coada = _ale_clientului(tenant)
    proprietar = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, proprietar, ceas)
    html = client.get("/validatoare/calibrare").text
    assert "Acordul cu omul" in html and "G10@V3" in html and GRESEALA in html
    tinta = next(e for e in coada if e.judecator_esec)
    cale = f"/validatoare/calibrare/{tinta.id}/eticheta"
    assert client.post(cale, data={"eticheta": "corect"}).status_code == 403, "fără CSRF"
    jeton = csrf(client, "/validatoare/calibrare")
    r = client.post(
        cale, data={"csrf_token": jeton, "eticheta": "gresit", "motiv": ""}, follow_redirects=False
    )
    assert r.status_code == 303 and "eroare=" in r.headers["location"], "„greșit” fără motiv nu se salvează"
    r = client.post(
        cale,
        data={"csrf_token": jeton, "eticheta": "gresit", "motiv": "textul era corect"},
        follow_redirects=False,
    )
    assert r.headers["location"].endswith("mesaj=eticheta_gresit")
    with admin_engine.connect() as c:
        rand = c.execute(
            text("SELECT eticheta, motiv, etichetat_de FROM calibrare_etichete WHERE id = :i"),
            {"i": tinta.id},
        ).one()
        audit = c.execute(
            text(
                "SELECT count(*) FROM jurnal_audit WHERE actiune = 'calibrare.eticheta' AND utilizator_id = :u"
            ),
            {"u": proprietar.id},
        ).scalar_one()
    assert tuple(rand) == ("gresit", "textul era corect", proprietar.id) and audit == 1


def test_esantionul_saptamanal_este_job_programat(
    tenant: uuid.UUID, verdicte_reale: dict[str, list[uuid.UUID]], porneste_executor: Callable[..., None]
) -> None:
    fluxuri.declara_programari()
    assert fluxuri.NUME_CALIBRARE in [p.nume for p in motor.programari_declarate()]
    porneste_executor()
    moment = dt.datetime.now(dt.UTC) + dt.timedelta(
        minutes=1
    )  # fereastra [moment − 7 zile, moment) acoperă verdictele
    job = motor.trimite(
        fluxuri.calibrare_saptamanala, moment, None, coada=Coada.INVATARE, cheie=f"cal:{uuid.uuid4()}"
    )
    stare = motor.asteapta_flux(job, timeout_sec=30)
    assert stare.stare.value == "terminat", stare
    with sesiune_agentie() as db:
        toate = [e for e in db.query(EtichetaCalibrare).all() if e.judecator == "G10@V3"]
    # cel mult 10 pe judecător pe săptămână, pe toți clienții (aici sunt cel puțin 22 de candidați)
    assert len(toate) == 10 and any(e.tenant_id == tenant for e in toate)
