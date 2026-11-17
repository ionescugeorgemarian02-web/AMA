"""F13.5 — gardianul de buget: plafoane, ritm, scutiri (D-010)."""

import datetime as dt

from app.reclame.gardian import Context, verifica

ACUM = dt.datetime(2026, 11, 17, 12, tzinfo=dt.UTC)


def ctx(**kw: object) -> Context:
    baza: dict[str, object] = {
        "plafon_zilnic_bani": 10_000,
        "plafon_lunar_bani": 300_000,
        "plafon_campanie_bani": 8_000,
        "schimbare_max_pct": 20,
        "asteptare_ore": 48,
        "schimbari_pe_zi": 5,
        "suma_active_bani": 1_600,
        "cheltuit_luna_bani": 50_000,
        "zile_ramase": 14,
        "schimbari_automate_azi": 0,
        "ultima_schimbare": ACUM - dt.timedelta(days=3),
        "reclame_oprite": False,
        "acum": ACUM,
    }
    return Context(**(baza | kw))  # type: ignore[arg-type]


ACTIVA = {"stare": "activa", "buget_zilnic_bani": 6_000}


def test_peste_plafon_e_refuzat_si_cere_clientul() -> None:
    v = verifica("buget", ACTIVA, {"buget_zilnic_bani": 9_000}, "om", ctx())
    assert not v.permis and v.cere_client and "plafonul pe campanie" in v.motive[0]
    v = verifica("buget", ACTIVA, {"buget_zilnic_bani": 7_000}, "om", ctx(suma_active_bani=4_000))
    assert not v.permis and any("plafonul zilnic" in m for m in v.motive)
    v = verifica(
        "stare",
        {"stare": "pauza", "buget_zilnic_bani": 6_000},
        {"stare": "activa"},
        "om",
        ctx(cheltuit_luna_bani=250_000),
    )
    assert not v.permis and any("plafonul lunar" in m for m in v.motive)


def test_ritmul() -> None:
    assert verifica("buget", ACTIVA, {"buget_zilnic_bani": 7_200}, "strateg", ctx()).permis
    v = verifica("buget", ACTIVA, {"buget_zilnic_bani": 7_300}, "strateg", ctx())
    assert not v.permis and "20%" in v.motive[0] and not v.cere_client
    v = verifica(
        "buget",
        ACTIVA,
        {"buget_zilnic_bani": 6_500},
        "regula",
        ctx(ultima_schimbare=ACUM - dt.timedelta(hours=5)),
    )
    assert not v.permis and "așteptare" in v.motive[0]
    v = verifica("buget", ACTIVA, {"buget_zilnic_bani": 6_500}, "regula", ctx(schimbari_automate_azi=5))
    assert not v.permis and "automate" in v.motive[0]
    assert verifica("buget", ACTIVA, {"buget_zilnic_bani": 6_500}, "om", ctx(schimbari_automate_azi=5)).permis


def test_scutiri_pauza_scadere_anulare_si_oprirea() -> None:
    oprit = ctx(reclame_oprite=True, suma_active_bani=50_000)
    assert verifica("stare", ACTIVA, {"stare": "pauza"}, "urgenta", oprit).permis
    assert verifica(
        "buget", ACTIVA, {"buget_zilnic_bani": 1_000}, "regula", ctx(ultima_schimbare=ACUM)
    ).permis
    assert verifica(
        "buget", ACTIVA, {"buget_zilnic_bani": 7_900}, "anulare", ctx(ultima_schimbare=ACUM)
    ).permis
    assert not verifica("buget", ACTIVA, {"buget_zilnic_bani": 9_000}, "anulare", ctx()).permis
    v = verifica("stare", {"stare": "pauza", "buget_zilnic_bani": 100}, {"stare": "activa"}, "om", oprit)
    assert not v.permis and "repornirea e manuală" in v.motive[0]
