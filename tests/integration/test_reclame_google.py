"""F13.2 — citirea rezultatelor Google Ads. „Gata când”: cifrele contului agenției apar în panou și coincid cu
consola Google Ads. Google Ads API e SIMULAT (contract HTTP local, # SIMULAT)."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.connectors.contract import Token
from app.connectors.publicare.baza import DepozitInMemorie
from app.connectors.reclame.google import CANAL_TOKEN
from app.conturi import Rol
from app.db import sesiune_agentie
from app.panou.reclame_web import lei
from app.reclame import rezultate
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica
from tests.integration.utile_productie import fabrica_clienti  # noqa: F401
from tests.integration.utile_reclame import ACUM, AZI, cont_agentie, depozit, google  # noqa: F401
from tests.platforme.google_ads import GoogleAdsSimulat

pytestmark = pytest.mark.db


def test_cifrele_google_apar_in_panou_si_coincid_cu_consola(
    google: GoogleAdsSimulat,
    depozit: DepozitInMemorie,
    cont_agentie: Callable[..., tuple[uuid.UUID, uuid.UUID]],
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
) -> None:
    tenant, cont_id = cont_agentie("google", "123-456-7890")
    depozit.pune(tenant, CANAL_TOKEN, Token(acces=google.token_nou("ya29")))
    a = google.adauga_campanie("Căutare: audit marketing", 4_000)
    google.adauga_campanie("Performance Max: audit", 3_000)
    for i in range(8):
        google.zi(AZI - dt.timedelta(days=i), ritm=0.7 + i / 20)
    assert rezultate.citeste_cont(cont_id, ACUM).startswith("citit:")
    m = google.manager(AZI - dt.timedelta(days=29), AZI)
    with sesiune_agentie() as db:
        t = rezultate.totaluri(db, cont_id, AZI - dt.timedelta(days=29), AZI)
        assert len(rezultate.pe_obiecte(db, cont_id, AZI - dt.timedelta(days=29), AZI, nivel="reclama")) == 2
        assert rezultate.totaluri(db, cont_id, AZI, AZI, obiect_extern=a).cheltuiala_bani == int(4_000 * 0.7)
    assert (t.cheltuiala_bani, t.afisari, t.clicuri, t.rezultate) == (
        m["bani"],
        m["afisari"],
        m["clicuri"],
        m["rezultate"],
    )

    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    h = client.get(f"/reclame/cont/{cont_id}").text
    assert "Google Ads" in h and f'<td data-camp="cheltuiala">{lei(m["bani"])} RON</td>' in h


def test_tokenul_respins_de_google_e_eroare_de_autentificare(
    google: GoogleAdsSimulat,
    depozit: DepozitInMemorie,
    cont_agentie: Callable[..., tuple[uuid.UUID, uuid.UUID]],
) -> None:
    tenant, cont_id = cont_agentie("google", "1234567890")
    depozit.pune(tenant, CANAL_TOKEN, Token(acces="token-revocat"))
    assert rezultate.citeste_cont(cont_id, ACUM) == "autentificare"
