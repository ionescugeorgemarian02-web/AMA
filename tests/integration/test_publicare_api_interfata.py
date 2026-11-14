"""F9.1 — interfața comună de conector, legată de executorul de efecte: autorizarea OAuth (token criptat în
bază),
modul efectiv al canalului, publicarea o singură dată (și după un răspuns pierdut), eroarea de autentificare
(pauză, apoi reautorizare). Platforma este FALSĂ (# SIMULAT, în memorie)."""

# ruff: noqa: F811
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text

from app.connectors import registru
from app.connectors.publicare import DepozitBaza
from app.connectors.publicare.fals import ConectorFalsPublicare, PlatformaFalsa
from app.db import sesiune_agentie, sesiune_tenant
from app.operare import efecte, motor
from app.operare.efecte import autorizare, servicii
from app.productie.stari import Stare
from app.publicare import canale
from tests.integration.utile_productie import fabrica_clienti, livrabil_in_publicare, om, stare, tenant  # noqa: F401

pytestmark = pytest.mark.db
REDIRECT = "https://ama.exemplu.test/publicare/autorizare"


@pytest.fixture
def platforma(monkeypatch: pytest.MonkeyPatch) -> Iterator[PlatformaFalsa]:
    registru.uita_tot()
    p = PlatformaFalsa()
    registru.inregistreaza("fals_api", ConectorFalsPublicare(p, DepozitBaza()))
    monkeypatch.setitem(canale.CERINTE, "fals_api", ("meta", "pagini"))
    yield p
    registru.uita_tot()


def autorizeaza(tenant: uuid.UUID, om: uuid.UUID, p: PlatformaFalsa, *, agentie: bool = True) -> None:
    with sesiune_tenant(tenant) as db:
        canale.configureaza(db, tenant, "fals_api", nume="Cafeneaua Zorilor", cont_agentie=agentie)
        url = autorizare.url_autorizare(db, tenant, "fals_api", redirect=REDIRECT)
    stare_oauth = url.split("state=")[1].split("&")[0].replace("%2E", ".")
    with sesiune_tenant(tenant) as db:
        autorizare.finalizeaza(
            db, tenant, "fals_api", cod=p.cod_valid(), stare=stare_oauth, redirect=REDIRECT, utilizator_id=om
        )


def test_autorizarea_tine_tokenul_criptat_si_modul_urmeaza_aprobarea(
    tenant: uuid.UUID, om: uuid.UUID, platforma: PlatformaFalsa, admin_engine: Engine
) -> None:
    with sesiune_tenant(tenant) as db:
        assert canale.mod(db, tenant, "fals_api").mod is canale.Mod.ASISTAT, "neautorizat: asistat"
    autorizeaza(tenant, om, platforma)
    token = canale.token_pentru(tenant, "fals_api")
    assert token is not None and token.acces in platforma.tokenuri_valide
    with admin_engine.connect() as c:
        brut = c.execute(
            text("SELECT token_criptat FROM publicare_conturi WHERE tenant_id = :t"), {"t": tenant}
        )
        assert token.acces.encode() not in bytes(brut.scalar_one()), "tokenul nu stă în clar"
    with sesiune_tenant(tenant) as db:
        m = canale.mod(db, tenant, "fals_api")
        assert m.automat and m.restrans, "aprobare în test: automat doar pe contul agenției"
        canale.configureaza(db, tenant, "fals_api", cont_agentie=False)
        m = canale.mod(db, tenant, "fals_api")
        assert m.mod is canale.Mod.ASISTAT and "asistat" in m.motiv
    with sesiune_agentie() as db:
        a = canale.aprobare(db, "meta", "pagini")
        assert a is not None
        a.stare, a.inregistrare = "aprobata", "inregistrari/meta-pagini.json"
    with sesiune_tenant(tenant) as db:
        assert canale.mod(db, tenant, "fals_api").automat and not canale.mod(db, tenant, "fals_api").restrans
        canale.alege_mod(db, tenant, "fals_api", canale.Mod.ASISTAT, utilizator_id=om, motiv="test")
        assert canale.mod(db, tenant, "fals_api").motiv == "trecut pe asistat de un om"
    with sesiune_agentie() as db:
        a = canale.aprobare(db, "meta", "pagini")
        assert a is not None
        a.stare, a.inregistrare = "in_test", None


def test_starea_oauth_gresita_e_refuzata(tenant: uuid.UUID, om: uuid.UUID, platforma: PlatformaFalsa) -> None:
    with sesiune_tenant(tenant) as db:
        autorizare.url_autorizare(db, tenant, "fals_api", redirect=REDIRECT)
    with pytest.raises(autorizare.AutorizareRefuzata), sesiune_tenant(tenant) as db:
        autorizare.finalizeaza(
            db,
            tenant,
            "fals_api",
            cod=platforma.cod_valid(),
            stare="fals_api.altceva",
            redirect=REDIRECT,
            utilizator_id=om,
        )
    assert canale.token_pentru(tenant, "fals_api") is None


def test_executorul_publica_o_singura_data_si_dupa_raspuns_pierdut(
    tenant: uuid.UUID, om: uuid.UUID, platforma: PlatformaFalsa
) -> None:
    autorizeaza(tenant, om, platforma)
    lid = livrabil_in_publicare(tenant, om, canal="fals_api")
    with sesiune_tenant(tenant) as db:
        e = efecte.cere(db, lid, payload={"text": "Cafeneaua Zorilor deschide la 7."}, porneste=False).efect
    platforma.injecteaza("pierde_raspunsul")
    with pytest.raises(motor.EroareTemporara):
        efecte.incearca_efect(tenant, e.id)
    assert efecte.incearca_efect(tenant, e.id) == "trimis", "a doua încercare întreabă întâi `verifica`"
    assert len(platforma.postari) == 1 and stare(tenant, lid) is Stare.PUBLICAT
    assert autorizare.stare_postare(tenant, "fals_api", platforma.postari[0]["id"]).value == "publicata"
    assert autorizare.limite(tenant, "fals_api").ramase == 99


def test_token_respins_pune_pauza_iar_reautorizarea_o_ridica(
    tenant: uuid.UUID, om: uuid.UUID, platforma: PlatformaFalsa
) -> None:
    autorizeaza(tenant, om, platforma)
    lid = livrabil_in_publicare(tenant, om, canal="fals_api")
    with sesiune_tenant(tenant) as db:
        e = efecte.cere(db, lid, payload={"text": "Cafeneaua Zorilor"}, porneste=False).efect
    platforma.expira_tokenul()
    assert efecte.incearca_efect(tenant, e.id) == "autentificare"
    with sesiune_tenant(tenant) as db:
        assert servicii.pauza(db, tenant, "fals_api") is not None
    autorizeaza(tenant, om, platforma)
    with sesiune_tenant(tenant) as db:
        assert servicii.pauza(db, tenant, "fals_api") is None
    assert efecte.incearca_efect(tenant, e.id) == "trimis" and len(platforma.postari) == 1
