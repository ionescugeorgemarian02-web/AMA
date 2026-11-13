"""F5.9 — biroul de aprobări. „Gata când”: aprobi, respingi și editezi de pe telefon, iar motivul se salvează. Teste HTTP pe
rutele reale; livrabilele trec prin cascada reală (G1 + G10, deterministe), fără modele."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app import productie, validare
from app.conturi import Rol
from app.db import sesiune_tenant
from app.operare import notificari
from app.productie import Stare, aprobari
from app.validare import intrebari
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.validare_utile import livrabil_in_validare, registru_doar, ruleaza

pytestmark = pytest.mark.db
BUN = "Sâmbătă la 11:00 facem degustare la cafenea. Vino să guști cafeaua proaspăt prăjită și să afli cum o prepari."
EDITAT = (
    "Sâmbătă la 12:00 facem degustare la cafenea. Vino să guști cafeaua proaspăt prăjită, în loturi mici."
)


@pytest.fixture(autouse=True)
def _fara_cereri_ramase(admin_engine: Engine) -> Iterator[None]:
    """Cererile în așteptare sunt vizibile proprietarului pe toți clienții: nimic nu rămâne de la sau pentru alt test."""

    def anuleaza() -> None:
        with admin_engine.begin() as c:
            c.execute(
                text("UPDATE aprobari SET stare = 'anulat', decis_la = now() WHERE stare = 'in_asteptare'")
            )

    anuleaza()
    yield
    anuleaza()


@pytest.fixture
def proprietar(client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float]) -> Cont:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    return cont


def la_aprobare(tenant: uuid.UUID, text_: str = BUN) -> tuple[uuid.UUID, productie.Aprobare]:
    with registru_doar("G1", "G10"):
        lid = livrabil_in_validare(tenant, text_)
        assert ruleaza(tenant, lid).stare is Stare.VALIDAT
    with sesiune_tenant(tenant) as db:
        return lid, aprobari.cere(db, lid)


def stare(tenant: uuid.UUID, lid: uuid.UUID) -> productie.Livrabil:
    with sesiune_tenant(tenant) as db:
        lv = productie.citeste(db, lid)
        assert lv is not None
        return lv


def test_cardul_arata_previzualizarea_verdictele_contextul_si_versiunile(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID
) -> None:
    _, ap = la_aprobare(tenant)
    html = client.get("/aprobari").text
    assert "Previzualizare pe facebook" in html and BUN in html
    assert (
        "a trecut cascada" in html and "Pachetul de context" in html and "Istoricul versiunilor (1)" in html
    )
    assert f'action="/aprobari/{ap.id}/aproba"' in html and f'action="/aprobari/{ap.id}/editeaza"' in html
    assert "Hook slab" in html and "O frază (opțional)" in html


def test_respingerea_cu_motiv_standard_se_salveaza_si_intra_in_statistica(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, admin_engine: Engine
) -> None:
    lid, ap = la_aprobare(tenant)
    r = client.post(
        f"/aprobari/{ap.id}/respinge",
        data={
            "csrf_token": csrf(client, "/aprobari"),
            "versiune": "1",
            "motiv_standard": "hook_slab",
            "motiv": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303 and stare(tenant, lid).stare == "respins"
    with admin_engine.connect() as c:
        motiv_cod, motiv, decis_de = c.execute(
            text("SELECT motiv_cod, motiv, decis_de FROM aprobari WHERE id = :i"), {"i": ap.id}
        ).one()
    assert (motiv_cod, motiv, decis_de) == ("hook_slab", "Hook slab", proprietar.id)
    html = client.get("/aprobari").text
    assert "Motivele respingerilor" in html and "Hook slab" in html


def test_aprobarea_din_birou(client: TestClient, proprietar: Cont, tenant: uuid.UUID) -> None:
    lid, ap = la_aprobare(tenant)
    r = client.post(
        f"/aprobari/{ap.id}/aproba", data={"csrf_token": csrf(client, "/aprobari"), "versiune": "1"},
        follow_redirects=False,
    )  # fmt: skip
    assert r.status_code == 303 and stare(tenant, lid).stare == "aprobat"


def test_editarea_pe_loc_creeaza_versiune_noua_care_trece_din_nou_validarea(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, admin_engine: Engine
) -> None:
    lid, ap = la_aprobare(tenant)
    jeton = csrf(client, "/aprobari")
    r = client.post(
        f"/aprobari/{ap.id}/editeaza", data={"csrf_token": jeton, "versiune": "1", "text": EDITAT},
        follow_redirects=False,
    )  # fmt: skip
    assert r.status_code == 303 and r.headers["location"] == "/aprobari?mesaj=editat"
    lv = stare(tenant, lid)
    assert (lv.stare, lv.versiune) == ("in_validare", 2), "versiunea nouă se validează din nou"
    with sesiune_tenant(tenant) as db:
        assert validare.continut.citeste(db, lid).text == EDITAT
        assert aprobari.citeste(db, ap.id).stare == "anulat"  # type: ignore[union-attr]
    # decizia pe cererea veche nu mai e posibilă
    r = client.post(f"/aprobari/{ap.id}/aproba", data={"csrf_token": jeton, "versiune": "1"})
    assert r.status_code == 409
    # jobul de validare (aici rulat direct): trece și se întoarce la aprobare, la același decident, pe versiunea 2
    with registru_doar("G1", "G10"):
        assert ruleaza(tenant, lid).stare is Stare.ASTEAPTA_APROBARE
    with sesiune_tenant(tenant) as db:
        noua = aprobari.cerere_activa(db, lid)
        assert noua is not None and noua.versiune == 2 and noua.decident == ap.decident
    html = client.get("/aprobari").text
    assert "Istoricul versiunilor (2)" in html and "<del>11:00</del>" in html and "<ins>12:00</ins>" in html
    r = client.post(
        f"/aprobari/{noua.id}/aproba", data={"csrf_token": jeton, "versiune": "2"}, follow_redirects=False
    )
    assert r.status_code == 303 and stare(tenant, lid).stare == "aprobat"
    with admin_engine.connect() as c:
        ed = c.execute(
            text(
                "SELECT detalii FROM jurnal_audit WHERE actiune = 'aprobare.editare' AND utilizator_id = :u"
            ),
            {"u": proprietar.id},
        ).scalar_one()
    assert ed["scos"] and ed["adaugat"] and ed["versiune_noua"] == 2


def test_o_editare_care_nu_trece_validarea_nu_ajunge_la_aprobare(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID
) -> None:
    lid, ap = la_aprobare(tenant)
    fara_diacritice = (
        "Sambata facem degustare la cafenea, vino sa gusti cafeaua proaspat prajita si sa afli cum o prepari."
    )
    client.post(
        f"/aprobari/{ap.id}/editeaza",
        data={"csrf_token": csrf(client, "/aprobari"), "versiune": "1", "text": fara_diacritice},
    )
    with registru_doar("G1", "G10"):
        assert ruleaza(tenant, lid).stare is Stare.IN_REPARATIE
    with sesiune_tenant(tenant) as db:
        assert aprobari.cerere_activa(db, lid) is None


def test_nicio_aprobare_pe_o_versiune_nevalidata(tenant: uuid.UUID, om: uuid.UUID) -> None:
    lid, _ = la_aprobare(tenant)
    with sesiune_tenant(tenant) as db:  # versiune nouă scrisă pe lângă birou: cererea se redeschide pe v2
        validare.continut.scrie(db, lid, text=EDITAT, autor="E4")
    with sesiune_tenant(tenant) as db:
        noua = aprobari.cerere_activa(db, lid)
        assert noua is not None and noua.versiune == 2
        with pytest.raises(aprobari.VersiuneNevalidata):
            aprobari.decide(
                db, noua.id, productie.Hotarare.APROBAT, utilizator_id=om, rol=Rol.PROPRIETAR, versiune=2
            )
    with sesiune_tenant(tenant) as db, pytest.raises(productie.TranzitieNepermisa):
        productie.muta(db, lid, Stare.ASTEAPTA_APROBARE, Stare.IN_VALIDARE, componenta="G1")  # fără om


def test_raspunsul_la_intrebarea_catre_client_din_birou(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID
) -> None:
    lid, _ = la_aprobare(tenant)
    with sesiune_tenant(tenant) as db:
        q = intrebari.deschide(
            db,
            tenant_id=tenant,
            livrabil_id=lid,
            versiune=1,
            validator="G2",
            intrebare="Care e prețul pachetului?",
        )
    html = client.get("/aprobari").text
    assert "Întrebare către client: Care e prețul pachetului?" in html
    r = client.post(
        f"/aprobari/intrebari/{q.id}/raspunde",
        data={"csrf_token": csrf(client, "/aprobari"), "raspuns": "49 de lei"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with sesiune_tenant(tenant) as db:
        [x] = intrebari.ale_livrabilului(db, lid)
    assert (x.stare, x.raspuns, x.raspuns_de) == ("raspunsa", "49 de lei", proprietar.id)


def test_o_cerere_noua_trimite_notificare(tenant: uuid.UUID, monkeypatch: pytest.MonkeyPatch) -> None:
    trimise: list[tuple[str, str]] = []
    monkeypatch.setattr(
        notificari, "notifica", lambda nivel, titlu, _t, **_k: trimise.append((nivel, titlu)) or {}
    )
    la_aprobare(tenant)
    assert any(n == notificari.Nivel.IMPORTANT for n, _ in trimise)
