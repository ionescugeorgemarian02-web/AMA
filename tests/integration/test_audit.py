"""F1.6 — jurnalul de audit și cel de evenimente: completitudine, doar adăugări, izolare, aceeași tranzacție."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app.conturi import Rol
from app.conturi.cli import creeaza_proprietar
from app.conturi.cli import main as cli_main
from app.conturi.servicii import (
    Actor,
    PermisiuneRefuzata,
    aloca_operator,
    creeaza_client,
    creeaza_utilizator,
    schimba_rol,
)
from app.db import ContextDb, sesiune, sesiune_agentie
from app.logging import correlation_id
from app.operare import audit, evenimente
from app.operare.jurnale import DetaliiNepermise
from tests.conftest import BazaTest
from tests.integration.conftest import PAROLA, Cont, cod_totp, csrf_din, login, post_cod

pytestmark = pytest.mark.db

Fabrica = Callable[..., Cont]


def randuri(admin: Engine, sql: str, **p: object) -> list[dict[str, object]]:
    with admin.connect() as c:
        return [dict(r._mapping) for r in c.execute(text(sql), p)]


def actiuni(admin: Engine, utilizator_id: uuid.UUID) -> list[str]:
    r = randuri(
        admin, "SELECT actiune FROM jurnal_audit WHERE utilizator_id = :u ORDER BY id", u=utilizator_id
    )
    return [str(x["actiune"]) for x in r]


# ---- Gata când: fiecare acțiune din test apare în jurnal cu utilizator și moment ---------------------------


def test_fiecare_actiune_apare_in_jurnal_cu_utilizator_si_moment(
    client: TestClient, fabrica_conturi: Fabrica, admin_engine: Engine, ceas: dict[str, float]
) -> None:
    inainte = datetime.now(UTC) - timedelta(seconds=2)
    cont = fabrica_conturi(Rol.PROPRIETAR, cu_totp=True)

    login(client, cont.email, "parola-gresita-dar-lunga")  # eșec
    login(client, cont.email, cont.parola)  # parolă acceptată
    post_cod(client, "/conturi/2fa", "000000")  # 2FA eșuat
    post_cod(client, "/conturi/2fa", cod_totp(cont.secret or "", ceas["t"]))  # 2FA reușit
    client.post("/conturi/iesire", data={"csrf_token": csrf_din(client.get("/conturi/eu").text)})  # ieșire

    rez = actiuni(admin_engine, cont.id)
    assert rez == [
        "autentificare.esec",
        "autentificare.parola_acceptata",
        "autentificare.2fa_esec",
        "autentificare.2fa_reusita",
        "autentificare.iesire",
    ]
    for rand in randuri(admin_engine, "SELECT * FROM jurnal_audit WHERE utilizator_id = :u", u=cont.id):
        assert rand["creat_la"] >= inainte  # type: ignore[operator]
        assert rand["creat_la"] <= datetime.now(UTC)  # type: ignore[operator]
        assert rand["id"] is not None
    # IP-ul cererii este înregistrat (nu pentru actiunile din CLI)
    http = randuri(
        admin_engine,
        "SELECT ip FROM jurnal_audit WHERE utilizator_id = :u AND actiune LIKE 'autentificare.%'",
        u=cont.id,
    )
    assert {r["ip"] for r in http} == {"203.0.113.7"}


def test_inrolare_2fa_si_blocarea_apar_in_jurnal(
    client: TestClient, fabrica_conturi: Fabrica, admin_engine: Engine, ceas: dict[str, float]
) -> None:
    import re

    from app.config import get_settings

    cont = fabrica_conturi(Rol.PROPRIETAR)
    login(client, cont.email, cont.parola)
    pagina = client.get("/conturi/2fa/inrolare")
    secret = re.search(r'id="secret">([A-Z2-7]+)<', pagina.text)
    assert secret
    client.post("/conturi/2fa/inrolare", data={"cod": "000000", "csrf_token": csrf_din(pagina.text)})
    client.post(
        "/conturi/2fa/inrolare",
        data={"cod": cod_totp(secret.group(1), ceas["t"]), "csrf_token": csrf_din(pagina.text)},
    )
    client.cookies.clear()
    for _ in range(get_settings().login_max_failures_account):
        login(client, cont.email, "parola-gresita-dar-lunga")
    a = actiuni(admin_engine, cont.id)
    for asteptat in (
        "autentificare.2fa_inrolare_inceputa",
        "autentificare.2fa_inrolare_esec",
        "autentificare.2fa_inrolata",
        "autentificare.blocare_cont",
    ):
        assert asteptat in a, a
    assert a.count("autentificare.blocare_cont") == 1  # semnalat o singură dată, la trecerea pragului


def test_login_reusit_fara_2fa_si_esec_utilizator_necunoscut(
    client: TestClient, fabrica_conturi: Fabrica, admin_engine: Engine
) -> None:
    cont = fabrica_conturi(Rol.CLIENT_TITULAR)
    login(client, "necunoscut@exemplu.test", "parola-gresita-dar-lunga")
    login(client, cont.email, cont.parola)
    assert "autentificare.reusita" in actiuni(admin_engine, cont.id)
    rand = randuri(
        admin_engine,
        "SELECT * FROM jurnal_audit WHERE actiune = 'autentificare.reusita' AND utilizator_id = :u",
        u=cont.id,
    )[0]
    assert rand["tenant_id"] == cont.tenant_id
    anonim = randuri(
        admin_engine,
        "SELECT * FROM jurnal_audit WHERE actiune = 'autentificare.esec' AND utilizator_id IS NULL AND ip = '203.0.113.7'",
    )
    assert anonim and anonim[-1]["actor_tip"] == "anonim" and anonim[-1]["tenant_id"] is None
    assert "necunoscut@exemplu.test" not in str(anonim)  # emailul nu se scrie în jurnal


def test_servicii_scriu_audit_si_evenimente(baza: BazaTest, admin_engine: Engine) -> None:
    with sesiune_agentie() as db:
        owner = creeaza_utilizator(
            db,
            email=f"o{uuid.uuid4().hex[:8]}@exemplu.test",
            parola=PAROLA,
            nume_afisat="Owner",
            rol=Rol.PROPRIETAR,
            tenant_id=None,
            actor=Actor.cli(),
        )
        actor = Actor(owner.id, Rol.PROPRIETAR)
        client = creeaza_client(db, "Firma Jurnal", actor=actor)
        op = creeaza_utilizator(
            db,
            email=f"p{uuid.uuid4().hex[:8]}@exemplu.test",
            parola=PAROLA,
            nume_afisat="Op",
            rol=Rol.OPERATOR,
            tenant_id=None,
            actor=actor,
        )
        aloca_operator(db, op.id, client.id, actor=actor)
        schimba_rol(db, op.id, Rol.ANALIST, None, actor=actor)
        ids = (owner.id, client.id, op.id)
    audit_rows = randuri(
        admin_engine,
        "SELECT actiune, utilizator_id, creat_la FROM jurnal_audit WHERE obiect_id = ANY(:ids) ORDER BY id",
        ids=[str(i) for i in ids],
    )
    assert [r["actiune"] for r in audit_rows] == [
        "utilizator.creat",
        "client.creat",
        "utilizator.creat",
        "alocare.creata",
        "rol.schimbat",
    ]
    assert audit_rows[0]["utilizator_id"] is None  # actor CLI
    assert all(r["utilizator_id"] == ids[0] for r in audit_rows[1:])
    ev = randuri(
        admin_engine,
        "SELECT tip FROM jurnal_evenimente WHERE obiect_id = ANY(:ids) ORDER BY id",
        ids=[str(i) for i in ids],
    )
    assert [r["tip"] for r in ev] == [
        "utilizator.creat",
        "client.creat",
        "utilizator.creat",
        "alocare.creata",
        "rol.schimbat",
    ]


def test_serviciile_verifica_permisiunile(baza: BazaTest) -> None:
    with pytest.raises(PermisiuneRefuzata), sesiune_agentie() as db:
        creeaza_client(db, "Intrus", actor=Actor(uuid.uuid4(), Rol.OPERATOR))
    with pytest.raises(PermisiuneRefuzata), sesiune_agentie() as db:
        creeaza_client(db, "Intrus", actor=Actor(uuid.uuid4(), None))  # un actor fără rol nu e „sistem”


def test_cli_creeaza_proprietar_si_nu_primeste_parola_in_argumente(
    baza: BazaTest, admin_engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    email = f"cli{uuid.uuid4().hex[:8]}@exemplu.test"
    assert cli_main(["creeaza-proprietar", "--email", email], parola_din=lambda: PAROLA) == 0
    assert "Proprietar creat" in capsys.readouterr().out
    r = randuri(
        admin_engine,
        "SELECT u.id, a.rol, a.tenant_id, u.parola_hash FROM utilizatori u JOIN apartenente a ON a.utilizator_id = u.id WHERE u.email = :e",
        e=email,
    )
    assert r[0]["rol"] == "proprietar" and r[0]["tenant_id"] is None
    assert str(r[0]["parola_hash"]).startswith("$argon2id$") and PAROLA not in str(r)
    assert "utilizator.creat" in [
        a["actiune"]
        for a in randuri(
            admin_engine,
            "SELECT actiune, actor_tip FROM jurnal_audit WHERE obiect_id = :i",
            i=str(r[0]["id"]),
        )
    ]
    assert (
        randuri(admin_engine, "SELECT actor_tip FROM jurnal_audit WHERE obiect_id = :i", i=str(r[0]["id"]))[
            0
        ]["actor_tip"]
        == "cli"
    )
    capsys.readouterr()
    # Parola nu se primește din argv.
    with pytest.raises(SystemExit):
        cli_main(["creeaza-proprietar", "--email", "x@exemplu.test", "--parola", PAROLA])
    capsys.readouterr()
    # Parolă prea scurtă și email duplicat sunt refuzate cu mesaj, nu cu traceback.
    assert cli_main(["creeaza-proprietar", "--email", "y@exemplu.test"], parola_din=lambda: "scurta") == 1
    assert "cel puțin 12" in capsys.readouterr().err
    assert cli_main(["creeaza-proprietar", "--email", email], parola_din=lambda: PAROLA) == 1
    assert "există deja" in capsys.readouterr().err.lower()


def test_cli_functia_creeaza_proprietar(baza: BazaTest) -> None:
    uid = creeaza_proprietar(f"f{uuid.uuid4().hex[:8]}@exemplu.test", None, PAROLA)
    assert uuid.UUID(uid).version == 7


# ---- Doar adăugări, impus de bază ----------------------------------------------------------------------------


@pytest.mark.parametrize("tabel", ["jurnal_audit", "jurnal_evenimente"])
def test_aplicatia_nu_poate_modifica_sau_sterge_jurnalul(
    baza: BazaTest, fabrica_conturi: Fabrica, tabel: str
) -> None:
    cont = fabrica_conturi(Rol.CLIENT_TITULAR)
    with sesiune(ContextDb(tenant_id=cont.tenant_id, agency=True)) as db:
        audit.record(db, "proba.scrisa", tenant_id=cont.tenant_id)
        evenimente.emite(db, "proba.scrisa", sursa="test", tenant_id=cont.tenant_id)
    for sql in (f"UPDATE {tabel} SET creat_la = now()", f"DELETE FROM {tabel}", f"TRUNCATE {tabel}"):
        with pytest.raises(DBAPIError, match="permission denied"), sesiune(ContextDb(agency=True)) as db:
            db.execute(text(sql))


@pytest.mark.parametrize("tabel", ["jurnal_audit", "jurnal_evenimente"])
def test_declansatorul_blocheaza_modificarea_chiar_si_pentru_proprietarul_tabelului(
    baza: BazaTest, fabrica_conturi: Fabrica, admin_engine: Engine, tabel: str
) -> None:
    cont = fabrica_conturi(Rol.CLIENT_TITULAR)
    with sesiune(ContextDb(agency=True)) as db:
        audit.record(db, "proba.scrisa", tenant_id=cont.tenant_id)
        evenimente.emite(db, "proba.scrisa", sursa="test", tenant_id=cont.tenant_id)
    # Superutilizatorul ocolește RLS și are toate drepturile: doar declanșatorul mai oprește modificarea.
    for sql in (f"UPDATE {tabel} SET creat_la = now()", f"DELETE FROM {tabel}", f"TRUNCATE {tabel}"):
        with pytest.raises(DBAPIError, match="doar pentru adaugare"), admin_engine.begin() as c:
            c.execute(text(sql))
    # Proprietarul tabelului are dreptul TRUNCATE (RLS nu se aplică la TRUNCATE): îl oprește declanșatorul.
    dsn = baza.owner_url.replace("postgresql+psycopg", "postgresql")
    with (
        psycopg.connect(dsn) as conn,
        pytest.raises(psycopg.errors.IntegrityConstraintViolation, match="doar pentru"),
    ):
        conn.execute(f"TRUNCATE {tabel}")  # type: ignore[call-overload]
    # Fără politică de UPDATE/DELETE, nici proprietarul nu poate atinge rânduri (RLS forțat).
    with psycopg.connect(dsn) as conn:
        conn.execute("SELECT set_config('app.agency', '1', true)")
        assert conn.execute(f"UPDATE {tabel} SET creat_la = now()").rowcount == 0  # type: ignore[call-overload]


def test_drepturile_aplicatiei_pe_jurnale_sunt_doar_insert_si_select(
    baza: BazaTest, admin_engine: Engine
) -> None:
    with admin_engine.connect() as c:
        for tabel in ("jurnal_audit", "jurnal_evenimente"):
            for drept, asteptat in (
                ("SELECT", True),
                ("INSERT", True),
                ("UPDATE", False),
                ("DELETE", False),
                ("TRUNCATE", False),
            ):
                are = c.execute(
                    text("SELECT has_table_privilege('ama_app', :t, :d)"), {"t": tabel, "d": drept}
                ).scalar_one()
                assert are is asteptat, (tabel, drept)


# ---- Izolare pe client --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tabel", "scrie"),
    [
        ("jurnal_audit", lambda db, t: audit.record(db, "proba.izolare", tenant_id=t)),
        ("jurnal_evenimente", lambda db, t: evenimente.emite(db, "proba.izolare", sursa="test", tenant_id=t)),
    ],
)
def test_jurnalele_sunt_izolate_pe_client(
    baza: BazaTest, fabrica_conturi: Fabrica, tabel: str, scrie: Callable[..., object]
) -> None:
    a, b = fabrica_conturi(Rol.CLIENT_TITULAR), fabrica_conturi(Rol.CLIENT_TITULAR)
    with sesiune(ContextDb(agency=True)) as db:
        scrie(db, a.tenant_id)
        scrie(db, b.tenant_id)
        scrie(db, None)  # intrare la nivel de agenție
    cond = {"jurnal_audit": "actiune", "jurnal_evenimente": "tip"}[tabel]
    sql = text(f"SELECT tenant_id FROM {tabel} WHERE {cond} = 'proba.izolare'")
    with sesiune(ContextDb(tenant_id=a.tenant_id)) as db:
        assert {r[0] for r in db.execute(sql)} == {a.tenant_id}  # nici B, nici intrările fără client
    with sesiune(ContextDb(tenant_id=b.tenant_id)) as db:
        assert {r[0] for r in db.execute(sql)} == {b.tenant_id}
    with sesiune() as db:
        assert db.execute(sql).all() == []  # fără context: nimic
    with sesiune(ContextDb(agency=True)) as db:
        assert {r[0] for r in db.execute(sql)} >= {a.tenant_id, b.tenant_id, None}
    # Clientul A nu poate scrie în jurnalul lui B și nici la nivel de agenție.
    for tinta in (b.tenant_id, None):
        with (
            pytest.raises(DBAPIError, match="row-level security"),
            sesiune(ContextDb(tenant_id=a.tenant_id)) as db,
        ):
            scrie(db, tinta)


# ---- Aceeași tranzacție, corelare, fără secrete -------------------------------------------------------------------


def test_jurnalul_este_in_aceeasi_tranzactie_cu_actiunea(baza: BazaTest, admin_engine: Engine) -> None:
    email = f"rb{uuid.uuid4().hex[:8]}@exemplu.test"
    ids: list[uuid.UUID] = []
    with pytest.raises(RuntimeError, match="anulează"), sesiune_agentie() as db:
        u = creeaza_utilizator(
            db,
            email=email,
            parola=PAROLA,
            nume_afisat="Rollback",
            rol=Rol.PROPRIETAR,
            tenant_id=None,
            actor=Actor.cli(),
        )
        ids.append(u.id)
        # În interiorul tranzacției rândul de audit există deja...
        assert (
            db.execute(
                text("SELECT count(*) FROM jurnal_audit WHERE obiect_id = :i"), {"i": str(u.id)}
            ).scalar_one()
            == 1
        )
        raise RuntimeError("anulează tot")
    # ...iar după rollback dispar și acțiunea, și jurnalul, și evenimentul.
    assert randuri(admin_engine, "SELECT 1 FROM utilizatori WHERE email = :e", e=email) == []
    assert randuri(admin_engine, "SELECT 1 FROM jurnal_audit WHERE obiect_id = :i", i=str(ids[0])) == []
    assert randuri(admin_engine, "SELECT 1 FROM jurnal_evenimente WHERE obiect_id = :i", i=str(ids[0])) == []


def test_corelarea_si_fara_secrete_in_detalii(baza: BazaTest, admin_engine: Engine) -> None:
    token = correlation_id.set("corelare-proba-123")
    try:
        with sesiune(ContextDb(agency=True)) as db:
            audit.record(
                db,
                "proba.corelare",
                detalii={"text": "x" * 2000, "uuid": uuid.uuid4(), "lista": [1, {"a": 2}]},
            )
            for cheie in ("parola", "token", "totp_cod", "Secret", "cod_recuperare"):
                with pytest.raises(DetaliiNepermise):
                    audit.record(db, "proba.interzisa", detalii={"ok": {cheie: "valoare"}})
    finally:
        correlation_id.reset(token)
    rand = randuri(
        admin_engine, "SELECT corelare_id, detalii FROM jurnal_audit WHERE actiune = 'proba.corelare'"
    )[0]
    assert rand["corelare_id"] == "corelare-proba-123"
    assert len(str(rand["detalii"]["text"])) == 500  # type: ignore[index]
    assert randuri(admin_engine, "SELECT 1 FROM jurnal_audit WHERE actiune = 'proba.interzisa'") == []


def test_corelarea_vine_din_cerere(
    client: TestClient, fabrica_conturi: Fabrica, admin_engine: Engine
) -> None:
    cont = fabrica_conturi()
    pagina = client.get("/conturi/login")
    client.post(
        "/conturi/login",
        data={"email": cont.email, "parola": cont.parola, "csrf_token": csrf_din(pagina.text)},
        headers={"x-request-id": "cerere-de-proba-0001"},
    )
    rand = randuri(
        admin_engine,
        "SELECT corelare_id FROM jurnal_audit WHERE utilizator_id = :u AND actiune = 'autentificare.reusita'",
        u=cont.id,
    )
    assert rand[0]["corelare_id"] == "cerere-de-proba-0001"


# ---- /readyz ---------------------------------------------------------------------------------------------------------


def test_readyz_verifica_baza(client: TestClient) -> None:
    r = client.get("/readyz")
    assert r.status_code == 200 and r.json()["checks"]["baza"] == "ok"


def test_readyz_semnaleaza_baza_cazuta(baza: BazaTest, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings
    from app.db import reset_engine
    from app.main import create_app

    monkeypatch.setenv(
        "AMA_DATABASE_URL", make_url(baza.app_url).set(port=1).render_as_string(hide_password=False)
    )
    get_settings.cache_clear()
    reset_engine()
    try:
        r = TestClient(create_app()).get("/readyz")
        assert r.status_code == 503 and r.json()["checks"]["baza"].startswith("eroare")
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        reset_engine()
