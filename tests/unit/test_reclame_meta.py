"""F13.1 — nucleele pure: banii din textul Marketing API, rândul de insights, formatul sumelor în panou."""

import datetime as dt

from app.connectors.reclame.meta import bani, rand_din_insights
from app.panou.reclame_web import lei


def test_banii_se_pastreaza_exact_in_subunitati() -> None:
    assert bani("12.34") == 1234 and bani("0.1") == 10 and bani("7") == 700 and bani("x") == 0


def test_randul_de_insights() -> None:
    r = rand_din_insights(
        {
            "campaign_id": "1",
            "campaign_name": "C",
            "ad_id": "9",
            "ad_name": "R",
            "date_start": "2026-11-10",
            "spend": "3.50",
            "impressions": "100",
            "clicks": "4",
            "actions": [{"action_type": "lead", "value": "2"}, {"action_type": "link_click", "value": "4"}],
        },
        "reclama",
    )
    assert (r.id_extern, r.parinte_extern, r.zi, r.cheltuiala_bani, r.rezultate) == (
        "9",
        "1",
        dt.date(2026, 11, 10),
        350,
        2,
    )
    assert rand_din_insights({"campaign_id": "1", "date_start": "2026-11-10"}, "campanie").rezultate is None


def test_lei() -> None:
    assert lei(1234567) == "12.345,67" and lei(5) == "0,05" and lei(None) == "–"


def test_trafic_si_lead_se_masoara_independent() -> None:
    date = {"campaign_id": "1", "date_start": "2026-11-10", "clicks": "37", "inline_link_clicks": "23"}
    r = rand_din_insights(date, "campanie")
    assert r.clicuri_trafic == 23 and r.rezultate is None
    assert rand_din_insights({**date, "actions": []}, "campanie").rezultate == 0
