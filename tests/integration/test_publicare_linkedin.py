"""F9.5 — LinkedIn. „Gata când”: o postare apare pe profilul tău. Profilul e automat de la început (aplicație
self-serve); pagina de companie rămâne pe asistat până la aprobarea Community Management API, apoi publică pe
pagină. Posts API e SIMULAT (contract HTTP local, # SIMULAT): profilul real, la migrare."""

# ruff: noqa: F811
import uuid
from collections.abc import Iterator

import pytest

from app.connectors import registru
from app.connectors.publicare.linkedin import ConectorLinkedin
from app.db import sesiune_tenant
from app.operare import efecte
from app.publicare import canale
from tests.integration.publicare_utile import autorizeaza, cere, efect, livrabil_stare, pune_aprobarea
from tests.integration.utile_productie import fabrica_clienti, livrabil_in_publicare, om, tenant  # noqa: F401
from tests.platforme.linkedin import CLIENT_ID, CLIENT_SECRET, LinkedinSimulat

pytestmark = pytest.mark.db


@pytest.fixture
def li() -> Iterator[LinkedinSimulat]:
    registru.uita_tot()
    s = LinkedinSimulat()
    for pagina in (False, True):
        c = ConectorLinkedin(
            client_id=CLIENT_ID, client_secret=CLIENT_SECRET, pagina=pagina, transport=s.transport
        )
        registru.inregistreaza(c.canal, c)
    yield s
    registru.uita_tot()


def test_postarea_apare_pe_profil_iar_pagina_asteapta_aprobarea(
    tenant: uuid.UUID, om: uuid.UUID, li: LinkedinSimulat
) -> None:
    # profilul TĂU (contul clientului-agenție, dar profilul nu cere aprobare): automat de la început
    autorizeaza(tenant, om, "linkedin", li.cod_valid(), agentie=False)
    with sesiune_tenant(tenant) as db:
        m = canale.mod(db, tenant, "linkedin")
        assert m.automat and not m.restrans and m.motiv == "aprobat de platformă"
    lid = livrabil_in_publicare(tenant, om, canal="linkedin")
    eid = cere(tenant, lid, {"text": "Cafeneaua Zorilor: cum am ales boabele de cafea.", "taguri": ["cafea"]})
    assert efecte.incearca_efect(tenant, eid) == "trimis"
    assert [(p["author"], p["commentary"]) for p in li.postari] == [
        (li.persoana, "Cafeneaua Zorilor: cum am ales boabele de cafea.\n\n#cafea")
    ], "o postare, pe profil"
    e = efect(tenant, eid)
    assert e.link == f"https://www.linkedin.com/feed/update/{li.postari[0]['id']}/"
    assert livrabil_stare(tenant, lid) == "publicat"
    # pagina de companie a unui client: asistat până la aprobarea Community Management API
    autorizeaza(tenant, om, "linkedin_pagina", li.cod_valid(), agentie=False)
    with sesiune_tenant(tenant) as db:
        assert canale.mod(db, tenant, "linkedin_pagina").mod is canale.Mod.ASISTAT
    pune_aprobarea("linkedin", "pagina", "aprobata")
    try:
        with sesiune_tenant(tenant) as db:
            assert canale.mod(db, tenant, "linkedin_pagina").automat
        lid2 = livrabil_in_publicare(tenant, om, canal="linkedin_pagina")
        assert (
            efecte.incearca_efect(tenant, cere(tenant, lid2, {"text": "Cafeneaua Zorilor angajează."}))
            == "trimis"
        )
        assert li.postari[-1]["author"] == li.organizatie
    finally:
        pune_aprobarea("linkedin", "pagina", "in_test")
