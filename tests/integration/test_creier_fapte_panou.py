"""F4.6 — punctul minim din panou pentru faptele Creierului: lista propunerilor, „Aprobă” și „Respinge”, cu CSRF,
permisiune (`creier.editeaza`), audit, și efectul asupra contextului. Ecranul bogat este F4.8."""

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.conturi import Rol
from app.creier import fapte
from app.creier.compartimente import SursaTip
from app.creier.versiuni import Sursa
from app.db import sesiune_tenant
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica, csrf

pytestmark = pytest.mark.db
Fabrica = Callable[..., Cont]
CITAT = "Etiopia Guji, natural, 250 g: 49 lei"


@pytest.fixture
def proprietar(client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]) -> Cont:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    return cont


def fapt_propus(
    tenant: uuid.UUID, om: uuid.UUID, afirmatie: str = "Etiopia Guji 250 g costă 49 lei"
) -> uuid.UUID:
    with sesiune_tenant(tenant, om) as db:
        i, _, _ = fapte.propune_fapt(
            db, tenant_id=tenant,
            continut={"tip": "pret", "subiect": "Etiopia Guji", "afirmatie": afirmatie,
                      "valoare": {"numar": "49", "moneda": "RON", "unitate": "250 g"}},
            sursa=Sursa(SursaTip.DECLARATIE_CLIENT, citat=CITAT, detalii={"url": "https://zorilor.exemplu.test/produse", "pozitie": 0}),
            utilizator_id=om,
        )  # fmt: skip
        return i.id


def in_context(tenant: uuid.UUID) -> list[str]:
    with sesiune_tenant(tenant) as db:
        return [f.afirmatie for f in fapte.pentru_context(db, tenant, dt.datetime.now(dt.UTC))]


def audit(admin: Engine, actiune: str, intrare: uuid.UUID) -> list[dict[str, object]]:
    with admin.connect() as c:
        return [
            dict(r._mapping)
            for r in c.execute(
                text(
                    "SELECT utilizator_id, tenant_id, detalii FROM jurnal_audit WHERE actiune = :a AND detalii->>'intrare' = :i"
                ),
                {"a": actiune, "i": str(intrare)},
            )
        ]


def test_lista_arata_propunerile_cu_sursa_citat_si_valoare(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, om: uuid.UUID
) -> None:
    iid = fapt_propus(tenant, om)
    html = client.get("/creier/fapte").text
    assert "Preț · Etiopia Guji" in html and "Etiopia Guji 250 g costă 49 lei" in html
    assert f"„{CITAT}”" in html and "zorilor.exemplu.test/produse" in html and "49 RON 250 g" in html
    assert f'action="/creier/fapte/{iid}/aproba"' in html and f'action="/creier/fapte/{iid}/respinge"' in html
    assert "Doar un fapt aprobat de un om intră în context" in html
    assert 'href="/creier/fapte"' in client.get("/meniu").text  # accesibil din meniu


def test_aprobarea_cere_csrf_se_audita_si_face_faptul_utilizabil_in_context(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    iid = fapt_propus(tenant, om)
    assert client.post(f"/creier/fapte/{iid}/aproba", data={"versiune": "1"}).status_code == 403  # fără CSRF
    assert (
        client.post(f"/creier/fapte/{iid}/aproba", data={"versiune": "1", "csrf_token": "gresit"}).status_code
        == 403
    )
    assert in_context(tenant) == []
    r = client.post(
        f"/creier/fapte/{iid}/aproba",
        data={"versiune": "1", "csrf_token": csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/creier/fapte?mesaj=aprobat"
    assert in_context(tenant) == ["Etiopia Guji 250 g costă 49 lei"]
    [a] = audit(admin_engine, "creier.versiune_aprobata", iid)
    assert a["utilizator_id"] == proprietar.id and a["tenant_id"] == tenant
    html = client.get("/creier/fapte?mesaj=aprobat").text
    assert (
        "Faptul a fost aprobat" in html and f"/creier/fapte/{iid}/aproba" not in html
    )  # dispare din lista de aprobat


def test_respingerea_cere_motiv_si_scoate_faptul_din_lista_fara_sa_il_lase_in_context(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, om: uuid.UUID, admin_engine: Engine
) -> None:
    iid = fapt_propus(tenant, om)
    jeton = csrf(client)
    r = client.post(
        f"/creier/fapte/{iid}/respinge", data={"versiune": "1", "motiv": " ", "csrf_token": jeton}
    )
    assert r.status_code == 422 and "motivul respingerii" in r.text
    r = client.post(
        f"/creier/fapte/{iid}/respinge",
        data={"versiune": "1", "motiv": "prețul s-a schimbat", "csrf_token": jeton},
        follow_redirects=False,
    )
    assert r.status_code == 303 and in_context(tenant) == []
    [a] = audit(admin_engine, "creier.versiune_retrasa", iid)
    assert a["utilizator_id"] == proprietar.id and a["detalii"]["cauza"] == "respins"  # type: ignore[index]
    assert f"/creier/fapte/{iid}/" not in client.get("/creier/fapte").text
    with sesiune_tenant(tenant) as db:
        assert fapte.fapt(db, iid).stare is fapte.StareFapt.RESPINS


def test_a_doua_decizie_pe_acelasi_fapt_este_refuzata(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, om: uuid.UUID
) -> None:
    iid = fapt_propus(tenant, om)
    jeton = csrf(client)
    assert (
        client.post(
            f"/creier/fapte/{iid}/aproba", data={"versiune": "1", "csrf_token": jeton}, follow_redirects=False
        ).status_code
        == 303
    )
    r = client.post(
        f"/creier/fapte/{iid}/respinge",
        data={"versiune": "1", "motiv": "m-am răzgândit", "csrf_token": jeton},
    )
    assert r.status_code == 409 and "doar o versiune propusă" in r.text
    assert (
        client.post(
            f"/creier/fapte/{uuid.uuid4()}/aproba", data={"versiune": "1", "csrf_token": jeton}
        ).status_code
        == 404
    )
    assert (
        client.post("/creier/fapte/nu-e-uuid/aproba", data={"versiune": "1", "csrf_token": jeton}).status_code
        == 404
    )


def test_doar_agentia_vede_lista_iar_aprobarea_cere_permisiunea_de_editare(
    client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float], tenant: uuid.UUID, om: uuid.UUID
) -> None:
    iid = fapt_propus(tenant, om)
    assert client.get("/creier/fapte", follow_redirects=False).status_code in (303, 401)  # fără sesiune
    operator = fabrica_conturi(Rol.OPERATOR, cu_totp=True)
    autentifica(client, operator, ceas)
    assert (
        client.get("/creier/fapte").status_code == 200
    )  # operatorul citește (fără clienți alocați: lista goală)
    r = client.post(f"/creier/fapte/{iid}/aproba", data={"versiune": "1", "csrf_token": csrf(client)})
    assert r.status_code == 403 and in_context(tenant) == []  # nu are `creier.editeaza`


def test_un_client_nu_vede_ecranul_agentiei(client: TestClient, fabrica_conturi: Fabrica) -> None:
    titular = fabrica_conturi(Rol.CLIENT_TITULAR)
    from tests.integration.conftest import login

    login(client, titular.email, titular.parola)
    assert client.get("/creier/fapte", follow_redirects=False).status_code in (303, 403)
