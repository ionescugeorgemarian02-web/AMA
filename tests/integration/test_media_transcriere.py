"""F8.3 — transcrierea inversă și timpii pe cuvânt. „Gata când”: pentru o narațiune de probă, fiecare cuvânt are
moment, iar o frază citită greșit este detectată. Vocea și transcriptorul sunt SIMULATE (D-007): momentele se
măsoară din semnal; whisper.cpp real: la migrare."""

# ruff: noqa: F811
import itertools
import uuid

import pytest

from app.db import sesiune_tenant
from app.media import normalizare, transcriere
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401

pytestmark = pytest.mark.db
SCRIPT = [
    "Cafeneaua Zorilor prăjește cafea în fiecare marți, la Brașov.",
    "Etiopia Guji costă 49 lei și are note de afine.",
    "Comandă până la ora 12:00 și primești cafeaua în aceeași zi.",
]


def test_fiecare_cuvant_are_moment_si_fraza_citita_gresit_este_detectata(tenant: uuid.UUID) -> None:
    fraze = [normalizare.normalizeaza(f) for f in SCRIPT]
    with sesiune_tenant(tenant) as db:
        bun = transcriere.naratiune_verificata(db, tenant, fraze)
        assert not bun.semnalate and not bun.resintetizata
        cuvinte = bun.aliniere.cuvinte
        assert [c.cuvant for c in cuvinte] == [j for f in fraze for j in transcriere.jetoane(f)]
        assert all(c.sfarsit > c.inceput for c in cuvinte)
        assert all(b.inceput >= a.sfarsit for a, b in itertools.pairwise(cuvinte))
        assert cuvinte[-1].sfarsit <= bun.naratiune.durata + 0.01
        # momentele vin din semnal: între fraze este pauza de 200 ms
        prima = len(transcriere.jetoane(fraze[0]))
        assert cuvinte[prima].inceput - cuvinte[prima - 1].sfarsit == pytest.approx(0.2, abs=0.02)

        gresit = transcriere.naratiune_verificata(
            db, tenant, fraze, gresit={"Brașov": "Brăila", "marți": "joi"}
        )
        assert gresit.resintetizata  # o resinteză, apoi semnalarea
        assert gresit.semnalate == [fraze[0]]
        f0 = gresit.aliniere.fraze[0]
        assert f0.wer > transcriere.PRAG_WER and "brăila" in f0.auzit
        assert all(f.corecta for f in gresit.aliniere.fraze[1:])
        assert all(c.sfarsit >= c.inceput for c in gresit.aliniere.cuvinte)
