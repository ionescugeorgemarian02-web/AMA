"""F13.7 — Consiliul. „Gata când”: o decizie luată în Claude apare în platformă și schimbă starea unei campanii.
Modul manual asistat: răspunsul (scris aici în locul lui Claude, # SIMULAT) se lipește în panou."""

# ruff: noqa: F811
import json
import re
import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.connectors.publicare.baza import DepozitInMemorie
from app.conturi import Rol
from app.db import sesiune_agentie
from app.reclame import DosarConsiliu, consiliu, rezultate
from tests.furnizor_fals import CerereInregistrata
from tests.integration.conftest import Cont
from tests.integration.test_reclame_urgenta import activeaza, stare
from tests.integration.utile_panou import autentifica, config, csrf  # noqa: F401
from tests.integration.utile_productie import fabrica_clienti, om  # noqa: F401
from tests.integration.utile_reclame import (  # noqa: F401
    ACUM,
    AZI,
    autorizeaza,
    construieste,
    cont_agentie,
    depozit,
    executa_efecte,
    meta,
)
from tests.onboarding_utile import ModelFals, model_fals, modele, prompt_complet, raspuns_json  # noqa: F401
from tests.platforme.meta_ads import MarketingSimulat

pytestmark = pytest.mark.db
Fabrica = Callable[..., tuple[uuid.UUID, uuid.UUID]]


def test_decizia_luata_in_claude_apare_in_platforma_si_opreste_campania(
    meta: MarketingSimulat,
    depozit: DepozitInMemorie,
    cont_agentie: Fabrica,
    om: uuid.UUID,
    client: TestClient,
    fabrica_conturi: Callable[..., Cont],
    ceas: dict[str, float],
) -> None:
    tenant, cont_id = cont_agentie()
    autorizeaza(depozit, meta, tenant)
    scalare, _ = construieste(cont_id, om)
    activeaza(scalare, om)
    meta.zi(AZI)
    rezultate.citeste_cont(cont_id, ACUM)

    autentifica(client, fabrica_conturi(Rol.PROPRIETAR, cu_totp=True), ceas)
    r = client.post(
        "/reclame/consiliu/deschide",
        data={"csrf_token": csrf(client), "cont_id": str(cont_id)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    h = client.get(r.headers["location"]).text
    assert "Dosar de Consiliu" in h and "Audit gratuit · scalare (activa" in h and "Formatul răspunsului" in h
    [optiune] = re.findall(r"`(opreste-\d+)`: Oprim campania „Audit gratuit · scalare”", h)

    # ce a răspuns Claude (lipit cu text în jur, cum vine din aplicație)
    raspuns = (
        "Am citit dosarul.\n```json\n"
        + json.dumps(
            {
                "alegere": optiune,
                "motive": ["Costul pe rezultat e peste prag de două săptămâni"],
                "conditii": ["Repornim dacă ipoteza nouă trece pragul"],
                "masuram": ["Cost pe rezultat sub 40 de lei"],
            },
            ensure_ascii=False,
        )
        + "\n```\nSucces!"
    )
    url = r.headers["location"]
    r = client.post(
        url + "/importa", data={"csrf_token": csrf(client), "raspuns": raspuns}, follow_redirects=False
    )
    assert "mesaj=decizie_consiliu" in r.headers["location"], r.headers["location"]
    executa_efecte()
    ext = next(c["id"] for c in meta.campanii() if c["name"] == "Audit gratuit · scalare")
    assert meta.obiecte[ext]["status"] == "PAUSED" and stare(scalare) == "in_pauza"
    h = client.get(f"/reclame/cont/{cont_id}").text
    assert 'data-iesire="opreste"' in h and "(consiliu)" in h and "Consiliul: Costul pe rezultat" in h

    # un răspuns fără formă sau cu o opțiune inventată nu schimbă nimic
    r = client.post(
        "/reclame/consiliu/deschide",
        data={"csrf_token": csrf(client), "cont_id": str(cont_id)},
        follow_redirects=False,
    )
    url = r.headers["location"]
    for gresit in ("Nu știu.", json.dumps({"alegere": "vinde-tot", "motive": ["x"], "masuram": ["y"]})):
        r = client.post(
            url + "/importa", data={"csrf_token": csrf(client), "raspuns": gresit}, follow_redirects=False
        )
        assert "eroare=" in r.headers["location"]


@pytest.fixture
def plafon_unu(config: Callable[..., None]) -> Iterator[None]:
    from app.config import get_settings

    config(reclame_consiliu_plafon_lunar="1")
    yield
    get_settings.cache_clear()  # setarea nu rămâne testelor următoare


def test_plafonul_lunar_amana_dosarul(cont_agentie: Fabrica, plafon_unu: None) -> None:
    _, cont_id = cont_agentie()
    with sesiune_agentie() as db:
        assert (
            consiliu.deschide(
                db, cont_id, subiect="Prima revizuire", motiv_apel="Revizuirea lunară a lunii"
            ).stare
            == "deschis"
        )
        d = consiliu.deschide(
            db, cont_id, subiect="A doua revizuire", motiv_apel="Încă o întrebare în aceeași lună"
        )
        assert d.stare == "amanat"
        with pytest.raises(consiliu.DosarRefuzat):
            consiliu.importa(
                db,
                d.id,
                '{"alegere": "continua", "motive": ["x"], "masuram": ["y"]}',
                utilizator_id=uuid.uuid4(),
            )


def test_modul_api_scrie_decizia_iar_propunerile_asteapta_omul(
    meta: MarketingSimulat,
    depozit: DepozitInMemorie,
    cont_agentie: Fabrica,
    om: uuid.UUID,
    modele: ModelFals,
) -> None:
    def decide(c: CerereInregistrata) -> str:
        alegere = re.search(r"`(opreste-\d+)`", prompt_complet(c))
        assert alegere
        return raspuns_json(
            decizie={
                "alegere": alegere.group(1),
                "motive": ["Prea scump"],
                "conditii": [],
                "masuram": ["Cost pe rezultat"],
            }
        )

    modele.handlere["Decide pe dosarul de Consiliu"] = decide
    tenant, cont_id = cont_agentie()
    autorizeaza(depozit, meta, tenant)
    scalare, _ = construieste(cont_id, om)
    activeaza(scalare, om)
    with sesiune_agentie() as db:
        d = consiliu.deschide(db, cont_id, subiect="Revizuire prin API", motiv_apel="Probă pentru modul API")
        rec = consiliu.intreaba_api(db, d.id)
        assert rec.iesire == "opreste" and rec.model == "consiliu:manual"
        assert db.get(DosarConsiliu, d.id).stare == "decis"  # type: ignore[union-attr]
    executa_efecte()
    assert stare(scalare) == "activa", "în modul API, oprirea așteaptă omul"
