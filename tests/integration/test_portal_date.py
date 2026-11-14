"""F7.7 — exportul și ștergerea. „Gata când”: datele clientului de test se exportă complet și se șterg la cerere.
Complet = fiecare tabel cu `tenant_id` în care clientul are rânduri, plus fișierele; nimic de la alt client.
Ștergerea rulează ca job durabil, ca proprietar al schemei, într-o singură tranzacție."""

import io
import json
import uuid
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app import media
from app.config import get_settings
from app.conturi import Rol
from app.db import sesiune_tenant
from app.db.stergere import ordine
from app.onboarding import sesiuni
from tests.integration.conftest import Cont, csrf_din, login
from tests.integration.utile_site import asteapta

pytestmark = pytest.mark.db
JPEG = b"\xff\xd8\xff\xe0" + b"date-zorilor" * 30
CU_TENANT = """SELECT c.relname FROM pg_class c JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id'
WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r'"""


def randuri(admin: Engine, tenant: uuid.UUID) -> dict[str, int]:
    # Fiecare numărare în tranzacția ei (autocommit): o citire care ține blocaje pe mai multe tabele deodată intră
    # în blocaj reciproc cu ștergerea, care ia tabelele pe rând în acces exclusiv (apărut odată cu tabelele F8).
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        tabele = [r[0] for r in c.execute(text(CU_TENANT))]
        rez = {t: c.execute(text(f'SELECT count(*) FROM "{t}" WHERE tenant_id = :t'), {"t": tenant}).scalar_one()
               for t in tabele}  # fmt: skip
    return {t: n for t, n in rez.items() if n}


def cu_date(cont: Cont) -> None:
    t = cont.tenant_id
    assert t is not None
    with sesiune_tenant(t, cont.id) as db:
        media.biblioteca.incarca(db, t, JPEG, nume_original="logo.jpg", sursa="portal", utilizator_id=cont.id)
        media.tendinte.adauga(db, t, "https://example.org/idee cafea la rece", utilizator_id=cont.id)
        sesiuni.deschide(db, tenant_id=t, utilizator_id=cont.id)


def test_export_complet_apoi_stergere_la_cerere(
    client: TestClient, fabrica_conturi: Callable[..., Cont], admin_engine: Engine, executor: None
) -> None:
    cont = fabrica_conturi(Rol.CLIENT_TITULAR)
    alt = fabrica_conturi(Rol.CLIENT_TITULAR)
    cu_date(cont)
    cu_date(alt)
    t = cont.tenant_id
    assert t is not None and alt.tenant_id is not None
    inainte = randuri(admin_engine, t)
    alt_inainte = randuri(admin_engine, alt.tenant_id)
    assert {"active", "tendinte", "apartenente", "onboarding_sesiuni"} <= set(inainte) or len(inainte) >= 5
    assert login(client, cont.email, cont.parola).status_code == 303
    r = client.get("/portal/date/export")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    manifest = json.loads(z.read("manifest.json"))
    # complet: fiecare tabel în care clientul are rânduri (în afară de cele pe care aplicația nu le poate citi)
    for tabel, n in inainte.items():
        if (
            f"date/{tabel}.json" in z.namelist()
        ):  # jurnalele cresc cu autentificarea, deci cel puțin cât înainte
            assert (
                manifest["tabele"][tabel] >= n
                if tabel.startswith("jurnal_")
                else manifest["tabele"][tabel] == n
            )

    lipsa = set(inainte) - {n.removeprefix("date/").removesuffix(".json") for n in z.namelist()}
    assert lipsa <= {"audit", "evenimente"}, (
        lipsa
    )  # jurnalele: doar agenția (aplicația nu le citește ca client)
    assert JPEG in [z.read(n) for n in z.namelist() if n.startswith("fisiere/")]
    toate = " ".join(z.read(n).decode("utf-8", "replace") for n in z.namelist() if n.startswith("date/"))
    assert str(alt.tenant_id) not in toate  # nimic de la alt client
    # ștergerea la cerere: confirmare obligatorie
    h = client.get("/portal/cont").text
    r = client.post("/portal/date/sterge", data={"csrf_token": csrf_din(h), "confirmare": "da"})
    assert "nu a fost înregistrată" in r.text
    r = client.post("/portal/date/sterge", data={"csrf_token": csrf_din(h), "confirmare": "ȘTERGE"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    asteapta(lambda: set(randuri(admin_engine, t)) <= {"jurnal_audit", "cereri_stergere"} or None, secunde=30)
    with admin_engine.connect() as c:
        stare, rezultat = c.execute(text("SELECT stare, rezultat FROM cereri_stergere WHERE tenant_id = :t"),
                                    {"t": t}).one()  # fmt: skip
        assert stare == "executat" and rezultat["active"] == 1
        assert c.execute(text("SELECT nume, sters_la IS NOT NULL FROM clienti WHERE id = :t"), {"t": t}).one() == (
            "Client șters", True)  # fmt: skip
        email = c.execute(text("SELECT email FROM utilizatori WHERE id = :u"), {"u": cont.id}).scalar_one()
        assert email.endswith("@sters.invalid")
        rls = c.execute(text("SELECT bool_and(relforcerowsecurity) FROM pg_class WHERE relname IN ('active', "
                             "'utilizatori', 'livrabile')")).scalar_one()  # fmt: skip
        assert rls is True  # RLS forțat la loc după ștergere
    assert randuri(admin_engine, t).get("jurnal_audit", 0) > 0  # jurnalul de audit se păstrează
    assert not (Path(get_settings().media_dir) / str(t)).exists()
    assert randuri(admin_engine, alt.tenant_id) == alt_inainte  # celălalt client, neatins
    client.cookies.clear()
    assert login(client, cont.email, cont.parola).status_code != 303


def test_ordinea_stergerii_copiii_intai() -> None:
    o = ordine({"a", "b", "c"}, [("b", "a"), ("c", "b"), ("x", "a")])
    assert o.index("c") < o.index("b") < o.index("a")
