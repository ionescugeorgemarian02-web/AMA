"""F10.8 — nucleele pure ale analistului de reclame: unghiul pe reguli, durata, citirea răspunsului, harta."""

import datetime as dt

from app.cercetare import reclame_concurenta as rc
from app.cercetare.reclame_concurenta import ReclamaObservata

AZI = dt.date(2026, 11, 14)


def test_unghiul_se_pune_pe_reguli() -> None:
    assert rc.unghi("Reducere 30% la toate sortimentele") == "pret"
    assert rc.unghi("Doar astăzi, ultimele locuri") == "urgenta"
    assert rc.unghi("Peste 2000 de clienți mulțumiți") == "dovada_sociala"
    assert rc.unghi("Cafea de specialitate, prăjită artizanal") == "calitate"
    assert rc.unghi("Livrare în 24 de ore") == "comoditate"
    assert rc.unghi("Bun venit la noi") == "altul"
    assert set(rc.ETICHETE_UNGHI) == {*rc.UNGHIURI, "altul"}


def test_durata_unei_reclame() -> None:
    assert rc.zile_rulare(dt.date(2026, 11, 14), None, AZI) == 1
    assert rc.zile_rulare(dt.date(2026, 8, 6), None, AZI) == 101, "încă rulează: până azi"
    assert rc.zile_rulare(dt.date(2026, 11, 1), dt.date(2026, 11, 10), AZI) == 10


def test_raspunsul_bibliotecii_sare_randurile_incomplete() -> None:
    corp = {
        "data": [
            {
                "id": "1",
                "ad_creative_bodies": ["Reducere la cafea"],
                "ad_delivery_start_time": "2026-08-06",
                "publisher_platforms": ["Facebook", "instagram"],
            },
            {"id": "2", "ad_creative_bodies": [], "ad_delivery_start_time": "2026-08-06"},
            {"id": "3", "ad_creative_bodies": ["Fără dată"]},
            {
                "id": "4",
                "ad_creative_bodies": ["Oprită"],
                "ad_delivery_start_time": "2026-10-01T00:00:00+0000",
                "ad_delivery_stop_time": "2026-10-20",
            },
        ]
    }
    r = rc.din_raspuns(corp)
    assert [(x.id_extern, x.ultima_livrare) for x in r] == [("1", None), ("4", dt.date(2026, 10, 20))]
    assert r[0].platforme == ("facebook", "instagram") and rc.din_raspuns({}) == []


def obs(unghi: str, prima: dt.date, ultima: dt.date | None = None) -> ReclamaObservata:
    return ReclamaObservata(unghi=unghi, prima_livrare=prima, ultima_livrare=ultima, text="x")


def test_harta_unghiurilor_si_spatiile_libere() -> None:
    randuri = [
        ("Prăjitoria Nordului", obs("pret", dt.date(2026, 8, 6))),
        ("Prăjitoria Nordului", obs("pret", dt.date(2026, 11, 1))),
        ("Cafeneaua Sud", obs("calitate", dt.date(2026, 10, 1), dt.date(2026, 10, 5))),
    ]
    h = rc.harta_din(randuri, AZI, top=2)
    assert h.pe_concurent == {"Prăjitoria Nordului": {"pret": 2}, "Cafeneaua Sud": {"calitate": 1}}
    assert [(c, z) for c, _, z in h.de_durata] == [("Prăjitoria Nordului", 101), ("Prăjitoria Nordului", 14)]
    assert "pret" not in h.spatii_libere and "garantie" in h.spatii_libere and h.reclame == 3
    assert rc.harta_din([], AZI).spatii_libere == [], "fără reclame observate nu se anunță spații libere"
