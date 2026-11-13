"""F5.1 — verdictele se afișează în urma livrabilului din ecranul Producție (18.4): validatorul și versiunea
lui,
rezultatul, dovada (fragmentul exact și regula), instrucțiunea de corectare și versiunile de conținut."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app import validare
from app.conturi import Rol
from app.validare import registru
from app.validare.autor import ContinutNou, SarcinaReparatie
from app.validare.registru import DefinitieValidator
from app.validare.verdict import Dovada, Treapta, esec, trece
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.validare_utile import autor_scriptat, livrabil_in_validare, registru_gol, ruleaza  # noqa: F401

pytestmark = pytest.mark.db


@pytest.fixture
def proprietar(client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float]) -> Cont:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    return cont


def test_urma_livrabilului_arata_verdictele_dovezile_si_instructiunea(
    client: TestClient,
    proprietar: Cont,
    tenant: uuid.UUID,
    registru_gol: None,
    autor_scriptat: Callable[..., list[SarcinaReparatie]],
) -> None:
    # SIMULAT: validator de probă; autor scriptat
    def gp(i: validare.Intrare) -> validare.Verdict:
        if "INTERZIS" in i.text:
            return esec(
                "GP", "3", Treapta.V1, dovezi=[Dovada("INTERZIS", "cuvânt interzis de probă")],
                instructiune="Scoate cuvântul INTERZIS.",
            )  # fmt: skip
        return trece("GP", "3", Treapta.V1)

    registru.inregistreaza(DefinitieValidator("GP", "Probă", "3", Treapta.V1), gp)
    autor_scriptat(lambda s: ContinutNou("Text curat, fără probleme.", autor="E4", model_autor="p/m"))
    lid = livrabil_in_validare(tenant, "Ceva INTERZIS aici.")
    ruleaza(tenant, lid)
    from app.db import sesiune_tenant

    with sesiune_tenant(tenant) as db:
        validare.ruleaza_repararea(db, lid)
    ruleaza(tenant, lid)

    h = client.get(f"/productie/{lid}").text
    assert "Validare" in h and "Versiunea 1 · runda 0" in h and "Versiunea 2 · runda 1" in h
    assert "blocată, în reparație" in h and "a trecut" in h
    assert "<strong>GP</strong>" in h and "v3 · V1" in h
    assert "cuvânt interzis de probă: „INTERZIS”" in h and "Scoate cuvântul INTERZIS." in h
    assert "Mesajul unic trimis autorului" in h and "1. [GP] Scoate cuvântul INTERZIS." in h
    assert "Versiunile de conținut" in h and "autor E4" in h and "p/m" in h


def test_urma_arata_intrebarea_deschisa_catre_client(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, om: uuid.UUID
) -> None:
    from app.db import sesiune_tenant
    from tests.validare_utile import LA, registru_doar

    with registru_doar("G2"):
        lid = livrabil_in_validare(
            tenant,
            "Abonamentul Birou costă 310 lei.",
            campuri={"fapte_necesare": [{"tip": "pret", "subiect": "Abonament Birou"}]},
        )
        ruleaza(tenant, lid, la=LA)
    with sesiune_tenant(tenant, om) as db:
        [q] = validare.intrebari.ale_livrabilului(db, lid)
        validare.intrebari.raspunde(db, q.id, "310 lei", utilizator_id=om)
    h = client.get(f"/productie/{lid}").text
    assert "Întrebări către client" in h and "Abonament Birou" in h and "cu răspuns" in h and "310 lei" in h
    assert "întrebare către client" in h  # decizia rulării
