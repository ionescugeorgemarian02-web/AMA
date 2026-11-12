"""F3.3 (citirea antetelor) — antetele de limită ale furnizorilor, în forma lor reală, se normalizează."""

import datetime as dt

import pytest

from app.gateway import antete
from app.gateway.tipuri import AntetLimita

ACUM = dt.datetime(2026, 11, 12, 12, 0, 0, tzinfo=dt.UTC)


@pytest.mark.parametrize(
    ("valoare", "asteptat"),
    [
        ("2m59.56s", 179.56),
        ("7.66s", 7.66),
        ("250ms", 0.25),
        ("1h2m", 3720.0),
        ("30", 30.0),
        ("0", 0.0),
        ("", None),
        ("abc", None),
        ("2x", None),
        ("-5", None),
        ("99999999", None),  # peste o săptămână: antet stricat
    ],
)
def test_durata(valoare: str, asteptat: float | None) -> None:
    rezultat = antete.durata_sec(valoare)
    assert rezultat == (pytest.approx(asteptat) if asteptat is not None else None)


def test_retry_after_in_secunde_si_ca_data_http() -> None:
    assert antete.retry_after("7", ACUM) == 7.0
    assert antete.retry_after("Thu, 12 Nov 2026 12:01:30 GMT", ACUM) == 90.0
    assert antete.retry_after("Thu, 12 Nov 2026 11:00:00 GMT", ACUM) == 0.0  # în trecut: nu mai așteptăm
    assert antete.retry_after("nu-stiu", ACUM) is None


def test_antete_in_stilul_groq() -> None:
    a = antete.citeste(
        {
            "x-ratelimit-limit-requests": "1000",
            "x-ratelimit-remaining-requests": "999",
            "x-ratelimit-limit-tokens": "12000",
            "X-RateLimit-Remaining-Tokens": "11800",
            "x-ratelimit-reset-requests": "1m26.4s",
            "x-ratelimit-reset-tokens": "7.66s",
        },
        ACUM,
    )
    assert (a.limita_cereri, a.ramas_cereri, a.limita_tokeni, a.ramas_tokeni) == (1000, 999, 12000, 11800)
    assert a.reset_cereri_la == ACUM + dt.timedelta(seconds=86.4)
    assert a.reset_tokeni_la == ACUM + dt.timedelta(seconds=7.66)


def test_antete_in_stilul_openrouter_reset_in_milisecunde_de_la_epoca() -> None:
    reset_ms = int((ACUM + dt.timedelta(seconds=45)).timestamp() * 1000)
    a = antete.citeste(
        {"X-RateLimit-Limit": "20", "X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset_ms)}, ACUM
    )
    assert (a.limita_cereri, a.ramas_cereri) == (20, 0)
    assert a.reset_cereri_la == ACUM + dt.timedelta(seconds=45)


def test_antete_in_stilul_anthropic_reset_rfc3339() -> None:
    a = antete.citeste(
        {
            "anthropic-ratelimit-requests-limit": "50",
            "anthropic-ratelimit-requests-remaining": "49",
            "anthropic-ratelimit-requests-reset": "2026-11-12T12:00:30Z",
            "anthropic-ratelimit-tokens-remaining": "39000",
            "retry-after": "30",
        },
        ACUM,
    )
    assert (a.limita_cereri, a.ramas_cereri, a.ramas_tokeni) == (50, 49, 39000)
    assert a.reset_cereri_la == dt.datetime(2026, 11, 12, 12, 0, 30, tzinfo=dt.UTC)
    assert a.retry_dupa_sec == 30.0


def test_antete_lipsa_sau_stricate_nu_dau_erori() -> None:
    assert antete.citeste({}, ACUM) == AntetLimita()
    a = antete.citeste(
        {"x-ratelimit-remaining-requests": "mult", "x-ratelimit-reset-requests": "curând"}, ACUM
    )
    assert a.gol
