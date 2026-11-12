"""Fixture-uri pentru testele HTTP: aplicația reală, baza reală, utilizatori creați prin servicii."""

import re
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.conturi import criptare, totp
from app.conturi.roluri import Rol
from app.conturi.servicii import Actor, creeaza_client, creeaza_utilizator
from app.db import sesiune_agentie
from app.main import create_app
from tests.conftest import BazaTest

PAROLA = "o-parola-lunga-si-buna-1"  # >= 12 caractere
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


@dataclass
class Cont:
    id: uuid.UUID
    email: str
    parola: str
    rol: Rol
    tenant_id: uuid.UUID | None
    secret: str | None = None  # TOTP activ, dacă există
    coduri: list[str] = field(default_factory=list)


@pytest.fixture(autouse=True)
def _curata_incercari(admin_engine: Engine, chei_de_test: None) -> Iterator[None]:
    """Contoarele de limitare sunt per IP: fiecare test pornește de la zero."""
    with admin_engine.begin() as c:
        c.execute(text("TRUNCATE incercari_autentificare"))
    yield


@pytest.fixture
def client(baza: BazaTest) -> Iterator[TestClient]:
    with TestClient(create_app(), client=("203.0.113.7", 50000)) as c:
        yield c


@pytest.fixture
def fabrica_conturi(baza: BazaTest, admin_engine: Engine) -> Callable[..., Cont]:
    def creeaza(
        rol: Rol = Rol.CLIENT_TITULAR, *, cu_totp: bool = False, tenant_id: uuid.UUID | None = None
    ) -> Cont:
        email = f"u{uuid.uuid4().hex[:10]}@exemplu.test"
        with sesiune_agentie() as db:
            if rol.value.startswith("client") and tenant_id is None:
                tenant_id = creeaza_client(db, f"Firma {uuid.uuid4().hex[:6]}", actor=Actor.cli()).id
            u = creeaza_utilizator(
                db,
                email=email,
                parola=PAROLA,
                nume_afisat="Ana Test",
                rol=rol,
                tenant_id=tenant_id,
                actor=Actor.cli(),
            )
            uid = u.id
        cont = Cont(uid, email, PAROLA, rol, tenant_id)
        if cu_totp:
            cont.secret = pyotp.random_base32()
            with admin_engine.begin() as c:  # pregătire directă (superutilizator): 2FA deja activat
                c.execute(
                    text("UPDATE utilizatori SET totp_secret_enc = :s, totp_activ = true WHERE id = :i"),
                    {"s": criptare.cripteaza(cont.secret.encode(), aad=uid.bytes), "i": uid},
                )
        return cont

    return creeaza


def csrf_din(html: str) -> str:
    m = CSRF_RE.search(html)
    assert m, "pagina nu conține jeton CSRF"
    return m.group(1)


def cod_totp(secret: str, ceas: float) -> str:
    return totp.cod_pentru(secret, ceas)


T0 = 1_800_000_000.0


@pytest.fixture
def ceas(monkeypatch: pytest.MonkeyPatch) -> dict[str, float]:
    """Ceasul folosit de verificarea TOTP, controlat de test (pași de timp diferiți)."""
    stare = {"t": T0}
    monkeypatch.setattr("app.conturi.autentificare._ceas", lambda: stare["t"])
    return stare


def post_cod(client: TestClient, cale: str, cod: str):  # type: ignore[no-untyped-def]
    pagina = client.get(cale)
    return client.post(cale, data={"cod": cod, "csrf_token": csrf_din(pagina.text)}, follow_redirects=False)


def login(client: TestClient, email: str, parola: str, *, urmeaza: bool = False):  # type: ignore[no-untyped-def]
    pagina = client.get("/conturi/login")
    return client.post(
        "/conturi/login",
        data={"email": email, "parola": parola, "csrf_token": csrf_din(pagina.text)},
        follow_redirects=urmeaza,
    )


# Fixture-urile panoului, livrării și Telegram (F1.7–F1.10), puse la dispoziția tuturor testelor de integrare.
from tests.integration.utile_panou import _curata_panou, bot_fals, config, push  # noqa: E402, F401

# Clienți și utilizatori pentru testele producției (F2.3+).
from tests.integration.utile_productie import anunturi, fabrica_clienti, om, tenant  # noqa: E402, F401
