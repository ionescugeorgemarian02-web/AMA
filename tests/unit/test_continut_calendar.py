"""F6.1 — nucleul determinist al calendarului: distribuția pe piloni, răspândirea sloturilor, problemele propunerii."""

import datetime as dt
from collections import Counter

from app.continut import calendar
from tests.continut_utile import calendar_valid

INCEPUT = dt.date(2026, 12, 1)


def test_planificarea_e_determinista_acopera_30_de_zile_si_respecta_ponderile() -> None:
    c = calendar.ContinutCalendar.model_validate(calendar_valid())
    a, b = calendar.planifica(c, INCEPUT), calendar.planifica(c, INCEPUT)
    assert a == b and len(a) == round(4 * 30 / 7) + round(30 / 7)
    zile = sorted({s.slot_la.astimezone(calendar.FUS).date() for s in a})
    assert zile[0] == INCEPUT and zile[-1] >= INCEPUT + dt.timedelta(days=23)
    piloni = Counter(s.pilon for s in a)
    assert piloni.most_common(1)[0][0] == "Cafea proaspătă" and set(piloni) == {
        p["nume"] for p in calendar_valid()["piloni"]
    }
    # ora din fusul României (18:00 pe Facebook), salvată în UTC
    assert all(s.slot_la.tzinfo is dt.UTC and s.slot_la.astimezone(calendar.FUS).hour == 18 for s in a)
    assert [s.nr for s in a] == list(range(1, len(a) + 1))


def test_problemele_propunerii() -> None:
    ok = calendar_valid()
    assert calendar.probleme_calendar(ok, canale_permise=["facebook"], inceput=INCEPUT) == []
    assert any(
        "nu este în strategia" in p
        for p in calendar.probleme_calendar(ok, canale_permise=["linkedin"], inceput=INCEPUT)
    )
    fara_idei = calendar_valid(
        idei=[i for i in ok["idei"] if i["pilon"] != "Comunitate"]
        + [{"pilon": "Preparare acasă", "subiect": "Ibricul sau filtrul?"}]
    )
    assert any(
        "Comunitate nu are nicio idee" in p
        for p in calendar.probleme_calendar(fara_idei, canale_permise=["facebook"], inceput=INCEPUT)
    )
    rar = calendar_valid(formate=[{"canal": "facebook", "tip": "postare", "pe_saptamana": 1}])
    # 4 sloturi pe 30 de zile, 3 piloni: fereastra e acoperită și fiecare pilon apare
    assert calendar.probleme_calendar(rar, canale_permise=["facebook"], inceput=INCEPUT) == []
    gresit = calendar_valid(piloni=ok["piloni"][:2])
    assert calendar.probleme_calendar(
        gresit, canale_permise=["facebook"], inceput=INCEPUT
    )  # schema: minim 3 piloni
    necunoscut = calendar_valid(
        idei=[*ok["idei"], {"pilon": "Altceva", "subiect": "Un subiect oarecare", "unghi": ""}]
    )
    assert any(
        "pilon necunoscut" in p
        for p in calendar.probleme_calendar(necunoscut, canale_permise=["facebook"], inceput=INCEPUT)
    )


def test_canalele_strategiei() -> None:
    s = {"plan_30_zile": [{"canal": "facebook"}, {"canal": "email"}], "plan_90_zile": [{"canal": "linkedin"}]}
    assert calendar.canale_din_strategie(s) == ["facebook", "linkedin"]
