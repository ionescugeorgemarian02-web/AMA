"""F6.7 — capturarea feedbackului. „Gata când”: o respingere apare ca exemplu negativ în contextul următoarei sarcini
similare. Editarea omului devine exemplu de aur cu ciorna. Brandul FICTIV, modelul FALS (# SIMULAT)."""

# ruff: noqa: F811
import uuid

import pytest

from app import continut, creier, productie
from app.continut import pipeline
from app.conturi import Rol
from app.creier.compartimente import Compartiment
from app.db import sesiune_tenant
from app.productie import Stare
from app.validare import birou
from tests.continut_utile import model_brief, model_postari
from tests.integration.lant_continut import calendar_aprobat, fara_cereri_ramase  # noqa: F401
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele, prompt_complet  # noqa: F401

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fara_cereri_ramase")]
FRAZA = "Prea insistent pe preț, vrem mai multă poveste"


def test_respingerea_devine_exemplu_negativ_in_contextul_urmatoarei_sarcini_similare(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    cal, _ = calendar_aprobat(tenant, om, modele)
    model_brief(modele)
    model_postari(modele)
    prompturi: list[str] = []
    for cheie in (
        "Scrie brieful livrabilului",
        "Propune deschideri pentru materialul",
        "Scrie postarea pentru",
    ):
        h = modele.handlere[cheie]
        modele.handlere[cheie] = lambda c, h=h: (prompturi.append(prompt_complet(c)), h(c))[1]
    with sesiune_tenant(tenant) as db:
        a, b, c3 = [i.livrabil_id for i in continut.calendar.intrari(db, cal) if i.tip == "postare"][:3]
    assert pipeline.produ(tenant, a) == Stare.ASTEAPTA_APROBARE.value
    assert not any("Exemple respinse" in p for p in prompturi)  # încă nu există exemple
    with sesiune_tenant(tenant, om) as db:
        ap = productie.aprobari.cerere_activa(db, a)
        assert ap is not None
        productie.aprobari.decide(
            db, ap.id, productie.Hotarare.RESPINS, utilizator_id=om, rol=Rol.PROPRIETAR,
            motiv_standard="hook_slab", motiv=FRAZA,
        )  # fmt: skip
        [(intrare, v)] = creier.lista(db, tenant_id=tenant, compartiment=Compartiment.EXEMPLE_NEGATIVE)
        assert v is not None and v.aprobat_prin == "sistem" and v.continut["motiv"] == FRAZA
        assert v.continut["motiv_cod"] == "hook_slab" and v.continut["tip"] == "postare"
        respins_text = v.continut["text"]
    prompturi.clear()
    # următoarea sarcină similară (postare pe Facebook): brieful și autorii primesc exemplul negativ, cu motivul
    assert pipeline.produ(tenant, b) == Stare.ASTEAPTA_APROBARE.value
    with sesiune_tenant(tenant) as db:
        br = continut.brief.al_livrabilului(db, b)
        assert br is not None and br.pachet_id is not None
        pachet = creier.context.citeste_pachet(db, br.pachet_id)
        assert pachet is not None
        [neg] = pachet.sectiune("exemple_negative")
        assert neg.id == str(intrare.id) and FRAZA in neg.text and respins_text[:40] in neg.text
    assert len(prompturi) == 3
    assert all(FRAZA in p for p in prompturi), "brieful, hook-urile și postarea văd exemplul negativ"
    assert "Exemple respinse, de evitat" in prompturi[0] and "NU le repeta" in prompturi[2]
    # editarea omului devine exemplu de aur, cu ciorna mașinii
    with sesiune_tenant(tenant, om) as db:
        ap = productie.aprobari.cerere_activa(db, b)
        assert ap is not None
        birou.editeaza(
            db, ap.id, versiune=ap.versiune, utilizator_id=om,
            text="Știi ce înseamnă data prăjirii?\n\nLa Cafeneaua Zorilor prăjim cafeaua în loturi mici. "
            "Comandă acum din magazinul online.",
        )  # fmt: skip
    assert pipeline.produ(tenant, b) == Stare.ASTEAPTA_APROBARE.value
    with sesiune_tenant(tenant, om) as db:
        ap = productie.aprobari.cerere_activa(db, b)
        assert ap is not None
        productie.aprobari.decide(db, ap.id, productie.Hotarare.APROBAT, utilizator_id=om, rol=Rol.PROPRIETAR)
        [(_, aur)] = creier.lista(db, tenant_id=tenant, compartiment=Compartiment.EXEMPLE_AUR)
        assert (
            aur is not None
            and aur.continut["ciorna"]
            and "prăjim cafeaua în loturi mici." in aur.continut["text"]
        )
    prompturi.clear()
    assert pipeline.produ(tenant, c3) == Stare.ASTEAPTA_APROBARE.value
    assert "Aprobat după editarea omului" in prompturi[0] and FRAZA in prompturi[0]
