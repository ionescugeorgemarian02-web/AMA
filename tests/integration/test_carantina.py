"""F5.10 — carantina și contestațiile. „Gata când”: un verdict contestat ajunge în setul de aur (exemplu
propus → promovat
de un om → inclus în rularea bancului); lanțul complet, prin ecranele din panou (CSRF, permisiune, audit)."""

# ruff: noqa: F811
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app import productie
from app.conturi import Rol
from app.db import sesiune_agentie, sesiune_tenant
from app.productie import Stare
from app.validare import banc, carantina, exemple
from tests.integration.conftest import Cont
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import fabrica_clienti, om, tenant  # noqa: F401
from tests.validare_utile import livrabil_in_validare, registru_doar, ruleaza, verdicte

pytestmark = pytest.mark.db
POLITIC = "Votează pentru candidatul nostru la primărie, duminică, și vino la cafeaua de după."


def in_carantina(tenant: uuid.UUID) -> uuid.UUID:
    with registru_doar("G3"):
        lid = livrabil_in_validare(tenant, POLITIC)
        r = ruleaza(tenant, lid)
    assert r.stare is Stare.CARANTINA
    return lid


@pytest.fixture
def proprietar(client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float]) -> Cont:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    return cont


def _stare(tenant: uuid.UUID, lid: uuid.UUID) -> str:
    with sesiune_tenant(tenant) as db:
        lv = productie.citeste(db, lid)
        assert lv is not None
        return lv.stare


def test_carantina_arata_dovezile_si_iese_doar_prin_decizie_umana(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, admin_engine: Engine, om: uuid.UUID
) -> None:
    lid, lid2 = in_carantina(tenant), in_carantina(tenant)
    lista = client.get("/validatoare/carantina").text
    assert f"/validatoare/carantina/{lid}" in lista and "pol-continut-politic" in lista
    detaliu = client.get(f"/validatoare/carantina/{lid}").text
    assert "Votează pentru" in detaliu and "De ce a fost blocat" in detaliu and "Contestă" in detaliu
    cale = f"/validatoare/carantina/{lid}/elibereaza"
    assert client.post(cale, data={"spre": "reparatie", "motiv": "regula aplicată greșit"}).status_code == 403
    jeton = csrf(client, f"/validatoare/carantina/{lid}")
    r = client.post(
        cale, data={"csrf_token": jeton, "spre": "reparatie", "motiv": ""}, follow_redirects=False
    )
    assert "eroare=" in r.headers["location"] and _stare(tenant, lid) == "carantina", "fără motiv nu iese"
    r = client.post(cale, data={"csrf_token": jeton, "spre": "publicare", "motiv": "vreau să public"})
    assert _stare(tenant, lid) == "carantina", "nu există drum spre publicare"
    r = client.post(
        cale,
        data={"csrf_token": jeton, "spre": "reparatie", "motiv": "autorul scoate apelul la vot"},
        follow_redirects=False,
    )
    assert r.headers["location"].endswith("mesaj=eliberat") and _stare(tenant, lid) == "in_reparatie"
    r = client.post(
        f"/validatoare/carantina/{lid2}/respinge",
        data={"csrf_token": jeton, "motiv": "conținut politic, refuzat"},
    )
    assert _stare(tenant, lid2) == "anulat"
    with admin_engine.connect() as c:
        tr = c.execute(
            text(
                "SELECT utilizator_id, motiv FROM livrabile_tranzitii WHERE livrabil_id = :l AND din = 'carantina' AND rezultat = 'aplicata'"
            ),
            {"l": lid},
        ).one()
        audit = (
            c.execute(
                text(
                    "SELECT actiune FROM jurnal_audit WHERE utilizator_id = :u AND actiune LIKE 'carantina.%'"
                ),
                {"u": proprietar.id},
            )
            .scalars()
            .all()
        )
    assert tuple(tr) == (proprietar.id, "autorul scoate apelul la vot")
    assert sorted(audit) == ["carantina.eliberare", "carantina.respingere"]
    # nici din cod, nici cu un om, carantina nu duce direct la aprobare / publicare
    lid3 = in_carantina(tenant)
    with sesiune_tenant(tenant) as db, pytest.raises(productie.TranzitieNepermisa):
        productie.muta(db, lid3, Stare.CARANTINA, Stare.ASTEAPTA_APROBARE, componenta="om", utilizator_id=om)
    with sesiune_tenant(tenant) as db, pytest.raises(productie.TranzitieNepermisa):
        productie.muta(db, lid3, Stare.CARANTINA, Stare.IN_VALIDARE, componenta="G1")  # fără om


def test_eliberarea_in_validare_repune_livrabilul_in_cascada(tenant: uuid.UUID, om: uuid.UUID) -> None:
    lid = in_carantina(tenant)
    with sesiune_tenant(tenant, om) as db:
        carantina.elibereaza(
            db, lid, spre="validare", motiv="regula de nișă s-a actualizat", utilizator_id=om
        )
    assert _stare(tenant, lid) == "in_validare"
    with sesiune_tenant(tenant, om) as db, pytest.raises(carantina.DecizieInvalida):
        carantina.respinge_definitiv(db, lid, motiv="x", utilizator_id=om)


def test_verdictul_contestat_ajunge_in_setul_de_aur_si_in_rularea_bancului(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, admin_engine: Engine
) -> None:
    lid = in_carantina(tenant)
    [v] = [x for x in verdicte(tenant, lid) if x.validator == "G3"]
    pagina_v = client.get(f"/validatoare/verdicte/{v.id}").text
    assert "Verdict greșit" in pagina_v
    jeton = csrf(client, f"/validatoare/verdicte/{v.id}")
    cale = f"/validatoare/verdicte/{v.id}/contesta"
    assert client.post(cale, data={"motiv": "nu e politic"}).status_code == 403
    r = client.post(cale, data={"csrf_token": jeton, "motiv": "e un concurs de vot pe meniu, nu politică"})
    assert r.status_code == 200 and "Contestația a fost înregistrată" in r.text
    # contestația intră în statistica validatorului
    with sesiune_agentie() as db:
        st = carantina.statistica_contestatii(db)["G3"]
        [propus] = [e for e in exemple.listeaza(db) if e.verdict_id == v.id]
    assert st["contestate"] >= 1 and propus.sursa == "contestatie" and propus.asteptat == "trece"
    assert POLITIC in propus.text
    # promovat de un om (cu text anonimizat, eticheta păstrată), prin ecranul de exemple
    ex = client.get("/validatoare/exemple").text
    assert f"/validatoare/exemple/{propus.id}/promoveaza" in ex
    text_anonim = "Votează meniul de toamnă: alegi tu ce cafea intră duminică în ofertă."
    r = client.post(
        f"/validatoare/exemple/{propus.id}/promoveaza",
        data={
            "csrf_token": csrf(client, "/validatoare/exemple"),
            "context_profil": "gol",
            "text": text_anonim,
        },
    )
    assert "Exemplul a intrat în setul de aur" in r.text
    with admin_engine.connect() as c:
        stare, decis_de = c.execute(
            text("SELECT stare, decis_de FROM exemple_propuse WHERE id = :i"), {"i": propus.id}
        ).one()
    assert (stare, decis_de) == ("promovat", proprietar.id)
    # rularea bancului (jobul durabil, aceeași funcție) include exemplul promovat
    with sesiune_agentie() as db:
        rid = banc.depozit.porneste(db, utilizator_id=proprietar.id).id
    assert banc.fluxuri.ruleaza_si_salveaza(rid) == "terminat"
    with sesiune_agentie() as db:
        sc = banc.depozit.citeste(db, rid).scoruri  # type: ignore[union-attr]
    g3 = sc["validatori"]["G3"]
    assert g3["promovate"] >= 1
    assert g3["exemple"] == len(banc.seturi.incarca().aur["G3"]) + g3["promovate"]


def test_analistul_nu_decide_in_carantina(
    client: TestClient, fabrica_conturi: Callable[..., Cont], ceas: dict[str, float], tenant: uuid.UUID
) -> None:
    lid = in_carantina(tenant)
    analist = fabrica_conturi(Rol.ANALIST, cu_totp=True)
    autentifica(client, analist, ceas)
    r = client.post(
        f"/validatoare/carantina/{lid}/respinge",
        data={"csrf_token": csrf(client), "motiv": "nu are drept aici"},
    )
    assert r.status_code == 403 and _stare(tenant, lid) == "carantina"
    assert client.get("/validatoare/exemple").status_code == 403
