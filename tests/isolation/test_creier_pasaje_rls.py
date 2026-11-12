"""F4.3 — pasajele și vectorii sunt date de client. „Gata când” (izolare): căutarea unui client nu întoarce niciodată
pasajele altuia, nici când pasajul altui client este potrivirea perfectă."""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app import creier
from app.creier.indexare import vector_literal
from app.db import ContextDb, sesiune
from app.ids import new_id
from tests.isolation.conftest import Date
from tests.vectorizator_fals import vector_bow

pytestmark = [pytest.mark.db, pytest.mark.isolation]
MODEL = "proba/e5-mic"
TEXT_A = "Etiopia Guji costă 49 lei pentru 250 g, cu note de afine."
TEXT_B = "Etiopia Guji costă 55 lei pentru 250 g, cu note de afine și miere."  # potrivirea perfectă a întrebării lui A, dar a lui B


@pytest.fixture
def pasaje_doi(date: Date, admin_engine: Engine) -> Iterator[dict[str, uuid.UUID]]:
    ids: dict[str, uuid.UUID] = {}
    with admin_engine.begin() as c:
        for cheie, tenant, txt in (("a", date.a, TEXT_A), ("b", date.b, TEXT_B)):
            sursa, doc, pas = new_id(), new_id(), new_id()
            ids[cheie] = pas
            c.execute(
                text(
                    "INSERT INTO surse (id, tenant_id, tip, statut, nume) VALUES (:i, :t, 'manual', 'material_client', 'S')"
                ),
                {"i": sursa, "t": tenant},
            )
            c.execute(
                text(
                    "INSERT INTO documente_colectate (id, tenant_id, sursa_id, tip, text, hash_continut, hash_text) VALUES (:i, :t, :s, 'text_lipit', :x, :h, :h)"
                ),
                {"i": doc, "t": tenant, "s": sursa, "x": txt, "h": new_id().hex * 2},
            )
            c.execute(
                text(
                    "INSERT INTO pasaje (id, tenant_id, sursa_id, document_id, pozitie, car_inceput, car_sfarsit, text, "
                    "text_normalizat, hash_document, embedding, model_vectori) VALUES (:i, :t, :s, :d, 0, 0, :n, :x, :xn, :h, "
                    "CAST(:e AS vector), :m)"
                ),
                {"i": pas, "t": tenant, "s": sursa, "d": doc, "n": len(txt), "x": txt, "xn": txt.lower(),
                 "h": new_id().hex * 2, "e": vector_literal(vector_bow(txt)), "m": MODEL},
            )  # fmt: skip
    yield ids


def test_cautarea_unui_client_nu_intoarce_pasajele_altuia_nici_cand_acelea_se_potrivesc_perfect(
    date: Date, pasaje_doi: dict[str, uuid.UUID]
) -> None:
    intrebare = "Cât costă Etiopia Guji cu note de afine și miere?"  # cuvintele din pasajul lui B
    for tenant, user, propriu, strain in ((date.a, date.user_a, "a", "b"), (date.b, date.user_b, "b", "a")):
        with sesiune(ContextDb(tenant_id=tenant, user_id=user)) as db:
            for kw in ({}, {"doar_text": True}):
                r = creier.cauta(
                    db, tenant_id=tenant, intrebare=intrebare, limita=10, vector_intrebare=vector_bow(intrebare),
                    model_vector=MODEL, **kw,
                )  # fmt: skip
                ids = {x.pasaj_id for x in r.rezultate}
                assert pasaje_doi[propriu] in ids and pasaje_doi[strain] not in ids


def test_o_sesiune_a_unui_client_nu_poate_cauta_in_numele_altuia(
    date: Date, pasaje_doi: dict[str, uuid.UUID]
) -> None:
    with (
        sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as db,
        pytest.raises(creier.CautareRefuzata),
    ):
        creier.cauta(db, tenant_id=date.b, intrebare="Etiopia Guji", doar_text=True)
    with sesiune(
        ContextDb()
    ) as db:  # fără client: baza nu arată nimic, chiar dacă se cere explicit clientul B
        assert creier.cauta(db, tenant_id=date.b, intrebare="Etiopia Guji", doar_text=True).rezultate == []


@pytest.mark.parametrize("coloana", ["text", "embedding", "text_normalizat"])
def test_rls_pe_pasaje_in_sql_direct(date: Date, pasaje_doi: dict[str, uuid.UUID], coloana: str) -> None:
    with sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as db:
        vazute = {r[0] for r in db.execute(text(f"SELECT id FROM pasaje WHERE {coloana} IS NOT NULL"))}
        assert pasaje_doi["a"] in vazute and pasaje_doi["b"] not in vazute
        r = db.execute(text("UPDATE pasaje SET text = 'furat' WHERE id = :i"), {"i": pasaje_doi["b"]})
        assert r.rowcount == 0  # type: ignore[attr-defined]
        r = db.execute(text("DELETE FROM pasaje WHERE id = :i"), {"i": pasaje_doi["b"]})
        assert r.rowcount == 0  # type: ignore[attr-defined]
    with sesiune(ContextDb()) as db:
        assert db.execute(text("SELECT count(*) FROM pasaje")).scalar_one() == 0


def test_un_client_nu_poate_insera_pasaje_pe_numele_altuia(
    date: Date, pasaje_doi: dict[str, uuid.UUID], admin_engine: Engine
) -> None:
    with admin_engine.connect() as c:
        sursa_b, doc_b = c.execute(
            text("SELECT sursa_id, document_id FROM pasaje WHERE id = :i"), {"i": pasaje_doi["b"]}
        ).one()
    with pytest.raises(DBAPIError), sesiune(ContextDb(tenant_id=date.a, user_id=date.user_a)) as db:
        db.execute(
            text(
                "INSERT INTO pasaje (id, tenant_id, sursa_id, document_id, pozitie, car_inceput, car_sfarsit, text, "
                "text_normalizat, hash_document) VALUES (:i, :t, :s, :d, 9, 0, 3, 'abc', 'abc', :h)"
            ),
            {"i": new_id(), "t": date.b, "s": sursa_b, "d": doc_b, "h": "c" * 64},
        )
