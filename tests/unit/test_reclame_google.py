"""F13.2 — rândul GAQL: micro-unități în bani, conversii zecimale rotunjite în jos."""

import datetime as dt

from app.connectors.reclame.google import client_id, rand_din_gaql


def test_randul_gaql() -> None:
    r = rand_din_gaql(
        {
            "campaign": {"id": "7", "name": "C"},
            "adGroupAd": {"ad": {"id": "9", "name": "R"}},
            "segments": {"date": "2026-11-10"},
            "metrics": {"costMicros": "12345678", "impressions": "100", "clicks": "3", "conversions": 2.6},
        },
        "reclama",
    )
    assert (r.id_extern, r.parinte_extern, r.zi, r.cheltuiala_bani, r.rezultate) == (
        "9",
        "7",
        dt.date(2026, 11, 10),
        1234,
        2,
    )
    assert client_id("123-456-7890") == "1234567890"
