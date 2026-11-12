"""F1.8/F1.9, partea din panou — rutele interne de livrare, ecranul Operare, starea backup-ului."""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.conturi import Rol
from tests.integration.conftest import Cont
from tests.integration.utile_panou import TOKEN_LIVRARE, autentifica, csrf

pytestmark = pytest.mark.db

Fabrica = Callable[..., Cont]
ANTET = {"X-Livrare-Token": TOKEN_LIVRARE}
IMG1 = "ghcr.io/exemplu/ama@sha256:" + "1" * 64
IMG2 = "ghcr.io/exemplu/ama@sha256:" + "2" * 64
IMG3 = "ghcr.io/exemplu/ama@sha256:" + "3" * 64


def randuri(admin: Engine, sql: str, **p: object) -> list[dict[str, Any]]:
    with admin.connect() as c:
        return [dict(r._mapping) for r in c.execute(text(sql), p)]


@pytest.fixture
def cu_jeton(config: Callable[..., None]) -> None:
    config(deploy_token=TOKEN_LIVRARE)


@pytest.fixture
def proprietar(client: TestClient, fabrica_conturi: Fabrica, ceas: dict[str, float]) -> Cont:
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)
    autentifica(client, cont, ceas)
    return cont


def raport(
    mediu: str, stare: str, imagine: str | None, cerere_id: str | None = None, **extra: Any
) -> dict[str, Any]:
    """Raportul exact cum îl construiește `build_report` din deployer."""
    return {
        "mediu": mediu,
        "stare": stare,
        "cerere_id": cerere_id,
        "imagine": imagine,
        "versiune": extra.pop("versiune", "sha-" + (imagine[-64:][:7] if imagine else "none")),
        "detalii": extra.pop("detalii", ""),
        "verificari": [{"nume": "healthz", "ok": True}, {"nume": "readyz", "ok": True}],
        "momentul": datetime.now(UTC).isoformat(timespec="seconds"),
        **extra,
    }


def post(client: TestClient, r: dict[str, Any]):  # type: ignore[no-untyped-def]
    return client.post("/intern/livrare/rezultat", json=r, headers=ANTET)


def cerere(client: TestClient) -> dict[str, Any] | None:
    r = client.get("/intern/livrare/cerere", headers=ANTET)
    assert r.status_code == 200
    return r.json()["cerere"]  # type: ignore[no-any-return]


def apasa(client: TestClient, actiune: str) -> Any:
    """Parcurge cele două trepte din panou: pagina de confirmare, apoi POST-ul."""
    cale = {"promovare": "/operare/promoveaza", "revenire": "/operare/revino"}[actiune]
    pagina = client.get(f"/operare/confirma?actiune={actiune}")
    assert pagina.status_code in (200, 409)
    return client.post(
        cale, data={"confirmare": "da", "csrf_token": csrf(client, "/operare")}, follow_redirects=False
    )


# ---- jetonul ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("metoda", "cale"), [("get", "/intern/livrare/cerere"), ("post", "/intern/livrare/rezultat")]
)
def test_fara_jeton_configurat_rutele_sunt_dezactivate_404(
    client: TestClient, metoda: str, cale: str
) -> None:
    r = getattr(client, metoda)(
        cale, headers=ANTET, **({"json": raport("staging", "reusita", IMG1)} if metoda == "post" else {})
    )
    assert r.status_code == 404


def test_jeton_prea_scurt_inseamna_dezactivat(client: TestClient, config: Callable[..., None]) -> None:
    config(deploy_token="scurt")
    assert client.get("/intern/livrare/cerere", headers={"X-Livrare-Token": "scurt"}).status_code == 404


@pytest.mark.parametrize(
    "antet",
    [
        {},
        {"X-Livrare-Token": ""},
        {"X-Livrare-Token": "x" * 40},
        {"X-Livrare-Token": TOKEN_LIVRARE[:-1]},
        {"X-Livrare-Token": TOKEN_LIVRARE + "x"},
    ],
)
def test_jeton_lipsa_sau_gresit_da_401_si_nu_scrie_nimic(
    client: TestClient, cu_jeton: None, antet: dict[str, str], admin_engine: Engine
) -> None:
    assert client.get("/intern/livrare/cerere", headers=antet).status_code == 401
    r = client.post("/intern/livrare/rezultat", json=raport("staging", "reusita", IMG1), headers=antet)
    assert r.status_code == 401
    assert randuri(admin_engine, "SELECT 1 FROM livrari") == []


def test_rutele_interne_nu_expun_altceva_si_nu_au_cookie_de_sesiune(
    client: TestClient, cu_jeton: None
) -> None:
    for cale in (
        "/intern",
        "/intern/",
        "/intern/livrare",
        "/intern/livrare/",
        "/intern/altceva",
        "/intern/livrare/istoric",
    ):
        assert client.get(cale, headers=ANTET).status_code == 404, cale
    assert cerere(client) is None
    r = client.get("/intern/livrare/cerere", headers=ANTET)
    assert set(r.json()) == {"cerere"} and r.headers["cache-control"] == "no-store"
    assert "set-cookie" not in r.headers


def test_corp_nevalid_este_respins(client: TestClient, cu_jeton: None) -> None:
    gresite = [
        raport("staging", "reusita", "imagine-fara-amprenta"),
        raport("altceva", "reusita", IMG1),
        raport("staging", "pornita", IMG1),
        raport("staging", "reusita", IMG1, detalii="x" * 501),
        raport("staging", "reusita", IMG1, cerere_id="nu-e-uuid"),
    ]
    for g in gresite:
        assert post(client, g).status_code == 422, g


# ---- fluxul complet ---------------------------------------------------------------------------------------


def test_promovare_cap_coada_cerere_preluare_in_curs_reusita(
    client: TestClient, cu_jeton: None, proprietar: Cont, admin_engine: Engine
) -> None:
    # 1. staging termină o implementare; deployer raportează fără cerere_id
    assert post(client, raport("staging", "in_curs", IMG1)).json() == {"ok": True}
    assert post(client, raport("staging", "reusita", IMG1, versiune="aaa1111")).json() == {"ok": True}
    assert cerere(client) is None
    html = client.get("/operare").text
    assert (
        "Promovează în producție" in html
        and "aaa1111" in html
        and "Revino la versiunea anterioară" not in html
    )

    # 2. proprietarul apasă (confirmare + CSRF), cererea apare pentru deployer
    r = apasa(client, "promovare")
    assert r.status_code == 303 and r.headers["location"] == "/operare?mesaj=promovare"
    c = cerere(client)
    assert c is not None and c["tip"] == "promovare" and c["imagine"] == IMG1 and c["versiune"] == "aaa1111"
    assert set(c) == {"id", "tip", "imagine", "versiune"}
    assert "Promovează în producție" not in client.get("/operare").text  # cerere în curs: butonul dispare
    assert apasa(client, "promovare").status_code == 409  # a doua cerere cât prima e activă

    # 3. deployer: in_curs → cererea se servește în continuare, apoi reusita → nu se mai servește
    assert post(client, raport("productie", "in_curs", IMG1, c["id"])).status_code == 200
    assert cerere(client)["id"] == c["id"]  # type: ignore[index]
    assert randuri(admin_engine, "SELECT stare FROM cereri_livrare")[0]["stare"] == "in_curs"
    assert post(client, raport("productie", "reusita", IMG1, c["id"], versiune="aaa1111")).status_code == 200
    assert cerere(client) is None
    assert randuri(admin_engine, "SELECT stare FROM cereri_livrare")[0]["stare"] == "reusita"

    # 4. panoul arată producția curentă și istoricul
    html = client.get("/operare").text
    assert "În producție acum" in html and "aaa1111" in html and "Promovează în producție" not in html
    asteptate = [
        ("staging", "in_curs"),
        ("staging", "reusita"),
        ("productie", "in_curs"),
        ("productie", "reusita"),
    ]
    assert [
        (x["mediu"], x["stare"]) for x in randuri(admin_engine, "SELECT * FROM livrari ORDER BY creat_la, id")
    ] == asteptate

    # 5. audit
    a = randuri(admin_engine, "SELECT * FROM jurnal_audit WHERE actiune = 'livrare.promovare_ceruta'")
    assert len(a) == 1 and a[0]["utilizator_id"] == proprietar.id and a[0]["detalii"]["versiune"] == "aaa1111"


def test_raport_repetat_este_idempotent_si_nu_da_inapoi_starea(
    client: TestClient, cu_jeton: None, proprietar: Cont, admin_engine: Engine
) -> None:
    post(client, raport("staging", "reusita", IMG1))
    apasa(client, "promovare")
    c = cerere(client)
    assert c
    ok = raport("productie", "reusita", IMG1, c["id"])
    for _ in range(3):
        assert post(client, ok).json() == {"ok": True}
    assert len(randuri(admin_engine, "SELECT 1 FROM livrari WHERE mediu = 'productie'")) == 1
    # un raport întârziat `in_curs` după starea finală nu schimbă nimic
    assert post(client, raport("productie", "in_curs", IMG1, c["id"])).status_code == 200
    assert randuri(admin_engine, "SELECT stare FROM cereri_livrare")[0]["stare"] == "reusita"
    # un raport pentru o cerere necunoscută se păstrează în istoric, dar nu strică nimic
    assert (
        post(client, raport("productie", "esuata", IMG1, "00000000-0000-4000-8000-000000000000")).status_code
        == 200
    )
    assert len(randuri(admin_engine, "SELECT 1 FROM cereri_livrare")) == 1
    # raporturile identice pe staging (fără cerere_id) se deduplică pe imagine + stare
    for _ in range(2):
        post(client, raport("staging", "esuata", IMG2))
    assert (
        len(randuri(admin_engine, "SELECT 1 FROM livrari WHERE imagine = :i AND mediu = 'staging'", i=IMG2))
        == 1
    )


def test_o_promovare_esuata_lasa_versiunea_veche_activa(
    client: TestClient, cu_jeton: None, proprietar: Cont
) -> None:
    post(client, raport("staging", "reusita", IMG1))
    apasa(client, "promovare")
    c = cerere(client)
    assert c
    post(client, raport("productie", "in_curs", IMG1, c["id"]))
    post(client, raport("productie", "esuata", IMG1, c["id"], detalii="readyz nu a răspuns"))
    assert cerere(client) is None
    html = client.get("/operare").text
    assert "necunoscută încă" in html  # nicio versiune nouă în producție
    assert "readyz nu a răspuns" in html  # motivul se vede în istoric
    assert "Promovează în producție" in html  # imaginea de pe staging poate fi cerută din nou


def test_revenire_cerere_fara_imagine_si_rezultat_revenita(
    client: TestClient, cu_jeton: None, proprietar: Cont
) -> None:
    for img, ver in ((IMG1, "v1v1v1v"), (IMG2, "v2v2v2v")):
        post(client, raport("staging", "reusita", img, versiune=ver))
        apasa(client, "promovare")
        c = cerere(client)
        assert c and c["imagine"] == img
        post(client, raport("productie", "reusita", img, c["id"], versiune=ver))
    assert "Revino la versiunea anterioară" in client.get("/operare").text

    r = apasa(client, "revenire")
    assert r.status_code == 303
    c = cerere(client)
    assert c is not None and c["tip"] == "revenire" and "imagine" not in c and c["versiune"] == "v1v1v1v"
    post(client, raport("productie", "in_curs", None, c["id"]))
    post(client, raport("productie", "revenita", IMG1, c["id"], versiune="v1v1v1v"))
    assert cerere(client) is None
    html = client.get("/operare").text
    assert "revenire făcută" in html
    # acum producția este IMG1 iar staging (IMG2) poate fi promovat din nou
    assert "Promovează în producție" in html


def test_promovarea_fara_nimic_pe_staging_si_revenirea_fara_anterioara_dau_409(
    client: TestClient, cu_jeton: None, proprietar: Cont
) -> None:
    assert apasa(client, "promovare").status_code == 409
    assert apasa(client, "revenire").status_code == 409
    post(client, raport("staging", "reusita", IMG1))
    apasa(client, "promovare")
    c = cerere(client)
    assert c
    post(client, raport("productie", "reusita", IMG1, c["id"]))
    assert apasa(client, "revenire").status_code == 409  # nu există versiune anterioară cunoscută


def test_imaginea_promovata_este_doar_una_care_a_trecut_pe_staging(
    client: TestClient, cu_jeton: None, proprietar: Cont
) -> None:
    post(client, raport("staging", "esuata", IMG3))  # a picat pe staging
    post(client, raport("staging", "in_curs", IMG2))  # încă nu a terminat
    assert apasa(client, "promovare").status_code == 409
    assert cerere(client) is None


def test_cerere_ramasa_nepreluata_expira_si_nu_blocheaza_butonul(
    client: TestClient, cu_jeton: None, proprietar: Cont, admin_engine: Engine
) -> None:
    post(client, raport("staging", "reusita", IMG1))
    apasa(client, "promovare")
    assert apasa(client, "promovare").status_code == 409
    with admin_engine.begin() as c:
        c.execute(text("UPDATE cereri_livrare SET creat_la = now() - interval '2 hours'"))
    assert apasa(client, "promovare").status_code == 303
    stari = [x["stare"] for x in randuri(admin_engine, "SELECT stare FROM cereri_livrare ORDER BY creat_la")]
    assert stari == ["esuata", "solicitata"]


def test_butoanele_cer_csrf_confirmare_si_rol_de_proprietar(
    client: TestClient,
    cu_jeton: None,
    proprietar: Cont,
    fabrica_conturi: Fabrica,
    ceas: dict[str, float],
    admin_engine: Engine,
) -> None:
    post(client, raport("staging", "reusita", IMG1))
    jeton = csrf(client, "/operare")
    assert (
        client.post("/operare/promoveaza", data={"confirmare": "da", "csrf_token": "gresit"}).status_code
        == 403
    )
    assert (
        client.post("/operare/promoveaza", data={"csrf_token": jeton}).status_code == 422
    )  # fără confirmare
    assert (
        client.post("/operare/revino", data={"csrf_token": "gresit", "confirmare": "da"}).status_code == 403
    )
    assert randuri(admin_engine, "SELECT 1 FROM cereri_livrare") == []
    client.post("/conturi/iesire", data={"csrf_token": jeton})
    op = fabrica_conturi(Rol.OPERATOR, cu_totp=True)
    autentifica(client, op, ceas)
    for cale in ("/operare", "/operare/confirma?actiune=promovare"):
        assert client.get(cale).status_code == 403
    assert (
        client.post("/operare/promoveaza", data={"confirmare": "da", "csrf_token": csrf(client)}).status_code
        == 403
    )
    assert randuri(admin_engine, "SELECT 1 FROM cereri_livrare") == []


# ---- starea backup-ului în panou ----------------------------------------------------------------------------


def scrie_backup(
    d: Path, nume: str, tip: str, stare: str, inceput: datetime, eroare: str | None = None
) -> None:
    (d / nume).write_text(
        json.dumps(
            {
                "schema": "ama.backup/1",
                "tip": tip,
                "stare": stare,
                "mediu": "productie",
                "versiune": "abc",
                "inceput": inceput.isoformat(),
                "sfarsit": inceput.isoformat(),
                "durata_s": 1.0,
                "eroare": eroare,
            }
        )
    )


def test_operare_arata_backup_si_testul_de_restaurare_cu_regula_de_invechire(
    client: TestClient, proprietar: Cont, config: Callable[..., None], tmp_path: Path
) -> None:
    acum = datetime.now(UTC)
    scrie_backup(tmp_path, "ultimul-backup.json", "backup", "reusit", acum - timedelta(hours=2))
    scrie_backup(
        tmp_path, "ultima-restaurare-test.json", "restaurare_test", "reusit", acum - timedelta(days=9)
    )
    config(backup_status_dir=str(tmp_path))
    html = client.get("/operare").text
    assert "Ultimul backup" in html and "în regulă" in html
    assert "Ultimul test de restaurare" in html and "învechit" in html
    assert "26 de ore" in html and "8 zile" in html


def test_backup_lipsa_sau_corupt_nu_strica_ecranele(
    client: TestClient, proprietar: Cont, config: Callable[..., None], tmp_path: Path
) -> None:
    config(backup_status_dir=str(tmp_path / "nu-exista"))
    assert "încă nu a rulat" in client.get("/operare").text
    (tmp_path / "ultimul-backup.json").write_text("{corupt")
    config(backup_status_dir=str(tmp_path))
    for cale in ("/operare", "/", "/fragment/stare"):
        r = client.get(cale)
        assert r.status_code == 200 and "necitibil" in r.text, cale


def test_backup_esuat_se_afiseaza_rosu_cu_motivul(
    client: TestClient, proprietar: Cont, config: Callable[..., None], tmp_path: Path
) -> None:
    scrie_backup(
        tmp_path, "ultimul-backup.json", "backup", "esuat", datetime.now(UTC), eroare="destinația nu răspunde"
    )
    config(backup_status_dir=str(tmp_path))
    html = client.get("/operare").text
    assert "destinația nu răspunde" in html and "insigna pericol" in html


def test_readyz_nu_depinde_de_backup(client: TestClient, config: Callable[..., None], tmp_path: Path) -> None:
    scrie_backup(
        tmp_path, "ultimul-backup.json", "backup", "esuat", datetime.now(UTC) - timedelta(days=30), eroare="x"
    )
    config(backup_status_dir=str(tmp_path))
    r = client.get("/readyz")
    assert r.status_code == 200 and r.json()["status"] == "ok" and set(r.json()["checks"]) == {"baza"}
    from app.operare import health

    assert health.indicatori()["backup"].bun is False  # indicatorul separat îl vede
