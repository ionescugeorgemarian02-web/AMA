"""F15.6 — lista de go-live (docs/25 §25.5) calculată unde se poate, bifabilă în rest; studiile de caz; T1 din
rezultatul testelor de avarie."""

import datetime as dt
import json
import re
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.conturi import Rol
from app.db import sesiune_agentie
from app.lansare import cli, golive, pilot, studii
from tests.integration.conftest import Cont, csrf_din
from tests.integration.utile_panou import autentifica

pytestmark = pytest.mark.db
ROOT = Path(__file__).resolve().parents[2]
ACUM = dt.datetime.now(dt.UTC)


@pytest.fixture(autouse=True)
def _curat(admin_engine: Engine) -> None:
    with admin_engine.begin() as c:
        c.execute(text("DELETE FROM studii_caz; DELETE FROM verificari_lansare; DELETE FROM rezultate_avarie;"
                       " DELETE FROM pilot_rapoarte; DELETE FROM pilot_feedback; DELETE FROM pilot_clienti"))  # fmt: skip


def _puncte(acum: dt.datetime | None = None) -> dict[str, dict[str, object]]:
    with sesiune_agentie() as db:
        return {str(p["cod"]): p for p in golive.evalueaza(db, acum)}


def _urme_resurse(admin: Engine, zile: int, *, la: dt.datetime, peste_in_ziua: int | None = None) -> None:
    """Urmele ticului de resurse (append-only), puse într-o fereastră proprie din viitor: nu ating alte teste."""
    with admin.begin() as c:
        for z in range(zile):
            c.execute(
                text("INSERT INTO urme (id, la, corelare_id, componenta, actiune, rezultat, iesiri) VALUES "
                     "(gen_random_uuid(), :la, 'proba', 'resurse', 'verifica', :r, CAST(:i AS jsonb))"),
                {"la": la - dt.timedelta(days=z, minutes=5), "r": "esec" if z == peste_in_ziua else "ok",
                 "i": json.dumps({"backup_bun": True})},
            )  # fmt: skip


def test_lista_e_exact_cea_din_25_5_plus_palnia_de_audit() -> None:
    doc = (ROOT / "docs" / "25-testare-lansare-pe-vps-si-criterii-de-go-live.md").read_text()
    sectiune = doc.split("### 25.5", 1)[1].split("\n### ", 1)[0]
    din_doc = re.findall(r"^- \[ \] (.+)$", sectiune, flags=re.M)
    assert [p.text for p in golive.PUNCTE if p.cod not in golive.EXTRA] == din_doc
    assert len({p.cod for p in golive.PUNCTE}) == len(golive.PUNCTE)


def test_t1_vine_din_rularea_de_avarie_pe_staging(tmp_path: Path) -> None:
    assert _puncte()["T1"]["auto"] is False
    raport = {"schema": "ama.avarie/1", "trecute": 13, "total": 14, "scenarii": []}
    (tmp_path / "r.json").write_text(json.dumps(raport))
    assert cli.main(["avarie", str(tmp_path / "r.json"), "--mediu", "staging"]) == 0
    t1 = _puncte()["T1"]
    assert t1["auto"] is False and "13/14" in str(t1["detaliu"])
    with sesiune_agentie() as db:
        golive.inregistreaza_avarie(db, {**raport, "trecute": 14}, mediu="local")  # local nu e staging
    assert _puncte()["T1"]["auto"] is False
    with sesiune_agentie() as db:
        golive.inregistreaza_avarie(db, {**raport, "trecute": 14}, mediu="staging")
    assert _puncte()["T1"]["bifat"] is True
    with pytest.raises(ValueError, match="avarie"), sesiune_agentie() as db:
        golive.inregistreaza_avarie(db, {"schema": "alt"}, mediu="staging")


def test_limitele_si_backupul_se_calculeaza_din_urmele_de_resurse(admin_engine: Engine) -> None:
    la = ACUM + dt.timedelta(days=400 + uuid.uuid4().int % 1000)
    _urme_resurse(admin_engine, 14, la=la, peste_in_ziua=3)
    p = _puncte(la)
    assert p["T6"]["auto"] is False and "13 din ultimele 14" in str(p["T6"]["detaliu"])
    assert p["T2"]["auto"] is False  # doar 14 zile de istoric, nu 28
    la = la + dt.timedelta(days=3000)
    _urme_resurse(admin_engine, 28, la=la)
    p = _puncte(la)
    assert p["T6"]["bifat"] and p["T2"]["bifat"]


def test_bifa_manuala_cere_nota_si_nu_acopera_un_punct_calculat(om: uuid.UUID) -> None:
    with sesiune_agentie() as db:
        with pytest.raises(golive.BifaRefuzata, match="notă"):
            golive.bifeaza(db, "T5", True, nota="", utilizator_id=om)
        with pytest.raises(golive.BifaRefuzata, match="automat"):
            golive.bifeaza(db, "T1", True, nota="am verificat", utilizator_id=om)
        golive.bifeaza(db, "T5", True, nota="alertă de probă primită în 20 s", utilizator_id=om)
    p = _puncte()
    assert p["T5"]["bifat"] and p["T5"]["nota"] == "alertă de probă primită în 20 s"
    assert p["C1"]["auto"] is False, "ciornele juridice nu sunt încă semnate de avocat"
    assert p["C2"]["bifat"], "transparența AI și nișele refuzate sunt publicate"
    assert p["O1"]["se_bifeaza_manual"] and not p["O1"]["bifat"]
    with sesiune_agentie() as db:
        assert not golive.rezumat(golive.evalueaza(db))["gata"]


def test_studiile_de_caz_din_pilot_se_publica_doar_cu_acord_si_apar_pe_site(
    client: TestClient, fabrica_clienti: Callable[[], uuid.UUID], om: uuid.UUID
) -> None:
    ids = []
    for k in range(2):
        t = fabrica_clienti()
        with sesiune_agentie() as db:
            pilot.inscrie(db, t, pret_lunar_bani=50_000, utilizator_id=om, rol=Rol.PROPRIETAR)
            s = studii.ciorna_din_pilot(db, t, titlu=f"Cafeneaua {k}: patru săptămâni la L1",
                                        situatie="Postau rar, fără plan.", actiune="Pachetul Creștere, două canale.")  # fmt: skip
            assert "livrabile decise" in s.rezultat and s.cifre["decise"] == 0
            ids.append(s.id)
    assert _puncte()["C6"]["auto"] is False
    with sesiune_agentie() as db:
        with pytest.raises(studii.StudiuInvalid, match="acordul"):
            studii.publica(db, ids[0], acord_client=False, utilizator_id=om)
        for i in ids:
            studii.publica(db, i, acord_client=True, utilizator_id=om)
    assert _puncte()["C6"]["bifat"]
    h = client.get("/site/studii-de-caz").text
    assert "Cafeneaua 0: patru săptămâni la L1" in h and "Publicat cu acordul clientului" in h


def test_ecranul_de_go_live_arata_toate_punctele_si_bifeaza_cu_csrf(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float]
) -> None:
    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    h = client.get("/lansare/go-live").text
    for p in golive.PUNCTE:
        assert f'data-punct="{p.cod}"' in h, p.cod
    assert 'data-gata="nu"' in h
    r = client.post("/lansare/go-live/O2", data={"csrf_token": csrf_din(h), "bifat": "da", "nota": "în calendar"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and "mesaj=bifa" in r.headers["location"]
    assert 'data-punct="O2" data-bifat="da"' in client.get("/lansare/go-live").text
    r = client.post("/lansare/go-live/T1", data={"csrf_token": csrf_din(h), "bifat": "da", "nota": "x" * 5},
                    follow_redirects=False)  # fmt: skip
    assert "eroare=" in r.headers["location"]
    assert client.post("/lansare/go-live/O2", data={"bifat": "da"}).status_code == 403
