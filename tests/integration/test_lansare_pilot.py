"""F15.5 — modul pilot: L1, preț de pilot, feedback săptămânal, indicatorii din urme, raportul săptămânal."""

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.conturi import Rol
from app.db import sesiune_agentie
from app.lansare import pilot
from app.productie import Clasa, Hotarare, Nivel, autonomie
from app.productie.reguli_aprobare import MOTIVE_RESPINGERE
from tests.integration.conftest import Cont, csrf_din
from tests.integration.test_productie_aprobari import cere, decide, validat
from tests.integration.utile_panou import autentifica

pytestmark = pytest.mark.db
AZI = dt.datetime.now(dt.UTC).date()


@pytest.fixture(autouse=True)
def _pilot_gol(admin_engine: Engine) -> None:
    with admin_engine.begin() as c:
        c.execute(text("DELETE FROM pilot_rapoarte; DELETE FROM pilot_feedback; DELETE FROM pilot_clienti"))


def _inscrie(t: uuid.UUID, om: uuid.UUID, **kw: object) -> pilot.PilotClient:
    with sesiune_agentie() as db:
        return pilot.inscrie(db, t, pret_lunar_bani=99_000, utilizator_id=om, rol=Rol.PROPRIETAR, **kw)  # type: ignore[arg-type]


def _decizii(t: uuid.UUID, om: uuid.UUID, rezultate: list[Hotarare]) -> None:
    for h in rezultate:
        ap = cere(t, validat(t))
        kw = (
            {"motiv_standard": next(iter(MOTIVE_RESPINGERE)), "motiv": "prea formal"}
            if h is Hotarare.RESPINS
            else {}
        )
        decide(t, ap.id, h, om, **kw)


def test_inscrierea_pune_totul_la_l1_cu_pretul_de_pilot_si_cel_mult_trei_clienti(
    fabrica_clienti: Callable[[], uuid.UUID], om: uuid.UUID
) -> None:
    t = fabrica_clienti()
    with sesiune_agentie() as db:
        for c in Clasa:
            autonomie.seteaza_nivel(
                db, t, c, Nivel.L2, utilizator_id=om, rol=Rol.PROPRIETAR, motiv="înainte de pilot"
            )
    p = _inscrie(t, om)
    assert p.pret_lunar_bani == 99_000 and p.stare == "activ" and p.saptamani == pilot.SAPTAMANI
    with sesiune_agentie() as db:
        assert set(autonomie.matrice(db, t).values()) == {Nivel.L1}
    for _ in range(2):
        _inscrie(fabrica_clienti(), om)
    with pytest.raises(pilot.PilotInvalid, match="3 clienți"):
        _inscrie(fabrica_clienti(), om)
    _inscrie(t, om)  # reînscrierea aceluiași client nu e un al patrulea


def test_indicatorii_vin_din_urme_si_raportul_saptamanal_se_salveaza(
    fabrica_clienti: Callable[[], uuid.UUID], om: uuid.UUID
) -> None:
    t, alt = fabrica_clienti(), fabrica_clienti()
    _inscrie(t, om)
    _decizii(t, om, [Hotarare.APROBAT, Hotarare.APROBAT, Hotarare.APROBAT, Hotarare.RESPINS])
    _decizii(alt, om, [Hotarare.RESPINS])  # alt client: nu intră în cifrele lui t
    with sesiune_agentie() as db:
        pilot.feedback(db, t, zi=AZI, satisfactie=4, minute_om=35, frictiuni="Aprobarea video e lentă.",
                       utilizator_id=om)  # fmt: skip
        ind = pilot.indicatori(db, t, pilot.luni(AZI), pilot.luni(AZI) + dt.timedelta(days=7))
        assert (ind.decise, ind.aprobate_din_prima, ind.rata_aprobare_din_prima) == (4, 3, 0.75)
        assert ind.incidente_critice == 0 and ind.minute_om == 35 and ind.satisfactie == 4.0
        pilot.raporteaza_incident(db, t, descriere="Postare publicată cu prețul greșit", utilizator_id=om)
        [r] = pilot.raport_saptamanal(db, AZI)
        assert r["tenant_id"] == str(t) and r["incidente_critice"] == 1 and not r["feedback_lipsa"]
        assert not r["poarta"]["trece"] and "1 incidente critice" in "; ".join(r["poarta"]["motive"])
        pilot.raport_saptamanal(db, AZI)  # idempotent pe săptămână
    with sesiune_agentie() as db:
        n = db.execute(text("SELECT count(*) FROM pilot_rapoarte WHERE tenant_id = :t"), {"t": t}).scalar()
        assert n == 1
        assert set(autonomie.matrice(db, t).values()) == {Nivel.L0}, "incidentul critic retrogradează"


def test_poarta_trece_dupa_patru_saptamani_fara_incident_cu_aprobare_peste_85(
    fabrica_clienti: Callable[[], uuid.UUID], om: uuid.UUID
) -> None:
    t = fabrica_clienti()
    p = _inscrie(t, om, inceput=AZI - dt.timedelta(days=27))
    _decizii(t, om, [Hotarare.APROBAT] * 9 + [Hotarare.RESPINS])  # 90%
    with sesiune_agentie() as db:
        assert "feedback pe 0 din 4 săptămâni" in pilot.stare_poarta(db, p, AZI)["motive"]
        for k in range(4):
            pilot.feedback(db, t, zi=p.inceput + dt.timedelta(weeks=k), satisfactie=5, minute_om=20, frictiuni="",
                           utilizator_id=om)  # fmt: skip
        st = pilot.stare_poarta(db, p, AZI)
    assert st["trece"], st
    assert st["rata_aprobare_din_prima"] == 0.9 and st["saptamani_gata"] == 4 and st["minute_om"] == 80


def test_ecranul_pilotului_cu_inscriere_feedback_incident_si_raport(
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    fabrica_clienti: Callable[[], uuid.UUID],
    ceas: dict[str, float],
) -> None:
    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    t = fabrica_clienti()
    h = client.get("/lansare/pilot").text
    assert "Niciun client în pilot" in h
    r = client.post("/lansare/pilot/inscrie", data={"csrf_token": csrf_din(h), "tenant_id": str(t), "pret_lei": 990},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    h = client.get("/lansare/pilot").text
    assert f'data-pilot="{t}"' in h and "990.00 lei" in h and 'data-poarta="nu"' in h
    for cale, date in ((f"/lansare/pilot/{t}/feedback", {"zi": AZI.isoformat(), "satisfactie": "4", "minute_om": "20"}),
                       (f"/lansare/pilot/{t}/incident", {"descriere": "Mesaj trimis fără aprobare"}),
                       ("/lansare/pilot/raport", {})):  # fmt: skip
        r = client.post(cale, data={"csrf_token": csrf_din(h), **date}, follow_redirects=False)
        assert r.status_code == 303 and "mesaj=" in r.headers["location"], cale
    h = client.get("/lansare/pilot").text
    assert "Incidente critice: 1" in h and '<th scope="row">' in h
    assert client.post("/lansare/pilot/raport", data={}).status_code == 403  # fără CSRF
