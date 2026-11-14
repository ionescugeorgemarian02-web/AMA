"""F9.8 — gardianul sănătății conturilor. „Gata când”: un token aproape expirat generează o cerere de
reautorizare, iar o serie de erori pune canalul pe pauză. Ceas controlat; platforma FALSĂ (# SIMULAT);
alertele, prinse în test."""

# ruff: noqa: F811
import datetime as dt
import uuid
from collections.abc import Iterator

import pytest

from app.connectors import registru
from app.connectors.contract import Token
from app.connectors.publicare import DepozitBaza
from app.connectors.publicare.fals import ConectorFalsPublicare, PlatformaFalsa
from app.db import sesiune_tenant
from app.operare import efecte, motor
from app.operare.efecte import servicii
from app.publicare import canale, sanatate
from tests.integration.publicare_utile import autorizeaza, cere
from tests.integration.utile_productie import (  # noqa: F401
    AnunturiFalse,
    anunturi,
    fabrica_clienti,
    livrabil_in_publicare,
    om,
    tenant,
)

pytestmark = pytest.mark.db


@pytest.fixture
def platforma() -> Iterator[PlatformaFalsa]:
    registru.uita_tot()
    p = PlatformaFalsa()
    registru.inregistreaza("facebook", ConectorFalsPublicare(p, DepozitBaza(), canal="facebook"))
    yield p
    registru.uita_tot()


def test_tokenul_aproape_expirat_cere_reautorizare_o_singura_data(
    tenant: uuid.UUID, om: uuid.UUID, platforma: PlatformaFalsa, anunturi: AnunturiFalse
) -> None:
    autorizeaza(tenant, om, "facebook", platforma.cod_valid())
    acum = dt.datetime.now(dt.UTC)
    # cu token de reîmprospătare: se reîmprospătează singur, fără om
    assert sanatate.verifica_contul(tenant, "facebook", acum + dt.timedelta(days=55)) == ["reimprospatat"]
    # fără: cerere de reautorizare, alertă, canalul trece pe asistat până la reautorizare
    t = platforma.emite_token()
    with sesiune_tenant(tenant) as db:
        canale.salveaza_token(
            db, tenant, "facebook", Token(t.acces, acum + dt.timedelta(days=3), "", "pagina")
        )
    assert sanatate.verifica_contul(tenant, "facebook", acum) == ["reautorizare"]
    assert [a[1] for a in anunturi.trimise] == ["Reautorizare necesară"]
    with sesiune_tenant(tenant) as db:
        m = canale.mod(db, tenant, "facebook")
        assert m.mod is canale.Mod.ASISTAT and m.motiv == "contul cere reautorizare"
    assert sanatate.verifica_contul(tenant, "facebook", acum) == [], "o singură cerere, nu una pe oră"
    autorizeaza(tenant, om, "facebook", platforma.cod_valid())
    with sesiune_tenant(tenant) as db:
        assert canale.mod(db, tenant, "facebook").automat, "reautorizarea șterge cererea"


def test_o_serie_de_erori_pune_canalul_pe_pauza(
    tenant: uuid.UUID, om: uuid.UUID, platforma: PlatformaFalsa, anunturi: AnunturiFalse
) -> None:
    autorizeaza(tenant, om, "facebook", platforma.cod_valid())
    platforma.injecteaza("temporar", "temporar")
    for i in range(sanatate.SERIE):
        lid = livrabil_in_publicare(tenant, om, canal="facebook")
        eid = cere(tenant, lid, {"text": f"Cafeneaua Zorilor {i}"})
        if i < 2:
            with pytest.raises(motor.EroareTemporara):
                efecte.incearca_efect(tenant, eid)
        else:
            platforma.injecteaza("definitiv")
            assert efecte.incearca_efect(tenant, eid) == "esuat"
    r = sanatate.ruleaza()
    assert r[f"{tenant}:facebook"] == ["pauza"]
    with sesiune_tenant(tenant) as db:
        assert servicii.pauza(db, tenant, "facebook") is not None
        c = canale.cont(db, tenant, "facebook")
        assert c is not None and c.setari["limite"]["sursa"] == "platforma falsă: contorul zilnic"
    assert "Canal pus pe pauză" in [a[1] for a in anunturi.trimise]
    lid = livrabil_in_publicare(tenant, om, canal="facebook")
    assert efecte.incearca_efect(tenant, cere(tenant, lid, {"text": "după pauză"})) == "pauza"
    assert platforma.postari == [], "pe pauză nu pleacă nimic"


def test_seria_nucleu_pur() -> None:
    assert sanatate.serie_de_erori(
        [("esuat_definitiv", "X"), ("esuat_temporar", "Y"), ("esuat_temporar", "Z")]
    )
    assert not sanatate.serie_de_erori([("esuat_definitiv", "X"), ("trimis", None), ("esuat_temporar", "Z")])
    assert not sanatate.serie_de_erori([("esuat_definitiv", "X")])
