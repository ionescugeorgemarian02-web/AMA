"""Poarta F4 — lanțul complet, local, cu brandul FICTIV „Cafeneaua Zorilor” și modelul FALS (# SIMULAT):

colectare (site fals, robots.txt) → fapte extrase și aprobate → interviu → brief → ghid de brand → citate și profil de public →
concurenți, afirmații și brief de insight (cu sondaj) → strategie pe 90 de zile → aprobările unui om → pachet de context care
conține ghidul, faptele (doar cele aprobate) și strategia.

Poarta propriu-zisă („CariereAI și BigBrain au fiecare un Creier de brand și o strategie pe 90 de zile, aprobate”) cere materialele
și aprobarea proprietarului și NU se poate trece aici: acest test dovedește doar că lanțul funcționează cap-coadă."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app import creier
from app.conturi import Rol
from app.creier import context, fapte
from app.creier import fluxuri as fluxuri_creier
from app.creier.compartimente import Compartiment
from app.db import sesiune_tenant
from app.onboarding import brief, citate, piata, public, strategie
from app.operare import motor
from tests.integration.conftest import Cont
from tests.integration.lant_onboarding import acum_plus, pana_la_insight
from tests.integration.test_cercetare_colectare import LIMITE, mediu, ruleaza, sursa_site  # noqa: F401
from tests.integration.test_creier_extragere import model_fals as extractor_fapte
from tests.integration.test_onboarding_strategie import model_strategie, propune
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele  # noqa: F401
from tests.site_fals import SiteFals

pytestmark = pytest.mark.db
Fabrica = Callable[..., Cont]


@pytest.fixture
def proprietar(client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]) -> Cont:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    return cont


def test_lantul_f4_cap_coada(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None,
    mediu: SiteFals, admin_engine: Engine,
) -> None:  # fmt: skip
    # 1. colectare: site-ul brandului, cu robots.txt respectat
    sid_site = sursa_site(tenant, mediu)
    ruleaza(tenant, sid_site)
    assert "/privat/" not in " ".join(
        c for c, _ in mediu.cereri if c != "/robots.txt"
    )  # robots.txt interzice /privat/
    with sesiune_tenant(tenant) as db:
        assert creier.pregateste_sursa(db, sid_site) > 0
    # 2. fapte extrase din materiale (F4.6): o parte aprobate de un om, restul rămân propuse
    modele.handlere["extrage faptele atomice"] = extractor_fapte
    job = fluxuri_creier.trimite_extragerea(tenant, sid_site, cheie=f"poarta:fapte:{tenant}")
    assert motor.asteapta_flux(job, timeout_sec=60).stare.value == "terminat"
    with sesiune_tenant(tenant) as db:
        propuse = fapte.propuneri(db, tenant_id=tenant)
    assert len(propuse) >= 4
    r = client.post(
        f"/creier/fapte/{propuse[0].intrare_id}/aproba",
        data={"versiune": "1", "csrf_token": csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    aprobat_din_site = propuse[0].afirmatie
    ramase = {p.afirmatie for p in propuse[1:]}
    # 3–7. interviu → brief → ghid → public → insight (toate aprobate de un om), apoi faptele manuale
    lant = pana_la_insight(tenant, om, modele, cu_materiale=False)
    # 8. strategia
    model_strategie(modele)
    propune(tenant, om, f"poarta:strategie:{tenant}")
    with sesiune_tenant(tenant) as db:
        i = creier.gaseste_intrare(
            db, tenant_id=tenant, compartiment=Compartiment.STRATEGIE, cheie=strategie.CHEIE_STRATEGIE
        )
        assert i is not None
        strategie_id = i.id
    pagina = client.get(f"/campanii/{tenant}").text
    assert "Propunere în așteptare" in pagina and "Criteriul de oprire" in pagina
    r = client.post(
        f"/campanii/{tenant}/{strategie_id}/aproba",
        data={"versiune": "1", "csrf_token": csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    pagina = client.get(f"/campanii/{tenant}").text
    assert (
        "Strategia aprobată" in pagina
        and "Abonamente lunare noi" in pagina
        and "aprobată" in client.get("/campanii").text
    )
    # 9. Creierul clientului: fiecare compartiment al lanțului are ce trebuie aprobat
    with sesiune_tenant(tenant) as db:
        rez = creier.rezumat_pe_compartimente(db, tenant)
        assert rez[Compartiment.BRIEF].aprobate == 1 and rez[Compartiment.PROFIL_BRAND].aprobate == 1
        assert rez[Compartiment.STRATEGIE].aprobate == 1
        assert rez[Compartiment.INSIGHT_PUBLIC].aprobate >= citate.MINIM_CITATE + 1  # citatele + profilul
        assert rez[Compartiment.INSIGHT_PIATA].aprobate >= 10  # afirmațiile concurenței + brieful de insight
        assert (
            brief.lipsuri(
                creier.versiune_aprobata(
                    db,
                    creier.gaseste_intrare(
                        db, tenant_id=tenant, compartiment=Compartiment.BRIEF, cheie="brief"
                    ).id,
                ).continut
            )
            == []
        )  # type: ignore[union-attr]
        raport = piata.verifica_prin_sondaj(
            db, tenant, creier.versiune_aprobata(db, lant.insight_id).continut
        )  # type: ignore[arg-type, union-attr]
        assert raport.trece
        profil = creier.versiune_aprobata(db, lant.profil_public_id).continut  # type: ignore[arg-type, union-attr]
        assert public.probleme_profil(db, tenant, profil) == []
    html = client.get(f"/creier/client/{tenant}").text
    assert "<table" not in html and "Strategie" in html and "Insight de public" in html
    # 10. pachetul de context al unei sarcini conține ghidul, faptele APROBATE și strategia; nimic neaprobat
    with sesiune_tenant(tenant) as db:
        p = context.construieste(
            db, tenant_id=tenant, tip_sarcina="postare_facebook", canal="facebook",
            intrebare="Postare despre cafeaua Etiopia Guji, prețul ei și livrarea", salveaza=False, la=acum_plus(),
            sectiuni_extra=("strategie",),
        )  # fmt: skip
    text_pachet = context.ca_text(p)
    assert (
        "ghid_brand" not in p.lipsuri
        and p.sectiune("ghid")
        and p.sectiune("strategie")
        and p.sectiune("fapte")
    )
    assert "Expertul calm" in text_pachet and "Abonamente lunare noi" in text_pachet
    fapte_in_pachet = " ".join(e.text for e in p.sectiune("fapte"))
    assert "Etiopia Guji, 250 g, costă 49 lei" in fapte_in_pachet  # fapt aprobat de un om
    for neaprobat in ramase:
        assert neaprobat not in fapte_in_pachet  # propunerile neaprobate din colectare nu intră
    assert (
        ramase and aprobat_din_site
    )  # au existat propuneri neaprobate din colectare, și niciuna nu a intrat
    # 11. auditul: fiecare aprobare poartă omul
    with admin_engine.connect() as c:
        aprobari = c.execute(
            text(
                "SELECT count(*) FROM jurnal_audit WHERE tenant_id = :t AND actiune = 'creier.versiune_aprobata' AND utilizator_id IS NOT NULL"
            ),
            {"t": tenant},
        ).scalar_one()
    assert aprobari >= 6  # brief, ghid, profil de public, brief de insight, strategie, faptele
