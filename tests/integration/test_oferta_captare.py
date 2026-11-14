"""F7.9 — oferta, pâlnia și paginile de captare. „Gata când”: pagina de audit a agenției este generată din platformă,
trece G2, G3 și G9 și are un singur apel la acțiune. Arhitectul (D2) și copywriterul (E3) sunt modelul FALS
(# SIMULAT, texte scriptate); validarea e cascada reală; agenția e un brand propriu (client de probă)."""

# ruff: noqa: F811
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from app import oferta
from app.db import sesiune_tenant
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele, raspuns_json  # noqa: F401
from tests.validare_utile import fapt_aprobat

pytestmark = pytest.mark.db
APEL = "Cere auditul gratuit"


def scriptat(modele: ModelFals, *, al_doilea_apel: bool = False) -> None:
    modele.handlere["Propune magnetul și traseul"] = lambda c: raspuns_json(
        magnet="Un audit gratuit al prezenței online, cu trei lucruri de făcut luna aceasta.",
        promisiune="Afli în câteva minute ce îți lipsește ca să fii ales de clienți noi.",
        public="Proprietari de firme mici din România, fără echipă de marketing.",
        traseu=[
            "Pagina de captare",
            "Confirmarea adresei",
            "Raportul de audit",
            "Alegerea pachetului",
            "Plata",
        ],
    )
    benef = ["Vezi ce spune site-ul tău despre ce vinzi și cui.", "Afli ce lipsește ca un client nou să te aleagă.",
             "Primești trei lucruri concrete de făcut luna aceasta."]  # fmt: skip
    if al_doilea_apel:
        benef[2] = "Sună-ne acum pentru o ofertă personalizată."
    modele.handlere["Scrie pagina de captare"] = lambda c: raspuns_json(
        titlu="Află ce îți lipsește ca să fii ales de clienți noi",
        subtitlu="Un audit gratuit al prezenței online a firmei tale, gata în câteva minute.",
        beneficii=benef,
        dovada="Auditul folosește aceeași metodă cu care lucrăm pentru brandurile noastre proprii.",
        apel=APEL,
        reclame=[f"Firma ta e greu de găsit online? {APEL}.", f"Trei lucruri de făcut luna aceasta. {APEL}.",
                 f"Vezi ce le lipsește clienților tăi pe site. {APEL}."],
        studiu_caz={"situatie": "O prăjitorie de cafea avea un site clar, dar fără un motiv de a o alege.",
                    "actiune": "Am pus oferta principală și un singur buton pe prima pagină.",
                    "rezultat": "Vizitatorii găsesc acum oferta și butonul de contact de pe telefon."},
    )  # fmt: skip


def test_pagina_de_audit_a_agentiei_trece_g2_g3_g9_si_are_un_singur_apel(
    client: TestClient, tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals
) -> None:
    scriptat(modele)
    fapt_aprobat(
        tenant, om, "termen", "Audit", "Auditul de marketing este gratuit"
    )  # faptul din registrul agenției
    with sesiune_tenant(tenant, om) as db:
        pg = oferta.pagini.genereaza(db, tenant, firma="AMA", oferta="Auditul gratuit de marketing",
                                     public="firme mici", apel=APEL, tinta="/site/audit", slug="audit-gratuit")  # fmt: skip
        assert pg.stare == "validat", pg.validare
        assert {"G2@V1", "G3@V1", "G9@V1"} <= {x.split("@")[0] + "@V1" for x in pg.validare["rulate"]}
        assert {x.split("@")[0] for x in pg.validare["rulate"]} == {"G2", "G3", "G9"}
        assert pg.validare["apeluri_in_plus"] == [] and len(pg.continut["reclame"]) == 3
        assert pg.continut["studiu_caz"]["rezultat"]
        assert client.get("/site/p/audit-gratuit").status_code == 404  # nepublicată
        oferta.pagini.publica(db, pg.id, utilizator_id=om)
    h = client.get("/site/p/audit-gratuit").text
    assert len(re.findall(r'class="cta"', h)) == 1 and f'<a class="cta" href="/site/audit">{APEL}</a>' in h
    assert "Află ce îți lipsește" in h and "<script src" not in h


def test_o_pagina_cu_al_doilea_apel_la_actiune_e_respinsa(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals
) -> None:
    scriptat(modele, al_doilea_apel=True)
    fapt_aprobat(tenant, om, "termen", "Audit", "Auditul de marketing este gratuit")
    with sesiune_tenant(tenant, om) as db:
        pg = oferta.pagini.genereaza(db, tenant, firma="AMA", oferta="Auditul gratuit", public="firme mici",
                                     apel=APEL, tinta="/site/audit", slug="audit-doi")  # fmt: skip
        assert pg.stare == "respins" and pg.validare["apeluri_in_plus"] == ["Sună"]
        with pytest.raises(oferta.pagini.EroareOferta):
            oferta.pagini.publica(db, pg.id, utilizator_id=om)
