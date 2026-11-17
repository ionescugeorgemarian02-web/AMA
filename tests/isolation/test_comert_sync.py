import uuid

import pytest
from sqlalchemy import select

from app.comert import oauth
from app.comert.modele import Magazin, Sincronizare
from app.comert.sincronizare import executa
from app.conturi import criptare
from app.db import sesiune_tenant

pytestmark = pytest.mark.db


def test_sync_succes_si_eroare(date, chei_de_test):
    shop = f"m{uuid.uuid4().hex}.myshopify.com"
    oauth.incepe(date.a, shop, "id", "https://ama.invalid/callback")
    with sesiune_tenant(date.a) as db:
        m = db.scalar(select(Magazin).where(Magazin.magazin == shop))
        m.token_criptat = criptare.cripteaza(uuid.uuid4().hex.encode(), aad=oauth.aad(date.a, shop))
    executa(date.a, shop, lambda _: [], lambda *_: [])
    with sesiune_tenant(date.a) as db:
        s = db.get(Sincronizare, (date.a, shop))
        assert s.stare == "succes"
        ultima = s.ultima_reusita
        assert ultima is not None

    def eroare(_):
        raise RuntimeError("nu ecou în stare sau eroare")

    with pytest.raises(ValueError, match="datele pot fi parțiale"):
        executa(date.a, shop, eroare, lambda *_: [])
    with sesiune_tenant(date.a) as db:
        s = db.get(Sincronizare, (date.a, shop))
        assert s.stare == "eroare" and s.ultima_reusita == ultima
