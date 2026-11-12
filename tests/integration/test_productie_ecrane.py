"""F2.9 — ecranele Producție și Operare: lista cu filtre, „urma” unui livrabil (mutări cu refuzuri, pașii fluxului
durabil, aprobări, efecte), reluarea unui pas eșuat și a unui livrabil din panou, anularea, starea motorului.

Fluxul de probă și conectorul sunt SIMULATE (`tests/integration/fluxuri_livrabil.py`, `tests/conector_fals.py`)."""

import re
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app import productie
from app.connectors import registru
from app.conturi import Rol
from app.db import sesiune_agentie, sesiune_tenant
from app.ids import new_id
from app.operare import coada_erori, efecte, motor, opriri
from app.operare.opriri import Oprire
from app.productie import Hotarare, aprobari
from app.productie.stari import Stare
from tests.conector_fals import ConectorFals
from tests.integration import fluxuri_livrabil as proba
from tests.integration.conftest import Cont, login
from tests.integration.utile_panou import autentifica, csrf
from tests.integration.utile_productie import (
    livrabil,
    livrabil_in_publicare,
    muta,
    stare,
)

pytestmark = pytest.mark.db
Fabrica = Callable[..., Cont]


@pytest.fixture
def proprietar(client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]) -> Cont:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    return cont


@pytest.fixture
def platforma(tmp_path: Path) -> Iterator[ConectorFals]:
    registru.uita_tot()
    fals = ConectorFals(tmp_path)
    registru.inregistreaza("fals", fals)
    yield fals
    registru.uita_tot()


@pytest.fixture(autouse=True)
def _curat(admin_engine: Engine) -> Iterator[None]:
    with admin_engine.begin() as c:
        c.execute(text("TRUNCATE opriri, efecte_de_trimis, conectori_pauze"))
        c.execute(text("UPDATE aprobari SET stare = 'anulat', decis_la = now() WHERE stare = 'in_asteptare'"))
    proba.FRAGIL["esueaza"] = False
    proba.APELURI_FRAGIL.clear()
    yield


def audit(admin: Engine, actiune: str, obiect: object) -> list[dict[str, object]]:
    with admin.connect() as c:
        return [
            dict(r._mapping)
            for r in c.execute(
                text(
                    "SELECT utilizator_id, tenant_id, detalii FROM jurnal_audit WHERE actiune = :a AND obiect_id = :o"
                ),
                {"a": actiune, "o": str(obiect)},
            )
        ]


def alege_clientul(client: TestClient, tenant: uuid.UUID) -> None:
    r = client.post(
        "/conturi/client-activ",
        data={"tenant_id": str(tenant), "csrf_token": csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code in (200, 303)


# --- lista ------------------------------------------------------------------------------------------------------------


def test_lista_filtreaza_pe_client_stare_si_exceptii_si_se_pagineaza(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, fabrica_clienti: Callable[[], uuid.UUID]
) -> None:
    alt_client = fabrica_clienti()
    ids = [livrabil(tenant, tip="postare") for _ in range(23)]
    la_om = livrabil(tenant, tip="video")
    muta(tenant, la_om, Stare.PLANIFICAT, Stare.BRIEFAT)
    muta(tenant, la_om, Stare.BRIEFAT, Stare.COADA_DE_ERORI)
    livrabil(alt_client, tip="articol")

    pag1 = client.get(f"/productie?client={tenant}").text
    assert pag1.count('aria-labelledby="l-') == 20 and "Mai departe" in pag1 and "Înapoi" not in pag1
    pag2 = client.get(f"/productie?client={tenant}&pagina=2").text
    assert pag2.count('aria-labelledby="l-') == 4 and "Înapoi" in pag2 and "Mai departe" not in pag2
    vazute = set(re.findall(r'href="/productie/([0-9a-f-]{36})"', pag1 + pag2))
    assert vazute == {str(i) for i in ids} | {str(la_om)}, "paginile acoperă tot, fără dubluri sau lipsuri"

    exceptii = client.get(f"/productie?client={tenant}&exceptii=1").text
    assert f"/productie/{la_om}" in exceptii and exceptii.count('aria-labelledby="l-') == 1
    assert "Coada de erori" in exceptii
    doar_planificate = client.get(f"/productie?client={tenant}&stare=planificat").text
    assert f"/productie/{la_om}" not in doar_planificate and "articol" not in doar_planificate
    assert "articol" in client.get(f"/productie?client={alt_client}").text
    gol = client.get(f"/productie?client={alt_client}&stare=inchis").text
    assert "Niciun livrabil pentru filtrele alese" in gol
    assert client.get("/productie?stare=inexistenta").status_code == 422
    assert client.get("/productie?client=nu-e-uuid").status_code == 422
    assert client.get("/productie?pagina=0").status_code == 422
    assert 'name="stare"' in pag1 and 'name="client"' in pag1 and 'name="exceptii"' in pag1


# --- urma unui livrabil de probă ----------------------------------------------------------------------------------------


def ruleaza_proba(tenant: uuid.UUID, lid: uuid.UUID, cheie: str, scenariu: str = "ok") -> str:
    job = motor.trimite(proba.proba, str(tenant), str(lid), scenariu, cheie=cheie)
    rez = motor.asteapta_flux(job, timeout_sec=60)
    assert rez.stare is motor.StareJob.TERMINAT, rez.eroare
    return job


def test_urma_arata_fiecare_pas_al_unui_livrabil_de_proba(
    executor: None,
    client: TestClient,
    proprietar: Cont,
    tenant: uuid.UUID,
    om: uuid.UUID,
    platforma: ConectorFals,
) -> None:
    lid = livrabil(tenant, canal="fals")
    job = ruleaza_proba(tenant, lid, f"urma-1-{lid}")  # se oprește la „așteaptă aprobare” (L1)
    assert stare(tenant, lid) == Stare.ASTEAPTA_APROBARE
    with pytest.raises(productie.TranzitieNepermisa):
        muta(tenant, lid, Stare.ASTEAPTA_APROBARE, Stare.PUBLICAT)  # refuzată și înregistrată
    with sesiune_tenant(tenant) as db:
        cerere = aprobari.cerere_activa(db, lid)
        assert cerere is not None
        aprobari.decide(db, cerere.id, Hotarare.APROBAT, utilizator_id=om, rol=Rol.PROPRIETAR, versiune=1)
    ruleaza_proba(tenant, lid, f"urma-2-{lid}")
    assert stare(tenant, lid) == Stare.INCHIS

    r = client.get(f"/productie/{lid}")
    assert r.status_code == 200
    h = r.text
    # mutările: toate stările normale, în ordine, plus refuzul
    pozitii = [h.rindex(f"→ {eticheta}") for eticheta in (
        "Briefat", "În scriere", "În validare", "Validat", "Așteaptă aprobare", "Aprobat", "Programat",
        "În publicare", "Publicat", "În măsurare", "Închis",
    )]  # fmt: skip
    assert pozitii == sorted(pozitii)
    assert "refuzată" in h
    # pașii fluxului durabil: numele, starea, durata, joburile (două rulări ale fluxului de probă)
    assert "proba.livrabil" in h and h.count("proba.livrabil") >= 2 and job in h
    assert "tests.integration.fluxuri_livrabil.avanseaza" in h and "ms" in h
    assert "terminat" in h
    # cererea de aprobare, efectul extern și contoarele
    assert "Versiunea 1" in h and "aprobat" in h
    assert "publicare pe fals" in h and "fals-1" in h and "https://platforma.exemplu.test/post/1" in h
    assert "Runde de reparație" in h and "0 / 2" in h
    # fiecare pas apare ca rând de tabel
    assert re.search(r"<td><code>tests\.integration\.fluxuri_livrabil\.avanseaza</code></td>", h)


def test_urma_arata_efectul_oprit_si_canalul_pe_pauza(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    with sesiune_tenant(tenant) as db:
        e = efecte.cere(db, lid, porneste=False).efect
    with sesiune_agentie() as db:
        opriri.seteaza(db, Oprire.PUBLICARE, True, canal="sistem", motiv="test")
    assert efecte.incearca_efect(tenant, e.id) == "oprit"
    h = client.get(f"/productie/{lid}").text
    assert "publicare pe fals" in h and "oprit: publicarea (global)" in h and "în_asteptare" not in h
    assert 'class="insigna ' in h and "În așteptare" in h
    # pe Operare: efectul oprit, întrerupătorul și opririle (cu legătură spre butoanele de pe Acasă)
    m = client.get("/operare/motor").text
    assert "În așteptare: 1" in m and f"/productie/{lid}" in m and "oprit: publicarea (global)" in m
    assert "Publicarea (global)" in m and 'href="/"' in m


def test_motorul_arata_workerul_cozile_si_programarile(
    executor: None, client: TestClient, proprietar: Cont, tenant: uuid.UUID
) -> None:
    from app.productie import fluxuri

    fluxuri.declara_programari()
    motor.aplica_programari()
    h = client.get("/operare/motor").text
    for coada in ("urgent", "greu", "io", "invatare"):
        assert f"<code>{coada}</code>" in h
    assert "2 în paralel" in h and "24 în paralel" in h
    assert "productie.tic" in h and "activă" in h
    assert 'hx-get="/operare/motor/fragment"' in h
    frag = client.get("/operare/motor/fragment")
    assert frag.status_code == 200 and "<html" not in frag.text and "Worker și cozi" in frag.text
    assert "Nicio oprire activă" in h or "oprit" in h


def test_adancimea_cozii_numara_ce_asteapta_si_ce_ruleaza(
    motor_curat: None, client: TestClient, proprietar: Cont
) -> None:
    # fără executor: joburile rămân în coadă
    for _i in range(3):
        motor.trimite(
            proba.fragil,
            str(uuid.uuid4()),
            str(uuid.uuid4()),
            coada=motor.Coada.GREU,
            cheie=f"ad-{uuid.uuid4()}",
        )
    h = client.get("/operare/motor").text
    m = re.search(r"<code>greu</code></td><td>(\d+)</td><td>(\d+)</td>", h)
    assert m and (int(m.group(1)), int(m.group(2))) == (3, 0)


def test_programarea_se_pune_pe_pauza_se_reia_si_ruleaza_acum_cu_csrf_si_audit(
    executor: None, client: TestClient, proprietar: Cont, admin_engine: Engine
) -> None:
    from app.productie import fluxuri

    fluxuri.declara_programari()
    motor.aplica_programari()
    nume = fluxuri.NUME_TIC
    cale = f"/operare/motor/programari/{nume}"
    assert client.post(f"{cale}/pauza", data={"csrf_token": "gresit"}).status_code == 403
    assert client.post(f"{cale}/pauza").status_code == 403
    r = client.post(f"{cale}/pauza", data={"csrf_token": csrf(client)}, follow_redirects=False)
    assert r.status_code == 303
    [p] = [p for p in motor.lista_programari() if p.nume == nume]
    assert p.stare == "pe_pauza" and "pe pauză" in client.get("/operare/motor").text
    assert (
        client.post(f"{cale}/reia", data={"csrf_token": csrf(client)}, follow_redirects=False).status_code
        == 303
    )
    [p] = [p for p in motor.lista_programari() if p.nume == nume]
    assert p.stare == "activa"
    r = client.post(f"{cale}/ruleaza", data={"csrf_token": csrf(client)}, follow_redirects=False)
    assert r.status_code == 303
    [a] = audit(admin_engine, "programare.ruleaza", nume)
    assert a["utilizator_id"] == proprietar.id and a["detalii"]["job"]  # type: ignore[index]
    motor.asteapta_flux(str(a["detalii"]["job"]), timeout_sec=30)  # type: ignore[index]
    assert audit(admin_engine, "programare.pauza", nume) and audit(admin_engine, "programare.reia", nume)
    assert (
        client.post(
            "/operare/motor/programari/inexistenta/pauza", data={"csrf_token": csrf(client)}
        ).status_code
        == 404
    )
    assert client.post(f"{cale}/sterge", data={"csrf_token": csrf(client)}).status_code == 422


def test_operatorul_vede_motorul_dar_nu_poate_actiona_asupra_programarilor(
    client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]
) -> None:
    operator = fabrica_conturi(Rol.OPERATOR, cu_totp=True)
    autentifica(client, operator, ceas)
    h = client.get("/operare/motor")
    assert h.status_code == 200 and "Doar proprietarul poate pune pe pauză" in h.text
    r = client.post("/operare/motor/programari/productie.tic/pauza", data={"csrf_token": csrf(client)})
    assert r.status_code == 403


@pytest.mark.parametrize("rol", [Rol.CLIENT_TITULAR, Rol.CLIENT_APROBATOR, Rol.CLIENT_VIZITATOR])
def test_clientii_nu_au_acces_la_ecranele_noi(client: TestClient, fabrica_conturi: Fabrica, rol: Rol) -> None:
    cont = fabrica_conturi(rol)
    login(client, cont.email, cont.parola)
    for cale in ("/productie", f"/productie/{uuid.uuid4()}", "/operare/motor", "/operare/motor/fragment"):
        assert client.get(cale).status_code == 403, cale
    assert client.post(f"/productie/{uuid.uuid4()}/anuleaza", data={"motiv": "xxx"}).status_code == 403


def test_pe_telefon_ecranele_au_navigare_csp_strict_si_nu_au_stiluri_sau_scripturi_inline(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID
) -> None:
    lid = livrabil(tenant)
    for cale in ("/productie", f"/productie/{lid}", "/operare/motor"):
        r = client.get(cale)
        assert r.status_code == 200
        assert 'name="viewport"' in r.text and 'class="bara-jos"' in r.text
        assert "style=" not in r.text and "<script>" not in r.text and "onclick=" not in r.text
        assert "script-src 'self'" in r.headers["content-security-policy"]
    assert 'href="/operare/motor"' in client.get("/meniu").text


# --- reluarea unui pas eșuat ----------------------------------------------------------------------------------------------


def job_nou(lid: uuid.UUID, ca_fork_din: str) -> motor.DetaliiJob | None:
    return next((j for j in motor.joburi_pentru([str(lid)]) if j.bifurcat_din == ca_fork_din), None)


def test_se_poate_relua_din_panou_un_pas_esuat(
    executor: None, client: TestClient, proprietar: Cont, tenant: uuid.UUID, admin_engine: Engine
) -> None:
    from tests.chaos.utile import asteapta

    lid = livrabil(tenant)
    proba.FRAGIL["esueaza"] = True
    job = motor.trimite(proba.fragil, str(tenant), str(lid), cheie=f"fragil-{lid}")
    assert motor.asteapta_flux(job, timeout_sec=30).stare is motor.StareJob.ESUAT

    h = client.get(f"/productie/{lid}").text
    assert "eșuat" in h and "proba.fragil_b" in h and "SIMULAT: pasul B a căzut" in h
    assert "Reia pasul eșuat" in h and f'name="job" value="{job}"' in h
    assert [p for p in h.split("<tr>") if "proba.fragil_b" in p and "pericol" in p], "pasul eșuat e marcat"

    # fără motiv: refuzat; fără CSRF: 403
    assert client.post(f"/productie/{lid}/reia", data={"ce": "job", "job": job}).status_code == 403
    r = client.post(
        f"/productie/{lid}/reia", data={"ce": "job", "job": job, "motiv": " ", "csrf_token": csrf(client)}
    )
    assert r.status_code == 422 and "motivul reluării" in r.text
    assert motor.stare_flux(job).stare is motor.StareJob.ESUAT  # type: ignore[union-attr]

    proba.FRAGIL["esueaza"] = False  # cauza s-a reparat
    r = client.post(
        f"/productie/{lid}/reia",
        data={"ce": "job", "job": job, "motiv": "am reparat pasul B", "csrf_token": csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == f"/productie/{lid}?mesaj=pas_reluat"
    asteapta(
        lambda: (j := job_nou(lid, job)) is not None and j.stare is motor.StareJob.TERMINAT,
        timeout_sec=30,
        mesaj="jobul reluat",
    )
    assert proba.APELURI_FRAGIL == ["a", "b", "b", "c"], "pasul A nu se repetă, B se reia, C rulează"
    [a] = audit(admin_engine, "livrabil.pas_reluat", lid)
    assert a["utilizator_id"] == proprietar.id and a["tenant_id"] == tenant
    assert a["detalii"]["job"] == job and a["detalii"]["motiv"] == "am reparat pasul B"  # type: ignore[index]
    # jobul vechi a fost reluat: nu se mai oferă a doua oară
    assert "Reia pasul eșuat" not in client.get(f"/productie/{lid}").text
    r = client.post(
        f"/productie/{lid}/reia",
        data={"ce": "job", "job": job, "motiv": "încă o dată", "csrf_token": csrf(client)},
    )
    assert r.status_code == 409


def test_nu_se_poate_relua_jobul_altui_livrabil(
    executor: None, client: TestClient, proprietar: Cont, tenant: uuid.UUID
) -> None:
    alt = livrabil(tenant)
    lid = livrabil(tenant)
    proba.FRAGIL["esueaza"] = True
    job_altul = motor.trimite(proba.fragil, str(tenant), str(alt), cheie=f"fragil-{alt}")
    motor.asteapta_flux(job_altul, timeout_sec=30)
    r = client.post(
        f"/productie/{lid}/reia",
        data={"ce": "job", "job": job_altul, "motiv": "încerc", "csrf_token": csrf(client)},
    )
    assert r.status_code == 409 and "Nu există un pas eșuat de reluat" in r.text
    assert motor.stare_flux(job_altul).stare is motor.StareJob.ESUAT  # type: ignore[union-attr]


def livrabil_oprit_la_limita(tenant: uuid.UUID) -> uuid.UUID:
    lid = livrabil(tenant)
    curenta = Stare.PLANIFICAT
    for s in (Stare.BRIEFAT, Stare.IN_SCRIERE, Stare.IN_VALIDARE):
        muta(tenant, lid, curenta, s)
        curenta = s
    for _ in range(2):
        muta(tenant, lid, Stare.IN_VALIDARE, Stare.IN_REPARATIE)
        muta(tenant, lid, Stare.IN_REPARATIE, Stare.IN_VALIDARE)
    muta(tenant, lid, Stare.IN_VALIDARE, Stare.IN_REPARATIE, detalii={"verdict": "ton nepotrivit"})
    return lid


def test_omul_reia_din_panou_un_livrabil_oprit_la_limita(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, admin_engine: Engine
) -> None:
    lid = livrabil_oprit_la_limita(tenant)
    assert stare(tenant, lid) == Stare.COADA_DE_ERORI
    h = client.get(f"/productie/{lid}").text
    assert "Reia livrabilul" in h and "limită depășită" in h
    r = client.post(
        f"/productie/{lid}/reia", data={"ce": "livrabil", "motiv": "x", "csrf_token": csrf(client)}
    )
    assert r.status_code == 422 and stare(tenant, lid) == Stare.COADA_DE_ERORI
    r = client.post(
        f"/productie/{lid}/reia",
        data={"ce": "livrabil", "motiv": "am schimbat promptul", "csrf_token": csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert stare(tenant, lid) == Stare.IN_VALIDARE
    with sesiune_tenant(tenant) as db:
        assert list(coada_erori.lista(db)) == [], "intrarea din coada de erori s-a închis"
    [a] = audit(admin_engine, "livrabil.reluat_de_om", lid)
    assert a["utilizator_id"] == proprietar.id
    # a doua reluare nu mai are ce relua
    r = client.post(
        f"/productie/{lid}/reia", data={"ce": "livrabil", "motiv": "încă o dată", "csrf_token": csrf(client)}
    )
    assert r.status_code == 409


def test_efectul_extern_esuat_se_reia_odata_cu_livrabilul(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    with sesiune_tenant(tenant) as db:
        e = efecte.cere(db, lid, porneste=False).efect
    platforma.scenariu(trimite=["definitiv"])
    assert efecte.incearca_efect(tenant, e.id) == "esuat"
    assert stare(tenant, lid) == Stare.COADA_DE_ERORI
    h = client.get(f"/productie/{lid}").text
    assert "EroareDefinitiva" in h and "Reia livrabilul" in h and "Eșuat" in h
    with sesiune_tenant(tenant) as db:
        [intrare] = coada_erori.lista(db)
    alerta = client.get(f"/alerte/{intrare.id}").text
    assert "Diagnostic: efect extern eșuat" in alerta and f"/productie/{lid}" in alerta
    assert f'action="/alerte/{intrare.id}/reia"' not in alerta, "se reia din Producție"
    assert client.post(f"/alerte/{intrare.id}/reia", data={"csrf_token": csrf(client)}).status_code == 409
    r = client.post(
        f"/productie/{lid}/reia",
        data={"ce": "livrabil", "motiv": "platforma a fost reparată", "csrf_token": csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code == 303 and stare(tenant, lid) == Stare.IN_PUBLICARE
    assert efecte.incearca_efect(tenant, e.id) == "trimis"
    assert len(platforma.postari()) == 1 and stare(tenant, lid) == Stare.PUBLICAT


# --- anularea ----------------------------------------------------------------------------------------------------------------


def test_anularea_cere_motiv_csrf_permisiune_si_se_audita(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, admin_engine: Engine
) -> None:
    lid = livrabil(tenant)
    muta(tenant, lid, Stare.PLANIFICAT, Stare.BRIEFAT)
    assert "Anulează livrabilul" in client.get(f"/productie/{lid}").text
    assert client.post(f"/productie/{lid}/anuleaza", data={"motiv": "clientul a renunțat"}).status_code == 403
    r = client.post(f"/productie/{lid}/anuleaza", data={"motiv": "", "csrf_token": csrf(client)})
    assert r.status_code == 422 and stare(tenant, lid) == Stare.BRIEFAT
    r = client.post(
        f"/productie/{lid}/anuleaza",
        data={"motiv": "clientul a renunțat", "csrf_token": csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code == 303 and stare(tenant, lid) == Stare.ANULAT
    [a] = audit(admin_engine, "livrabil.anulat_de_om", lid)
    assert (a["utilizator_id"], a["tenant_id"]) == (proprietar.id, tenant)
    assert "Anulează livrabilul" not in client.get(f"/productie/{lid}").text
    r = client.post(f"/productie/{lid}/anuleaza", data={"motiv": "încă o dată", "csrf_token": csrf(client)})
    assert r.status_code == 409


def test_un_livrabil_in_publicare_nu_se_anuleaza_si_unul_cu_cerere_si_efect_da(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID, om: uuid.UUID, platforma: ConectorFals
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    r = client.post(
        f"/productie/{lid}/anuleaza", data={"motiv": "vreau să-l opresc", "csrf_token": csrf(client)}
    )
    assert (
        r.status_code == 409 and "nu se mai anulează" in r.text and stare(tenant, lid) == Stare.IN_PUBLICARE
    )
    # un livrabil căzut în coada de erori după un efect eșuat: anularea anulează și efectul
    with sesiune_tenant(tenant) as db:
        e = efecte.cere(db, lid, porneste=False).efect
    platforma.scenariu(trimite=["definitiv"])
    efecte.incearca_efect(tenant, e.id)
    r = client.post(
        f"/productie/{lid}/anuleaza",
        data={"motiv": "renunțăm", "csrf_token": csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code == 303 and stare(tenant, lid) == Stare.ANULAT
    with sesiune_tenant(tenant) as db:
        efect = efecte.citeste(db, e.id)
        assert efect is not None and efect.stare == "anulat"


def test_anularea_scoate_cererea_de_aprobare_din_lista(
    client: TestClient, proprietar: Cont, tenant: uuid.UUID
) -> None:
    lid = livrabil(tenant)
    for s, la in (
        (Stare.PLANIFICAT, Stare.BRIEFAT),
        (Stare.BRIEFAT, Stare.IN_SCRIERE),
        (Stare.IN_SCRIERE, Stare.IN_VALIDARE),
        (Stare.IN_VALIDARE, Stare.VALIDAT),
    ):
        muta(tenant, lid, s, la)
    with sesiune_tenant(tenant) as db:
        ap = aprobari.cere(db, lid)
    assert str(ap.id) in client.get("/aprobari").text
    r = client.post(
        f"/productie/{lid}/anuleaza",
        data={"motiv": "nu mai e nevoie", "csrf_token": csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code == 303 and str(ap.id) not in client.get("/aprobari").text


# --- izolarea pe client --------------------------------------------------------------------------------------------------------


def test_operatorul_vede_si_actioneaza_doar_asupra_clientului_alocat(
    client: TestClient,
    fabrica_conturi: Fabrica,
    ceas: dict[str, float],
    tenant: uuid.UUID,
    fabrica_clienti: Callable[[], uuid.UUID],
    admin_engine: Engine,
) -> None:
    alt_client = fabrica_clienti()
    al_lui = livrabil(tenant, tip="postare")
    al_altuia = livrabil(alt_client, tip="articol")
    operator = fabrica_conturi(Rol.OPERATOR, cu_totp=True)
    with admin_engine.begin() as c:
        c.execute(
            text("INSERT INTO alocari (id, utilizator_id, tenant_id) VALUES (:i, :u, :t)"),
            {"i": new_id(), "u": operator.id, "t": tenant},
        )
    autentifica(client, operator, ceas)
    assert str(al_lui) not in client.get("/productie").text, "fără client ales, operatorul nu vede nimic"
    alege_clientul(client, tenant)
    lista = client.get("/productie").text
    assert f"/productie/{al_lui}" in lista and f"/productie/{al_altuia}" not in lista
    assert client.get(f"/productie/{al_lui}").status_code == 200
    assert client.get(f"/productie/{al_altuia}").status_code == 404
    jeton = csrf(client)
    assert (
        client.post(
            f"/productie/{al_altuia}/anuleaza", data={"motiv": "încerc", "csrf_token": jeton}
        ).status_code
        == 404
    )
    assert stare(alt_client, al_altuia) == Stare.PLANIFICAT
    assert client.get(f"/productie?client={alt_client}").text.count('aria-labelledby="l-') == 0
    assert (
        client.post(
            f"/productie/{al_lui}/anuleaza",
            data={"motiv": "nu mai e nevoie", "csrf_token": jeton},
            follow_redirects=False,
        ).status_code
        == 303
    )


def test_analistul_citeste_dar_nu_poate_relua_sau_anula(
    client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float], tenant: uuid.UUID
) -> None:
    lid = livrabil(tenant)
    analist = fabrica_conturi(Rol.ANALIST, cu_totp=True)
    autentifica(client, analist, ceas)
    assert client.get("/productie").status_code == 200
    jeton = csrf(client)
    for actiune, date in (("anuleaza", {"motiv": "xxx"}), ("reia", {"ce": "livrabil", "motiv": "xxx"})):
        assert (
            client.post(f"/productie/{lid}/{actiune}", data={**date, "csrf_token": jeton}).status_code == 403
        )
    assert stare(tenant, lid) == Stare.PLANIFICAT


def test_reautorizarea_conectorului_din_operare(
    client: TestClient,
    proprietar: Cont,
    tenant: uuid.UUID,
    om: uuid.UUID,
    platforma: ConectorFals,
    admin_engine: Engine,
) -> None:
    lid = livrabil_in_publicare(tenant, om)
    with sesiune_tenant(tenant) as db:
        e = efecte.cere(db, lid, porneste=False).efect
    platforma.scenariu(trimite=["autentificare"])
    assert efecte.incearca_efect(tenant, e.id) == "autentificare"
    h = client.get("/operare/motor").text
    assert "pe pauză: cere reautorizare" in h and "Reautorizat, reia" in h
    date = {"tenant_id": str(tenant), "canal": "fals"}
    assert client.post("/operare/motor/conectori/reia", data=date).status_code == 403
    r = client.post(
        "/operare/motor/conectori/reia", data={**date, "csrf_token": csrf(client)}, follow_redirects=False
    )
    assert r.status_code == 303 and "pe pauză" not in client.get("/operare/motor").text
    assert audit(admin_engine, "conector.reautorizat", f"{tenant}:fals")
    r = client.post("/operare/motor/conectori/reia", data={**date, "csrf_token": csrf(client)})
    assert r.status_code == 404
    assert efecte.incearca_efect(tenant, e.id) == "trimis"
