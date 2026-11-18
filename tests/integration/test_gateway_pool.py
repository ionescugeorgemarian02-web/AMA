"""G-pool pe bază reală: sămânța catalogului, seiful, rutarea cu „altă familie” și sănătatea pe model."""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Engine, text

from app.db import sesiune_agentie, sesiune_tenant
from app.gateway import apel, catalog, sanatate_model, secrete, seif
from app.gateway.apel import ContextApel, Rezultat
from tests.furnizor_fals import FurnizorFals
from tests.gateway_utile import CeasControlat, FabricaModele, gazda
from tests.integration import fluxuri_gateway as proba


@pytest.fixture(autouse=True)
def _mediu(cheie_proba: str, ceas_controlat: CeasControlat, fals: FurnizorFals) -> Iterator[None]:
    fals.text = '{"eticheta": "ok", "dovezi": ["d"], "incredere": 0.7}'
    sanatate_model.reseteaza()
    yield
    sanatate_model.reseteaza()


def apeleaza(tenant: uuid.UUID, profil: str, **kw: Any) -> Rezultat:
    with sesiune_tenant(tenant) as db:
        ctx = ContextApel(
            db=db, tenant_id=tenant, profil=profil, mesaje=proba.MESAJE, schema=proba.Raspuns,
            componenta="test", **kw,
        )  # fmt: skip
        return apel.ruleaza(ctx)


def test_samanta_catalogului_e_inactiva_si_profilurile_au_rezerva(admin_engine: Engine) -> None:
    with admin_engine.connect() as c:
        randuri = c.execute(
            text("SELECT cod, stare FROM gateway_furnizori WHERE cod = ANY(:c)"), {"c": list(catalog.POOL)}
        ).all()
        furnizori = {r.cod: r.stare for r in randuri}
        modele = c.execute(
            text("SELECT count(*) FROM gateway_modele WHERE sursa = 'catalog G-pool'")
        ).scalar_one()
        lant = c.execute(text("SELECT lant FROM gateway_profiluri WHERE nume = 'judecata'")).scalar_one()
        consiliu = c.execute(text("SELECT lant FROM gateway_profiluri WHERE nume = 'consiliu'")).scalar_one()
    assert set(furnizori) == set(catalog.POOL)
    noi = set(catalog.POOL) - {"openrouter", "groq", "gemini", "cloudflare"}
    assert all(furnizori[f] == "inactiv" for f in noi)  # proprietarul confirmă termenii și activează (8.1)
    assert modele > 20
    assert lant[-1] == "rezerva:judecata" and not any(x.startswith("rezerva:") for x in consiliu)


def test_seiful_cripteaza_si_refuza_numele_din_afara_catalogului(admin_engine: Engine) -> None:
    try:
        with sesiune_agentie() as db:
            seif.pune(db, "SAMBANOVA_API_KEY", "valoare-din-seif")
            with pytest.raises(ValueError):
                seif.pune(db, "AMA_MASTER_KEY", "x")
        with admin_engine.connect() as c:
            blob = c.execute(
                text("SELECT valoare FROM gateway_seif WHERE nume = 'SAMBANOVA_API_KEY'")
            ).scalar_one()
        assert b"valoare-din-seif" not in bytes(blob)
        assert seif.citeste("SAMBANOVA_API_KEY") == "valoare-din-seif"
        assert secrete.complet("sambanova")
    finally:
        with sesiune_agentie() as db:
            seif.sterge(db, "SAMBANOVA_API_KEY")
    assert seif.citeste("SAMBANOVA_API_KEY") is None


def test_judecatorul_alege_alta_familie_decat_autorul(
    tenant: uuid.UUID, fabrica_modele: FabricaModele, fals: FurnizorFals
) -> None:
    fa, fb, fc = fabrica_modele.furnizor(), fabrica_modele.furnizor(), fabrica_modele.furnizor()
    autor = fabrica_modele.model(fa, identificator="llama-3.3-70b")
    tot_llama = fabrica_modele.model(fb, identificator="llama-3.1-8b")
    qwen = fabrica_modele.model(fc, identificator="qwen3-32b")
    profil = fabrica_modele.profil([autor.cod, tot_llama.cod, qwen.cod])
    r = apeleaza(tenant, profil, alt_model_decat=autor.cod, alta_familie=True)
    assert r.model == qwen.cod
    assert not fals.cereri_la(gazda(tot_llama))
    assert apeleaza(tenant, profil, alt_model_decat=autor.cod).model == tot_llama.cod  # fără paza familiei


def test_modelul_inexistent_cade_pe_urmatorul_si_nu_mai_e_incercat(
    tenant: uuid.UUID, fabrica_modele: FabricaModele, fals: FurnizorFals
) -> None:
    fa, fb = fabrica_modele.furnizor(), fabrica_modele.furnizor()
    a = fabrica_modele.model(fa, identificator="disparut")
    b = fabrica_modele.model(fb, identificator="rezerva")
    profil = fabrica_modele.profil([a.cod, b.cod])
    fals.scenariu(gazda(a), permanent="404")
    assert apeleaza(tenant, profil).model == b.cod
    assert a.cod in sanatate_model.indisponibile()
    assert apeleaza(tenant, profil).model == b.cod
    assert len(fals.cereri_la(gazda(a))) == 1  # a doua oară modelul bolnav nu mai primește cererea
