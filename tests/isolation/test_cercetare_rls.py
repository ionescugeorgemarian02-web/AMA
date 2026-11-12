"""F4.2 — sursele, colectările, paginile și documentele colectate sunt date de client: RLS pe `tenant_id`."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app import cercetare
from app.db import ContextDb, sesiune
from app.ids import new_id
from tests.isolation.conftest import Date

pytestmark = [pytest.mark.db, pytest.mark.isolation]
H = "a" * 64
TABELE = ("surse", "colectari", "colectari_pagini", "documente_colectate")


@pytest.fixture
def randuri(date: Date, admin_engine: Engine) -> dict[str, dict[str, uuid.UUID]]:
    ids: dict[str, dict[str, uuid.UUID]] = {}
    with admin_engine.begin() as c:
        for cheie, tenant in (("a", date.a), ("b", date.b)):
            i = {k: new_id() for k in ("sursa", "colectare", "pagina", "document")}
            ids[cheie] = i
            c.execute(
                text(
                    "INSERT INTO surse (id, tenant_id, tip, statut, nume, url_radacina) VALUES (:i, :t, 'site', 'site_client', 'S', 'https://x.test/')"
                ),
                {"i": i["sursa"], "t": tenant},
            )
            c.execute(
                text(
                    "INSERT INTO colectari (id, tenant_id, sursa_id, user_agent) VALUES (:i, :t, :s, 'AMA-Colector/test')"
                ),
                {"i": i["colectare"], "t": tenant, "s": i["sursa"]},
            )
            c.execute(
                text(
                    "INSERT INTO documente_colectate (id, tenant_id, sursa_id, tip, url, text, hash_continut, hash_text) VALUES (:i, :t, :s, 'pagina', 'https://x.test/', 'text', :h, :h)"
                ),
                {"i": i["document"], "t": tenant, "s": i["sursa"], "h": H},
            )
            c.execute(
                text(
                    "INSERT INTO colectari_pagini (id, tenant_id, colectare_id, url, document_id) VALUES (:i, :t, :c, 'https://x.test/', :d)"
                ),
                {"i": i["pagina"], "t": tenant, "c": i["colectare"], "d": i["document"]},
            )
    return ids


def vazute(ctx: ContextDb, tabel: str) -> set[uuid.UUID]:
    with sesiune(ctx) as s:
        return {r[0] for r in s.execute(text(f"SELECT id FROM {tabel}"))}


@pytest.mark.parametrize(
    ("tabel", "cheie"),
    [
        ("surse", "sursa"),
        ("colectari", "colectare"),
        ("colectari_pagini", "pagina"),
        ("documente_colectate", "document"),
    ],
)
def test_fiecare_client_vede_doar_ce_a_colectat_el(
    date: Date, randuri: dict[str, dict[str, uuid.UUID]], tabel: str, cheie: str
) -> None:
    a, b = ContextDb(tenant_id=date.a, user_id=date.user_a), ContextDb(tenant_id=date.b, user_id=date.user_b)
    assert randuri["a"][cheie] in vazute(a, tabel) and randuri["b"][cheie] not in vazute(a, tabel)
    assert randuri["b"][cheie] in vazute(b, tabel) and randuri["a"][cheie] not in vazute(b, tabel)
    assert {randuri["a"][cheie], randuri["b"][cheie]} <= vazute(ContextDb(agency=True), tabel)
    assert vazute(ContextDb(), tabel) == set()


def test_un_client_nu_poate_scrie_pe_numele_altuia(
    date: Date, randuri: dict[str, dict[str, uuid.UUID]]
) -> None:
    ctx_a = ContextDb(tenant_id=date.a, user_id=date.user_a)
    with pytest.raises(DBAPIError), sesiune(ctx_a) as db:
        db.add(
            cercetare.SursaColectare(
                id=new_id(), tenant_id=date.b, tip="manual", statut="material_client", nume="furat"
            )
        )
        db.flush()
    with sesiune(ctx_a) as db, pytest.raises(cercetare.ColectareInvalida):  # sursa lui B nu se vede
        cercetare.pregateste_colectare(db, randuri["b"]["sursa"])
    with sesiune(ctx_a) as db:
        r = db.execute(
            text("UPDATE documente_colectate SET titlu = 'furat' WHERE id = :i"),
            {"i": randuri["b"]["document"]},
        )
        assert r.rowcount == 0  # type: ignore[attr-defined]


def test_acelasi_text_nu_se_pastreaza_de_doua_ori_in_aceeasi_sursa_dar_clientii_pot_avea_acelasi_text(
    date: Date, randuri: dict[str, dict[str, uuid.UUID]], admin_engine: Engine
) -> None:
    with pytest.raises(DBAPIError) as exc, admin_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO documente_colectate (id, tenant_id, sursa_id, tip, url, text, hash_continut, hash_text) VALUES (:i, :t, :s, 'pagina', 'https://x.test/alta', 'text', :h, :h)"
            ),
            {"i": new_id(), "t": date.a, "s": randuri["a"]["sursa"], "h": H},
        )
    assert "documente_text" in str(exc.value)  # B are același hash_text (H) în sursa lui: permis
