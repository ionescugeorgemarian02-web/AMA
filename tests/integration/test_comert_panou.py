import uuid

from app.comert import oauth
from app.conturi import Rol
from tests.integration.utile_panou import autentifica


def test_panou_comert_izolat(client, fabrica_conturi, ceas):
    assert client.get("/comert", follow_redirects=False).status_code in (303, 401)
    cont = fabrica_conturi(Rol.CLIENT_TITULAR, cu_totp=True)
    shop = f"m{uuid.uuid4().hex}.myshopify.com"
    oauth.incepe(cont.tenant_id, shop, "id", "https://ama.invalid/callback")
    alt = fabrica_conturi(Rol.CLIENT_TITULAR, cu_totp=True)
    strain = f"m{uuid.uuid4().hex}.myshopify.com"
    oauth.incepe(alt.tenant_id, strain, "id", "https://ama.invalid/callback")
    autentifica(client, cont, ceas)
    r = client.get("/comert")
    assert r.status_code == 200
    assert shop in r.text and strain not in r.text
    assert "Neconectat" in r.text
    assert "token_criptat" not in r.text


def test_panou_foloseste_coduri_persistente(client, fabrica_conturi, ceas):
    import datetime as dt

    from sqlalchemy import select

    from app.comert import vanzari
    from app.comert.modele import Magazin
    from app.db import sesiune_tenant

    cont = fabrica_conturi(Rol.CLIENT_TITULAR, cu_totp=True)
    shop = f"m{uuid.uuid4().hex}.myshopify.com"
    oauth.incepe(cont.tenant_id, shop, "id", "https://ama.invalid/callback")
    with sesiune_tenant(cont.tenant_id) as db:
        m = db.scalar(select(Magazin).where(Magazin.magazin == shop))
        m.coduri_reducere = {"REAL": ["Campanie cod real", "email"]}
    acum = dt.datetime.now(dt.UTC).isoformat()
    vanzari.importa(
        cont.tenant_id,
        shop,
        "comanda",
        [
            {
                "id": "1",
                "created_at": acum,
                "updated_at": acum,
                "currency": "RON",
                "total_price": "12.34",
                "cod_reducere": "REAL",
            }
        ],
    )
    autentifica(client, cont, ceas)
    r = client.get("/comert")
    assert r.status_code == 200
    assert "Campanie cod real" in r.text
    assert "email" in r.text
    assert "1234" in r.text
