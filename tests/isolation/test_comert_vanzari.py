import uuid

import pytest

from app.comert import oauth, vanzari

pytestmark = pytest.mark.db


def test_comenzi_clienti_consimtamant(date, chei_de_test):
    shop = f"m{uuid.uuid4().hex}.myshopify.com"
    oauth.incepe(date.a, shop, "id", "https://ama.invalid/callback")
    comanda = {
        "id": "1",
        "updated_at": "2026-11-17T12:00:00Z",
        "total_price": "12.34",
        "created_at": "2026-11-17T12:00:00Z",
        "currency": "RON",
    }
    for _ in range(2):
        vanzari.importa(date.a, shop, "comanda", [comanda])
    assert len(vanzari.citeste(date.a, shop, "comanda")) == 1
    assert vanzari.citeste(date.a, shop, "comanda")[0]["total_bani"] == 1234
    assert vanzari.citeste(date.b, shop, "comanda") == []
    persoana = {"id": "2", "updated_at": "2026-11-17T12:00:00Z", "email": "ana@example.test"}
    vanzari.importa(date.a, shop, "client", [persoana])
    assert vanzari.pentru_crm(date.a, shop) == []
    persoana.update(updated_at="2026-11-18T12:00:00Z", email_marketing_consent={"state": "subscribed"})
    vanzari.importa(date.a, shop, "client", [persoana])
    assert vanzari.pentru_crm(date.a, shop)[0]["email"] == "ana@example.test"
    assert "ana@example.test" not in str(vanzari.citeste(date.a, shop, "client"))
    persoana.update(updated_at="2026-11-19T12:00:00Z", email_marketing_consent={"state": "unsubscribed"})
    vanzari.importa(date.a, shop, "client", [persoana])
    assert vanzari.pentru_crm(date.a, shop) == []


def test_monede_lot_invalid_si_timestamptz(date, chei_de_test):
    import datetime as dt

    from sqlalchemy import select, text

    from app.comert.modele import DateComert
    from app.db import sesiune_tenant

    shop = f"m{uuid.uuid4().hex}.myshopify.com"
    oauth.incepe(date.a, shop, "id", "https://ama.invalid/callback")
    baza = {"updated_at": "2026-11-17T12:00:00Z", "created_at": "2026-11-01T01:00:00+02:00"}
    randuri = [
        {**baza, "id": "invalid", "currency": "XXX", "total_price": "1"},
        {**baza, "id": "jpy", "currency": "JPY", "total_price": "123", "rambursat_bani": "2"},
        {**baza, "id": "kwd", "currency": "KWD", "total_price": "1.234", "rambursat_bani": ".001"},
        {**baza, "id": "bhd", "currency": "BHD", "total_price": "2.345"},
        {**baza, "id": "tz", "currency": "RON", "total_price": "1", "created_at": "2026-11-01T00:00:00"},
        {**baza, "id": "frac", "currency": "JPY", "total_price": "1.1"},
    ]
    assert [r["id_extern"] for r in vanzari.importa(date.a, shop, "comanda", randuri)] == [
        "invalid",
        "tz",
        "frac",
    ]
    comenzi = {r["id_extern"]: r for r in vanzari.citeste(date.a, shop, "comanda")}
    assert (comenzi["jpy"]["total_bani"], comenzi["jpy"]["rambursat_bani"]) == (123, 2)
    assert (comenzi["kwd"]["total_bani"], comenzi["kwd"]["rambursat_bani"]) == (1234, 1)
    assert comenzi["bhd"]["total_bani"] == 2345
    with sesiune_tenant(date.a) as db:
        r = db.scalar(select(DateComert).where(DateComert.magazin == shop, DateComert.id_extern == "jpy"))
        assert r.creata_la == dt.datetime(2026, 10, 31, 23, tzinfo=dt.UTC)
        assert (
            db.scalar(
                text(
                    "SELECT data_type FROM information_schema.columns WHERE table_name='comert_date' AND column_name='creata_la'"
                )
            )
            == "timestamp with time zone"
        )


def test_atribuire_pe_material_dupa_rambursare(date, chei_de_test):
    import datetime as dt

    from app.comert import atribuire
    from app.db import sesiune_tenant

    shop = f"m{uuid.uuid4().hex}.myshopify.com"
    oauth.incepe(date.a, shop, "id", "https://ama.invalid/callback")
    comanda = {
        "id": "1",
        "updated_at": "2026-11-05T12:00:00Z",
        "created_at": "2026-11-01T08:00:00Z",
        "total_price": "49",
        "currency": "RON",
        "utm_content": "material-a",
        "rambursat_bani": "9",
    }
    vanzari.importa(date.a, shop, "comanda", [comanda])
    interval = (dt.datetime(2026, 11, 1, tzinfo=dt.UTC), dt.datetime(2026, 12, 1, tzinfo=dt.UTC))
    with sesiune_tenant(date.a) as db:
        r = atribuire.materiale(db, date.a, *interval)
        assert r["comenzi_importate"] == 1
        assert r["materiale"][0]["material"] == "material-a"
        assert r["materiale"][0]["net_bani"] == 4000
    with sesiune_tenant(date.b) as db:
        assert not atribuire.materiale(db, date.b, *interval)["materiale"]
