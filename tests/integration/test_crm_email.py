"""F12.2 — email către abonați. „Gata când”: o adresă dezabonată nu mai poate primi nimic, din nicio campanie.
Furnizorul de email e cutia poștală SIMULATĂ; verificarea domeniului (DNS) e înlocuită în teste."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable, Iterator
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.connectors.email import CutiePostalaSimulata
from app.conturi import Rol
from app.crm import email, registru
from app.db import sesiune_agentie
from app.operare.efecte import sistem
from tests.integration.conftest import Cont
from tests.integration.utile_crm import TABELE_CRM
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import om  # noqa: F401
from tests.integration.utile_site import asteapta, cutie, link_din  # noqa: F401

pytestmark = pytest.mark.db
TABELE = TABELE_CRM
ADRESA = "ana@zorilor.example"


@pytest.fixture(autouse=True)
def _curat(admin_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def sterge() -> None:
        with admin_engine.begin() as c:
            for t in TABELE:
                c.execute(text(f"DELETE FROM {t}"))
            c.execute(text("DELETE FROM crm_matrice_tari WHERE tara <> 'RO'"))

    sterge()
    monkeypatch.setattr(email, "REZOLVA", lambda d: not d.startswith("inexistent"))
    yield
    sterge()  # lista de suprimare e globală: nu trebuie să rămână pentru alte teste


def contact(
    adresa: str = ADRESA, sursa: str = "formular_audit", firma: str = "Cafeneaua Zorilor"
) -> uuid.UUID:
    with sesiune_agentie() as db:
        return registru.primeste(db, email=adresa, firma=firma, sursa=sursa)[0].contact_id


def trimite(cid: uuid.UUID, campanie: str, **kw: object) -> email.Rezultat:
    with sesiune_agentie() as db:
        return email.trimite(
            db, cid, campanie=campanie, scop="email_audit", subiect=f"Noutăți: {campanie}",
            text="Am pregătit trei idei pentru firma ta.", **kw,  # type: ignore[arg-type]
        )  # fmt: skip


def test_o_adresa_dezabonata_nu_mai_primeste_nimic_din_nicio_campanie(
    client: TestClient, cutie: CutiePostalaSimulata, executor: None
) -> None:
    cid = contact()
    assert trimite(cid, "secventa-1").trimis and trimite(cid, "secventa-1").trimis
    [m] = asteapta(lambda: cutie.catre(ADRESA))
    assert len(cutie.catre(ADRESA)) == 1, "aceeași campanie nu trimite de două ori"
    link = link_din(m.text, "/dezabonare/")
    assert m.antete == {
        "List-Unsubscribe": f"<{link}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }

    # un mesaj cerut înainte de dezabonare, încă netrimis
    with sesiune_agentie() as db:
        in_asteptare = sistem.cere(
            db, "email", cheie="crm:test-in-asteptare", porneste=False,
            payload={"catre": ADRESA, "subiect": "Întârziat", "text": "x", "categorie": "marketing"},
        ).id  # fmt: skip

    cale = urlsplit(link).path
    h = client.get(cale)
    assert h.status_code == 200 and "Dezabonează-mă" in h.text
    with sesiune_agentie() as db:
        assert not email.suprimat(db, ADRESA), "deschiderea linkului (și previzualizările) nu dezabonează"
    r = client.post(cale)  # un clic, fără alt formular și fără autentificare
    assert r.status_code == 200 and "Te-am dezabonat" in r.text
    assert client.post(cale).status_code == 200, "a doua oară nu strică nimic"
    assert client.get("/site/dezabonare/jeton-fals").status_code == 404
    assert client.post("/site/dezabonare/jeton-fals").status_code == 404

    with sesiune_agentie() as db:
        assert email.suprimat(db, ADRESA) and registru.scopuri_acordate(db, cid) == []
    for campanie in ("secventa-2", "oferta-de-iarna", "alta-campanie"):
        r2 = trimite(cid, campanie)
        assert (r2.trimis, r2.motiv) == (False, "suprimat") and "suprimare" in r2.explicatie
    contact()  # chiar dacă cere din nou auditul și își dă din nou acordul, adresa rămâne suprimată
    with sesiune_agentie() as db:
        assert registru.are_consimtamant(db, cid, "email_audit")
    assert trimite(cid, "dupa-un-nou-acord").motiv == "suprimat"
    alt = contact("ANA@zorilor.example".lower(), firma="Altă Firmă")  # același om, regăsit: tot suprimat
    assert alt == cid
    assert sistem.incearca(in_asteptare) == "anulat", "mesajul cerut înainte de dezabonare nu mai pleacă"
    assert len(cutie.catre(ADRESA)) == 1, "după dezabonare nu a mai plecat nimic"

    # emailurile tranzacționale nu sunt comerciale: dezabonarea nu le oprește
    with sesiune_agentie() as db:
        factura = sistem.cere(
            db, "email", cheie="test:factura", porneste=False,
            payload={"catre": ADRESA, "subiect": "Factura ta", "text": "Atașat."},
        ).id  # fmt: skip
    assert sistem.incearca(factura) == "trimis"


def test_fara_consimtamant_tara_blocata_si_domeniu_inexistent(
    cutie: CutiePostalaSimulata, executor: None, admin_engine: Engine, om: uuid.UUID
) -> None:
    recomandat = contact("dan@recomandat.example", sursa="recomandare", firma="Firma lui Dan")
    assert trimite(recomandat, "c1").motiv == "fara_consimtamant", "o recomandare nu e acord pentru emailuri"
    assert (
        trimite(contact("eva@inexistent-domeniu.example", firma="Firma Evei"), "c1").motiv
        == "domeniu_inexistent"
    )
    assert trimite(uuid.uuid4(), "c1").motiv == "contact_inexistent"

    german = contact("hans@bäckerei.example".encode("ascii", "ignore").decode(), firma="Bäckerei Hans")
    with admin_engine.begin() as c:
        c.execute(text("UPDATE crm_contacte SET tara = 'DE' WHERE id = :i"), {"i": german})
    assert trimite(german, "c1").motiv == "tara_blocata", "o țară fără rând în matrice e blocată"
    with sesiune_agentie() as db:
        for gresit in ({"tara": "Germania"}, {"regula": "permis"}, {"verificat_de": ""}):
            date = {
                "tara": "de",
                "tip_destinatar": "firma",
                "regula": "blocat",
                "mentiuni": "",
                "verificat_de": "av. Pop",
            }
            with pytest.raises(registru.CrmRefuzat):
                email.seteaza_regula(db, **{**date, **gresit}, utilizator_id=om)
        email.seteaza_regula(
            db, tara="de", tip_destinatar="firma", regula="blocat", mentiuni="", verificat_de="av. Pop, 2026-11-15",
            utilizator_id=om,
        )  # fmt: skip
    assert trimite(german, "c1").motiv == "tara_blocata"
    with sesiune_agentie() as db:
        email.seteaza_regula(
            db, tara="DE", tip_destinatar="firma", regula="doar_cu_consimtamant",
            mentiuni="Impressum: Agenția Exemplu SRL, București.", verificat_de="av. Pop, 2026-11-15", utilizator_id=om,
        )  # fmt: skip
        assert len(email.matrice(db)) == 3
    assert trimite(german, "c1").trimis
    [m] = asteapta(lambda: cutie.catre("hans@bckerei.example"))
    assert "Impressum: Agenția Exemplu SRL" in m.text and "Dezabonează-te dintr-un clic" in m.text
    with admin_engine.connect() as c:
        refuzuri = c.execute(
            text("SELECT detalii->>'motiv' FROM jurnal_audit WHERE actiune = 'crm.email_refuzat' AND obiect_id = :i"),
            {"i": str(german)},
        ).scalars().all()  # fmt: skip
    assert refuzuri == ["tara_blocata", "tara_blocata"], "fiecare refuz lasă urmă"


def test_limita_zilnica_si_pragurile_de_oprire(admin_engine: Engine) -> None:
    cid = contact()
    acum = dt.datetime.now(dt.UTC)

    def umple(n: int, la: dt.datetime) -> None:
        with admin_engine.begin() as c:
            for _ in range(n):
                c.execute(
                    text("INSERT INTO crm_trimiteri (id, contact_id, email, campanie, cheie, la) VALUES (:i, :c, :e, 'veche', :k, :l)"),
                    {"i": uuid.uuid4(), "c": cid, "e": ADRESA, "k": uuid.uuid4().hex, "l": la},
                )  # fmt: skip

    umple(50, acum)
    with sesiune_agentie() as db:
        s = email.stare(db)
        assert (s["azi"], s["limita"], s["oprit"]) == (50, 50, False)
    assert trimite(cid, "peste-limita").motiv == "limita_zilnica"
    umple(1, acum - dt.timedelta(days=8))  # prima trimitere a fost acum 8 zile: a doua săptămână, limita 100
    with sesiune_agentie() as db:
        assert email.stare(db)["limita"] == 100
        for i in range(2):
            assert email.suprima(db, f"respins{i}@undeva.example", "respins", sursa="furnizor")
        assert not email.suprima(db, "respins0@undeva.example", "plangere"), "o adresă intră o singură dată"
        s = email.stare(db)
        assert (s["trimise"], s["respinse"], s["plangeri"], s["oprit"]) == (51, 2, 0, True), (
            "2 din 51: peste 2%"
        )
    r = trimite(cid, "dupa-respingeri")
    assert r.motiv == "oprit_praguri" and "oprită" in r.explicatie


def test_urma_si_lista_de_suprimare_nu_se_pot_sterge_iar_ecranul_e_al_proprietarului(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float]
) -> None:
    with sesiune_agentie() as db:
        email.suprima(db, "gata@undeva.example", "manual")
        with pytest.raises(registru.CrmRefuzat):
            email.suprima(db, "nu-e-email", "manual")
        with pytest.raises(registru.CrmRefuzat):
            email.suprima(db, "ok@undeva.example", "altceva")
    for comanda in (
        "DELETE FROM crm_suprimari",
        "UPDATE crm_suprimari SET motiv = 'manual'",
        "DELETE FROM crm_trimiteri",
    ):
        with pytest.raises(DBAPIError, match="permission denied"), sesiune_agentie() as db:
            db.execute(text(comanda))

    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    assert "/crm/email" in client.get("/crm").text
    h = client.get("/crm/email").text
    assert "Matricea pe țări" in h and "doar cu consimțământ" in h and "neverificată de avocat" in h
    jeton = csrf(client, "/crm/email")
    assert client.post("/crm/email/suprimare", data={"csrf_token": jeton, "email": "x"}).status_code == 422
    assert client.post("/crm/email/suprimare", data={"email": "a@b.example"}).status_code == 403
    r = client.post("/crm/email/suprimare", data={"csrf_token": jeton, "email": "Cere@Altfel.example"}, follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    with sesiune_agentie() as db:
        assert email.suprimat(db, "cere@altfel.example") and email.stare(db)["suprimate"] == 2
    regula = {"csrf_token": jeton, "tara": "MD", "tip_destinatar": "firma", "regula": "doar_cu_consimtamant", "verificat_de": "av. Rusu, aviz din 2026-11-10"}  # fmt: skip
    assert client.post("/crm/email/regula", data={**regula, "verificat_de": ""}).status_code == 422
    assert client.post("/crm/email/regula", data=regula, follow_redirects=False).status_code == 303
    assert "av. Rusu, aviz din 2026-11-10" in client.get("/crm/email").text


def test_operatorul_nu_are_ecranul_de_email(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float]
) -> None:
    autentifica(client, fabrica_conturi(Rol.OPERATOR, cu_totp=True), ceas)
    assert client.get("/crm/email").status_code == 403
