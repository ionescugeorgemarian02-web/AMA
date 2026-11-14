"""F10.4 — regulile scorului de sănătate (4.10) și nucleele indicatorilor (4.13)."""

import datetime as dt

from app.analiza import sanatate
from app.analiza.sanatate import DateRisc

ACUM = dt.datetime(2026, 11, 14, 12, 0, tzinfo=dt.UTC)
Z = dt.timedelta(days=1)
SANATOS = DateRisc(ultima_autentificare=ACUM - 2 * Z, client_de_la=ACUM - 90 * Z, abonament_stare="activ")


def coduri(d: DateRisc) -> list[str]:
    return [s.cod for s in sanatate.semnale(d, ACUM)]


def cu(**schimbari: object) -> DateRisc:
    return DateRisc(**{**SANATOS.__dict__, **schimbari})  # type: ignore[arg-type]


def test_clientul_fara_probleme_are_100_si_niciun_semnal() -> None:
    assert sanatate.semnale(SANATOS, ACUM) == []
    assert sanatate.scor([]) == 100 and sanatate.nivel(100) == "bun"


def test_aprobarile_intarziate_si_expirate_sunt_semnale() -> None:
    s = sanatate.semnale(cu(aprobari_intarziate=1), ACUM)
    assert [x.cod for x in s] == ["aprobari_intarziate"] and s[0].puncte == 20
    assert "1 aprobare așteaptă la client de peste 48 de ore" in s[0].text
    assert sanatate.semnale(cu(aprobari_intarziate=4), ACUM)[0].puncte == 30
    assert coduri(cu(aprobari_expirate=2)) == ["aprobari_expirate"]
    assert sanatate.scor(sanatate.semnale(cu(aprobari_intarziate=3, aprobari_expirate=3), ACUM)) == 50


def test_respingerile_se_judeca_doar_cu_decizii_destule() -> None:
    assert coduri(cu(decizii=4, respingeri=4)) == [], "patru decizii sunt prea puține pentru o concluzie"
    assert coduri(cu(decizii=10, respingeri=3)) == [], "30% nu trece pragul"
    assert coduri(cu(decizii=10, respingeri=4)) == ["respingeri_multe"]


def test_portalul_nedeschis_si_clientul_abia_venit() -> None:
    assert coduri(cu(ultima_autentificare=ACUM - 13 * Z)) == []
    s14 = sanatate.semnale(cu(ultima_autentificare=ACUM - 14 * Z), ACUM)
    assert [x.puncte for x in s14] == [15] and "14 de zile" in s14[0].text
    assert sanatate.semnale(cu(ultima_autentificare=ACUM - 45 * Z), ACUM)[0].puncte == 25
    assert coduri(cu(ultima_autentificare=None)) == ["portal_nedeschis"]
    nou = cu(ultima_autentificare=None, client_de_la=ACUM - 3 * Z)
    assert coduri(nou) == [], "un client venit acum trei zile nu e absent"


def test_facturile_restante_si_suspendarea() -> None:
    assert sanatate.semnale(cu(abonament_stare="restant"), ACUM)[0].puncte == 25
    assert sanatate.semnale(cu(abonament_stare="suspendat"), ACUM)[0].puncte == 40
    assert coduri(cu(abonament_stare=None)) == [], "fără abonament (brand propriu) nu e restanță"


def test_nivelurile_si_scorul_nu_coboara_sub_zero() -> None:
    assert [sanatate.nivel(v) for v in (100, 80, 79, 50, 49, 0)] == [
        "bun",
        "bun",
        "atentie",
        "atentie",
        "risc",
        "risc",
    ]
    tot = cu(
        aprobari_intarziate=5,
        aprobari_expirate=5,
        decizii=10,
        respingeri=9,
        ultima_autentificare=ACUM - 60 * Z,
        abonament_stare="suspendat",
    )
    assert sanatate.scor(sanatate.semnale(tot, ACUM)) == 0
    assert set(sanatate.NIVELURI) == {"bun", "atentie", "risc"}


def test_procentele_nu_se_calculeaza_din_nimic() -> None:
    assert sanatate.rata(0, 0) is None
    assert sanatate.rata(3, 4) == 0.75
    assert sanatate.churn(0, 0) is None
    assert sanatate.churn(1, 19) == 0.05
