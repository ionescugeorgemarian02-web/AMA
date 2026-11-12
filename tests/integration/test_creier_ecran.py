"""F4.8 — ecranul „Creierul de brand”. „Gata când”: editezi și aprobi de pe telefon. În teste: fluxul HTTP complet (editare =
propunere nouă, diferență, aprobare, respingere, retragere, CSRF, permisiuni, audit) și verificarea că paginile sunt utilizabile
la lățime mică (fără tabele, fără stiluri sau scripturi inline, cu `viewport`)."""

# ruff: noqa: F811
import re
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app import creier
from app.conturi import Rol
from app.creier.compartimente import Compartiment, SursaTip
from app.db import sesiune_tenant
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401

pytestmark = pytest.mark.db
Fabrica = Callable[..., Cont]
GHID = {
    "nume": "Barista prietenos",
    "descriere": "Brandul sună cald, ca un barista care explică pe îndelete.",
    "reguli_da": ["Spune pe nume ce e în pachet", "Dă data prăjirii"],
    "reguli_nu": ["Nu promite efecte medicale", "Nu compara cu alte firme"],
}


@pytest.fixture
def proprietar(client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]) -> Cont:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    return cont


def intrare(tenant: uuid.UUID, om: uuid.UUID, comp: Compartiment = Compartiment.PROFIL_BRAND, cheie: str = "ghid",
            continut: dict[str, Any] | None = None, aprobata: bool = True) -> uuid.UUID:  # fmt: skip
    with sesiune_tenant(tenant, om) as db:
        i, v = creier.creeaza_intrare(
            db, tenant_id=tenant, compartiment=comp, cheie=cheie, continut=continut or GHID, sursa=creier.Sursa(SursaTip.OM),
            utilizator_id=om,
        )  # fmt: skip
        if aprobata:
            creier.aproba(db, i.id, v.nr, utilizator_id=om)
        return i.id


def post(client: TestClient, cale: str, **date: str) -> Any:
    return client.post(cale, data={**date, "csrf_token": csrf(client)}, follow_redirects=False)


def audit(admin: Engine, actiune: str, intrare_id: uuid.UUID) -> list[dict[str, Any]]:
    with admin.connect() as c:
        return [
            dict(r._mapping)
            for r in c.execute(
                text(
                    "SELECT utilizator_id, detalii FROM jurnal_audit WHERE actiune = :a AND detalii->>'intrare' = :i"
                ),
                {"a": actiune, "i": str(intrare_id)},
            )
        ]


def fara_inline(html: str) -> None:
    """CSP strict: fără stiluri sau scripturi inline, fără handlere `on…=`."""
    assert "style=" not in html and "<style" not in html
    assert not re.search(r"<script(?![^>]*\bsrc=)", html) and not re.search(r"\son[a-z]+\s*=", html)


def test_ecranul_arata_compartimentele_cu_versiunea_aprobata_propunerile_si_sursele(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, om: uuid.UUID
) -> None:
    iid = intrare(tenant, om)
    with sesiune_tenant(tenant, om) as db:
        creier.propune_schimbare(
            db,
            iid,
            continut={**GHID, "nume": "Barista vesel"},
            sursa=creier.Sursa(SursaTip.OM),
            utilizator_id=om,
        )
    html = client.get(f"/creier/client/{tenant}").text
    for nume in (
        "Profil de brand",
        "Registru de fapte",
        "Catalog de oferte",
        "Brief de onboarding",
        "Insight de piață",
        "Strategie",
        "Constrângeri",
    ):
        assert nume in html
    assert "1 intrări" in html and "1 aprobate" in html and "1 în așteptare" in html
    assert "Propuneri în așteptare (1)" in html and f"/creier/intrare/{iid}" in html
    assert f'href="/creier/fapte?client={tenant}"' in html  # faptele: integrate, nu dublate
    assert (
        'href="/creier/client/' in html
        and "Surse" in html
        and 'href="/creier/client' in client.get("/onboarding/" + str(tenant)).text
    )
    assert "<table" not in html
    lista = client.get(f"/creier/client/{tenant}/profil_brand").text
    assert "ghid" in lista and "aprobată: versiunea 1" in lista and "1 propunere(i) în așteptare" in lista
    r = client.get(f"/creier/client/{tenant}/registru_fapte", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/creier/fapte?client={tenant}"
    assert client.get(f"/creier/client/{tenant}/inexistent").status_code == 404
    assert client.get(f"/creier/client/{uuid.uuid4()}").status_code == 404
    assert 'href="/creier/client"' in client.get("/meniu").text  # accesibil din meniu


def test_editarea_creeaza_o_propunere_nu_suprascrie_diferenta_aprobarea_si_istoricul(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    iid = intrare(tenant, om)
    pagina = client.get(f"/creier/intrare/{iid}").text
    assert (
        "Versiunea aprobată" in pagina
        and 'name="c_descriere"' in pagina
        and "Salvează ca propunere" in pagina
    )
    assert (
        client.post(f"/creier/intrare/{iid}/editeaza", data={"c_nume": "Nou"}).status_code == 403
    )  # fără CSRF
    r = post(
        client,
        f"/creier/intrare/{iid}/editeaza",
        c_nume="Barista vesel",
        c_reguli_da="Spune pe nume ce e în pachet\nZâmbește\n",
        motiv="mai vesel",
    )
    assert r.status_code == 303 and r.headers["location"] == f"/creier/intrare/{iid}?mesaj=editat"
    with sesiune_tenant(tenant) as db:
        v1, v2 = creier.istoric(db, iid)
        assert (
            v1.stare == "aprobat" and v1.continut["nume"] == "Barista prietenos"
        )  # versiunea veche neatinsă
        assert (
            v2.stare == "propus"
            and v2.continut["nume"] == "Barista vesel"
            and v2.continut["reguli_da"] == ["Spune pe nume ce e în pachet", "Zâmbește"]
        )
        assert (
            v2.continut["descriere"] == GHID["descriere"]
            and v2.motiv == "mai vesel"
            and v2.creat_de == proprietar.id
        )
    pagina = client.get(f"/creier/intrare/{iid}").text  # diferența implicită: aprobata față de propunere
    assert (
        "Propunere în așteptare" in pagina
        and "Diferența v1 → v2" in pagina
        and "nume" in pagina
        and "Barista vesel" in pagina
    )
    pagina = client.get(f"/creier/intrare/{iid}?a=1&b=2").text
    assert ("reguli_da.1" in pagina and "schimbat" in pagina) or "adaugat" in pagina
    assert "Aprobă v2" in pagina and "Respinge" in pagina
    r = post(client, f"/creier/intrare/{iid}/aproba", versiune="2")
    assert r.status_code == 303 and r.headers["location"].endswith("mesaj=aprobat")
    with sesiune_tenant(tenant) as db:
        v1, v2 = creier.istoric(db, iid)
        assert (v1.stare, v1.retras_cauza, v1.inlocuita_de, v2.stare) == ("retras", "inlocuita", 2, "aprobat")
    a = audit(admin_engine, "creier.versiune_aprobata", iid)[-1]
    assert a["utilizator_id"] == proprietar.id  # aprobarea poartă omul; propunerile și retragerile la fel
    assert len(audit(admin_engine, "creier.versiune_propusa", iid)) == 1
    # a doua aprobare pe aceeași versiune: refuzată
    assert post(client, f"/creier/intrare/{iid}/aproba", versiune="2").status_code == 409


def test_respingerea_cere_motiv_iar_retragerea_scoate_versiunea_din_uz(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, om: uuid.UUID
) -> None:
    iid = intrare(tenant, om)
    post(client, f"/creier/intrare/{iid}/editeaza", c_nume="Alt nume")
    r = post(client, f"/creier/intrare/{iid}/respinge", versiune="2", motiv=" ")
    assert r.status_code == 422 and "Scrie motivul" in r.text
    r = post(client, f"/creier/intrare/{iid}/respinge", versiune="2", motiv="nu se potrivește tonului")
    assert r.status_code == 303
    with sesiune_tenant(tenant) as db:
        v = creier.citeste(db, iid, 2)
        assert (v.stare, v.retras_cauza, v.retras_motiv) == ("retras", "respins", "nu se potrivește tonului")
        assert creier.versiune_aprobata(db, iid).nr == 1  # type: ignore[union-attr]
    assert "nu se potrivește tonului" in client.get(f"/creier/intrare/{iid}").text
    r = post(client, f"/creier/intrare/{iid}/retrage", versiune="1", motiv="brandul își schimbă tonul")
    assert r.status_code == 303
    with sesiune_tenant(tenant) as db:
        assert creier.versiune_aprobata(db, iid) is None
        assert creier.citeste(db, iid, 1).retras_cauza == "retras"
    assert "Nicio versiune aprobată" in client.get(f"/creier/intrare/{iid}").text


def test_o_editare_care_incalca_poarta_sau_schema_nu_se_salveaza(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, om: uuid.UUID
) -> None:
    from tests.unit.test_onboarding_brief import brief_complet

    iid = intrare(tenant, om, Compartiment.BRIEF, "brief", brief_complet())
    gol = '{"valoare": "-", "surse": []}'
    r = post(client, f"/creier/intrare/{iid}/editeaza", c_ton_dorit=gol)
    assert (
        r.status_code == 422 and "Modificarea nu a fost salvată" in r.text and "Ton dorit" in r.text
    )  # poarta brieful
    r = post(client, f"/creier/intrare/{iid}/editeaza", c_ton_dorit="{nu e json")
    assert r.status_code == 422 and "JSON valid" in r.text
    with sesiune_tenant(tenant) as db:
        assert len(creier.istoric(db, iid)) == 1  # nicio propunere nouă


def test_ciorna_se_trimite_spre_aprobare_din_ecran(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, om: uuid.UUID
) -> None:
    with sesiune_tenant(tenant, om) as db:
        i, _ = creier.creeaza_intrare(db, tenant_id=tenant, compartiment=Compartiment.CONSTRANGERI, cheie="r1",
                                      continut={"regula": "Fără promisiuni medicale"}, sursa=creier.Sursa(SursaTip.OM),
                                      utilizator_id=om, propune=False)  # fmt: skip
        iid = i.id
    assert "Trimite spre aprobare" in client.get(f"/creier/intrare/{iid}").text
    assert post(client, f"/creier/intrare/{iid}/trimite", versiune="1").status_code == 303
    with sesiune_tenant(tenant) as db:
        assert creier.citeste(db, iid, 1).stare == "propus"


def test_permisiunile_analistul_nu_decide_nu_editeaza_si_nu_porneste_pasi(
    client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float], tenant: uuid.UUID, om: uuid.UUID
) -> None:
    iid = intrare(tenant, om)
    cont = fabrica_conturi(Rol.ANALIST, cu_totp=True)
    autentifica(client, cont, ceas)
    assert client.get("/creier/client").status_code == 200  # citește lista de clienți
    for cale, date in (
        (f"/creier/intrare/{iid}/editeaza", {"c_nume": "x"}),
        (f"/creier/intrare/{iid}/aproba", {"versiune": "1"}),
        (f"/creier/intrare/{iid}/respinge", {"versiune": "1", "motiv": "nu"}),
        (f"/creier/intrare/{iid}/retrage", {"versiune": "1", "motiv": "nu"}),
        (f"/creier/client/{tenant}/pas/ton", {}),
        (f"/creier/client/{tenant}/concurent", {"nume": "X"}),
    ):
        assert post(client, cale, **date).status_code == 403, cale


def test_pasii_de_pregatire_si_concurentii_se_pornesc_din_ecran(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID
) -> None:
    html = client.get(f"/creier/client/{tenant}").text
    assert "Pregătirea Creierului" in html and "Propune strategia" in html and "Adaugă concurentul" in html
    r = post(client, f"/creier/client/{tenant}/concurent", nume="Cafeneaua Brumei")
    assert r.status_code == 303
    assert "Cafeneaua Brumei" in client.get(f"/creier/client/{tenant}").text
    assert (
        "doar pentru analiză" in client.get(f"/creier/client/{tenant}").text
    )  # textul concurenței nu se reutilizează
    r = post(client, f"/creier/client/{tenant}/pas/necunoscut")
    assert r.status_code == 404


def test_paginile_sunt_utilizabile_pe_telefon_fara_tabele_si_fara_inline(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, om: uuid.UUID
) -> None:
    iid = intrare(tenant, om)
    post(client, f"/creier/intrare/{iid}/editeaza", c_nume="Altul")
    for cale in ("/meniu", f"/creier/client/{tenant}", f"/creier/client/{tenant}/profil_brand", f"/creier/intrare/{iid}",
                 f"/creier/intrare/{iid}?a=1&b=2", f"/onboarding/{tenant}", f"/campanii/{tenant}"):  # fmt: skip
        r = client.get(cale)
        assert r.status_code == 200, cale
        assert "<table" not in r.text, cale  # nicio tabelă care să forțeze derularea orizontală
        assert 'name="viewport"' in r.text and "width=device-width" in r.text, cale
        fara_inline(r.text)
        csp = r.headers.get("Content-Security-Policy", "")
        assert csp and "'unsafe-inline'" not in csp, cale  # CSP strict: nimic inline
