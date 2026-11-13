"""F6.6 — publicarea asistată. „Gata când”: publici o postare reală din două atingeri și linkul ei apare în sistem. Postarea
e a brandului FICTIV, modelul FALS, iar „publicarea” e simulată: omul din test lipește un link de Facebook inventat
(# SIMULAT). Telefonul real și postarea reală, la migrare."""

# ruff: noqa: F811
import re
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app import continut, productie, publicare, validare
from app.conturi import Rol
from app.db import sesiune_tenant
from app.productie import Stare
from tests.continut_utile import model_postari
from tests.integration.conftest import Cont
from tests.integration.lant_continut import cu_briefuri, fara_cereri_ramase  # noqa: F401
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.onboarding_utile import ModelFals, model_fals, modele  # noqa: F401

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("fara_cereri_ramase")]
LINK = "https://www.facebook.com/cafeneauazorilor/posts/1234567890"


def postare_la_aprobare(tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals) -> uuid.UUID:
    cal, _ = cu_briefuri(tenant, om, modele)
    model_postari(modele)
    with sesiune_tenant(tenant) as db:
        lid = next(i.livrabil_id for i in continut.calendar.intrari(db, cal) if i.tip == "postare")
    assert lid is not None and continut.pipeline.produ(tenant, lid) == Stare.ASTEAPTA_APROBARE.value
    return lid


def test_aprobata_pachet_pe_telefon_partajare_link_lipit_publicata(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float],
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None,
) -> None:  # fmt: skip
    lid = postare_la_aprobare(tenant, om, modele)
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    with sesiune_tenant(tenant) as db:
        ap = productie.aprobari.cerere_activa(db, lid)
        assert ap is not None
        text_aprobat = validare.continut.citeste(db, lid).text
    r = client.post(f"/aprobari/{ap.id}/aproba", data={"csrf_token": csrf(client, "/aprobari"), "versiune": ap.versiune},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    # aprobarea a pregătit singură pachetul: livrabilul e programat
    with sesiune_tenant(tenant) as db:
        lv = productie.citeste(db, lid)
        assert lv is not None and lv.stare == Stare.PROGRAMAT.value
        [p] = publicare.asistata.ale_livrabilului(db, lid)
        assert (
            p.stare == "pregatit"
            and p.versiune == lv.versiune
            and p.cheie.endswith(f":facebook:v{lv.versiune}:publicare_asistata")
        )
    # pe telefon: un card cu textul final (cu hashtag-uri) și UN buton „Partajează” (atingerea 1; alegerea aplicației = 2)
    html = client.get("/publicare").text
    assert html.count('data-partajeaza="t-') == 1 and f'id="t-{p.id}"' in html
    textarea = re.search(rf'<textarea id="t-{p.id}"[^>]*>(.*?)</textarea>', html, re.S)
    assert (
        textarea is not None
        and text_aprobat.split("\n")[0] in textarea.group(1)
        and "#cafea #Brasov" in textarea.group(1)
    )
    assert "Conținut creat cu ajutorul AI" in html and "Pașii obligatorii" in html
    # un link greșit nu se salvează
    r = client.post(
        f"/publicare/{p.id}/link",
        data={"csrf_token": csrf(client, "/publicare"), "link": "https://exemplu.test/x"},
    )
    assert r.status_code == 422 and "nu este pe facebook" in r.text
    r = client.post(
        f"/publicare/{p.id}/link",
        data={"csrf_token": csrf(client, "/publicare"), "link": LINK},
        follow_redirects=False,
    )
    assert r.status_code == 303
    html = client.get("/publicare?mesaj=publicat").text
    assert "Linkul a fost salvat" in html and LINK in html and "Nimic de publicat acum" in html
    with sesiune_tenant(tenant) as db:
        lv = productie.citeste(db, lid)
        assert lv is not None and lv.stare == Stare.PUBLICAT.value
        [p] = publicare.asistata.ale_livrabilului(db, lid)
        assert p.stare == "publicat" and p.link == LINK and p.publicat_de == cont.id
        ultima = productie.istoric(db, lid)[-1]
        assert (
            ultima.in_stare == "publicat"
            and ultima.detalii["link"] == LINK
            and ultima.utilizator_id == cont.id
        )
        with pytest.raises(publicare.asistata.EroarePublicare, match="deja publicat"):
            publicare.asistata.confirma(db, p.id, link=LINK, utilizator_id=cont.id)


def test_pregatirea_cere_versiunea_aprobata_si_e_idempotenta(
    tenant: uuid.UUID, om: uuid.UUID, modele: ModelFals, executor: None
) -> None:
    lid = postare_la_aprobare(tenant, om, modele)
    with sesiune_tenant(tenant, om) as db:
        with pytest.raises(publicare.asistata.EroarePublicare, match="doar un livrabil aprobat"):
            publicare.asistata.pregateste(db, lid)
        ap = productie.aprobari.cerere_activa(db, lid)
        assert ap is not None
        r = productie.aprobari.decide(
            db, ap.id, productie.Hotarare.APROBAT, utilizator_id=om, rol=Rol.PROPRIETAR
        )
        assert r.stare_livrabil is Stare.PROGRAMAT
        a = publicare.asistata.pregateste(db, lid)
        assert publicare.asistata.pregateste(db, lid).id == a.id
