import datetime as dt

from app.comert.atribuire import calculeaza


def test_atribuire_lunara():
    def rand(**kw):
        return {"creata_la": "2026-11-01T00:00:00Z", "total_bani": 1000, "moneda": "RON", **kw}

    r = calculeaza(
        [
            rand(utm_campaign="c1", utm_source="meta", cod_reducere="COD", rambursat_bani=100),
            rand(cod_reducere="COD"),
            rand(),
            rand(moneda="EUR"),
            rand(anulata=True),
            rand(creata_la="2026-12-01T00:00:00Z"),
        ],
        dt.date(2026, 11, 1),
        {"COD": ("c2", "email")},
    )
    assert r[("c1", "meta", "RON")] == 900
    assert r[("c2", "email", "RON")] == 1000
    assert r[("necunoscut", "necunoscut", "RON")] == 1000
    assert r[("necunoscut", "necunoscut", "EUR")] == 1000
