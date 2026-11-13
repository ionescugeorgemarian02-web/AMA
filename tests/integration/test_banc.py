"""F5.7 — bancul de evaluare (K4): cascada rulează izolat pe seturile de aur, pe clienți de probă creați și
ANULAȚI, calculează
pe validator matricea de confuzie, precizia și recall-ul, rata de blocare a celor greșite și respingerile pe
nedrept; rezultatul
se salvează și se vede în panou. „Gata când”: bancul rulează dintr-o atingere și arată scorurile."""

import datetime as dt
import json
import time
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.conturi import Rol
from app.db import sesiune_agentie
from app.validare import banc
from app.validare.banc import __main__ as cli
from app.validare.banc import executie, seturi
from app.validare.banc.seturi import Exemplu, Seturi
from tests.conftest import BazaTest
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica, csrf

pytestmark = pytest.mark.db
TABELE_NUMARATE = ("clienti", "utilizatori", "creier_intrari", "surse", "pasaje", "jurnal_audit")


def _numara(engine: Engine) -> dict[str, int]:
    with engine.connect() as c:
        return {t: c.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in TABELE_NUMARATE}


@pytest.fixture(scope="module")
def rulare(baza: BazaTest, admin_engine: Engine) -> dict[str, Any]:
    inainte = _numara(admin_engine)
    sc = executie.ruleaza(seturi.incarca())
    return {"scoruri": sc, "inainte": inainte, "dupa": _numara(admin_engine)}


def test_bancul_calculeaza_scorurile_pe_fiecare_validator(rulare: dict[str, Any]) -> None:
    sc = rulare["scoruri"]
    s = seturi.incarca()
    assert sc["exemple"] == s.numar() and sc["amprenta_seturi"] == s.amprenta
    assert set(sc["validatori"]) == set(seturi.VALIDATORI)
    for g, v in sc["validatori"].items():
        assert v["exemple"] == len(s.aur[g]) and v["tp"] + v["fp"] + v["fn"] + v["tn"] == v["exemple"]
        assert {"precizie", "recall", "rata_fals_pozitive", "matrice", "gresite"} <= set(v)
        assert sum(sum(r.values()) for r in v["matrice"].values()) == v["exemple"]
    assert sc["rele"]["total"] == len(s.rele) and sc["bune"]["total"] == len(s.bune)
    assert sum(d["total"] for d in sc["rele"]["pe_validator"].values()) == len(s.rele)
    assert sc["omise"] == ["G4@V2", "G7@V2"], "pașii cu vectori nu se pretind măsurați"
    json.dumps(sc)  # se poate salva ca JSON


def test_bancul_nu_lasa_nimic_in_baza(rulare: dict[str, Any]) -> None:
    assert rulare["dupa"] == rulare["inainte"]


def test_un_exemplu_promovat_de_un_om_intra_in_rulare(baza: BazaTest) -> None:
    la = dt.datetime(2026, 11, 12, 12, tzinfo=dt.UTC)
    contexte = seturi.citeste_contexte()[1]
    promovat = Exemplu(
        id="p-1", set="promovat:G10", ctx="gol", tip="postare", canal="facebook",
        text="Cafeaua noastra e proaspat prajita si o gasesti in fiecare dimineata la cafenea.",
        asteptat="esec", severitate="majora", motiv="diacritice lipsă", validator="G10",
    )  # fmt: skip
    sc = executie.ruleaza(Seturi(la=la, contexte=contexte, aur={}, rele=(), bune=(), promovate=(promovat,)))
    assert sc["validatori"]["G10"]["exemple"] == 1 and sc["validatori"]["G10"]["promovate"] == 1
    assert sc["validatori"]["G10"]["tp"] == 1


def test_comanda_din_terminal_afiseaza_si_salveaza(
    rulare: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(executie, "ruleaza", lambda _s: rulare["scoruri"])
    cod = cli.main([])
    iesire = capsys.readouterr().out
    assert cod == (0 if rulare["scoruri"]["poarta"]["trece"] else 1)
    assert "Poarta F5" in iesire and "G2" in iesire and "Precizie" in iesire
    with sesiune_agentie() as db:
        ultima = banc.depozit.ultima_terminata(db)
        assert (
            ultima is not None and ultima.scoruri["amprenta_seturi"] == rulare["scoruri"]["amprenta_seturi"]
        )
    assert json.loads(_json(cli, monkeypatch, capsys))["poarta"] == rulare["scoruri"]["poarta"]


def _json(modul: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> str:
    modul.main(["--json", "--fara-salvare"])
    return capsys.readouterr().out


@pytest.fixture
def proprietar(client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float]) -> Cont:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    return cont


def test_butonul_din_panou_porneste_bancul_ca_job_durabil_si_scorurile_se_vad(
    client: TestClient,
    proprietar: Cont,
    porneste_executor: Callable[..., None],
    rulare: dict[str, Any],
    admin_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        executie, "ruleaza", lambda _s: rulare["scoruri"]
    )  # aceleași scoruri, fără a doua rulare lentă
    porneste_executor()
    assert client.post("/validatoare/banc/porneste", data={}).status_code == 403, "fără CSRF nu pornește"
    r = client.post(
        "/validatoare/banc/porneste",
        data={"csrf_token": csrf(client, "/validatoare")},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/validatoare?mesaj=banc"
    with admin_engine.connect() as c:
        rid, pornit_de = c.execute(
            text("SELECT id, pornit_de FROM banc_rulari ORDER BY pornit_la DESC LIMIT 1")
        ).one()
        assert pornit_de == proprietar.id
        audit = c.execute(
            text(
                "SELECT utilizator_id FROM jurnal_audit WHERE actiune = 'validare.banc_pornit' AND obiect_id = :i"
            ),
            {"i": str(rid)},
        ).all()
    assert [a[0] for a in audit] == [proprietar.id]
    limita = time.monotonic() + 30
    stare = "in_curs"
    while stare == "in_curs" and time.monotonic() < limita:
        time.sleep(0.1)
        with admin_engine.connect() as c:
            stare = c.execute(text("SELECT stare FROM banc_rulari WHERE id = :i"), {"i": rid}).scalar_one()
    assert stare == "terminat"
    html = client.get("/validatoare").text
    p = rulare["scoruri"]["poarta"]
    assert f"<strong>{p['rele_blocate']}</strong> din {p['rele_total']}" in html
    assert "Precizie · recall" in html and 'aria-labelledby="v-G2"' in html and "Matricea de confuzie" in html
    detaliu = client.get(f"/validatoare/banc/{rid}")
    assert detaliu.status_code == 200 and "Poarta F5" in detaliu.text
    assert client.get(f"/validatoare/banc/{uuid.uuid4()}").status_code == 404


def test_doar_proprietarul_vede_si_porneste_bancul(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float]
) -> None:
    operator = fabrica_conturi(Rol.OPERATOR, cu_totp=True)
    autentifica(client, operator, ceas)
    assert client.get("/validatoare").status_code == 403
    assert client.post("/validatoare/banc/porneste", data={"csrf_token": csrf(client)}).status_code == 403
