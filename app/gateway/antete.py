"""Citirea antetelor de limită ale furnizorilor (8.4: sursa de adevăr când există). Pur: fără rețea, fără
bază.

Forme întâlnite (normalizate într-un singur `AntetLimita`):
- `retry-after`: secunde sau dată HTTP (toți, pe 429 / 503);
- Groq și altele „compatibile”: `x-ratelimit-{limit,remaining,reset}-{requests,tokens}`, cu `reset` ca durată
  (`2m59.56s`, `7.66s`, `250ms`) sau secunde;
- OpenRouter: `x-ratelimit-limit`, `x-ratelimit-remaining`, `x-ratelimit-reset` (milisecunde de la epocă);
- Anthropic: `anthropic-ratelimit-{requests,tokens,input-tokens,output-tokens}-{limit,remaining,reset}`, cu
`reset`
  RFC 3339.
Un antet lipsă sau ilizibil este ignorat (niciodată o eroare: un antet ciudat nu are voie să strice un apel).
"""

import datetime as dt
import email.utils
import re
from collections.abc import Mapping

from app.gateway.tipuri import AntetLimita

DURATA = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")
UNITATI = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
MAXIM_SEC = 7 * 24 * 3600  # un reset mai îndepărtat de o săptămână e un antet stricat, nu o limită


def _intreg(valoare: str | None) -> int | None:
    if valoare is None:
        return None
    try:
        n = int(float(valoare.strip()))
    except ValueError:
        return None
    return n if n >= 0 else None


def durata_sec(valoare: str | None) -> float | None:
    """`'2m59.56s'` → 179.56; `'7.66s'`; `'250ms'`; `'30'` (secunde). `None` dacă nu se înțelege."""
    if not valoare:
        return None
    v = valoare.strip().lower()
    try:
        return _plafon(float(v))
    except ValueError:
        pass
    gasite = DURATA.findall(v)
    if not gasite or "".join(n + u for n, u in gasite) != v:
        return None
    return _plafon(sum(float(n) * UNITATI[u] for n, u in gasite))


def _plafon(sec: float) -> float | None:
    return sec if 0 <= sec <= MAXIM_SEC else None


def _moment_rfc3339(valoare: str | None) -> dt.datetime | None:
    if not valoare:
        return None
    try:
        t = dt.datetime.fromisoformat(valoare.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.UTC)


def retry_after(valoare: str | None, acum: dt.datetime) -> float | None:
    """Secunde de așteptat din `Retry-After` (număr de secunde sau dată HTTP)."""
    if not valoare:
        return None
    sec = durata_sec(valoare)
    if sec is not None:
        return sec
    try:
        t = email.utils.parsedate_to_datetime(valoare)
    except (TypeError, ValueError):
        return None
    t = t if t.tzinfo else t.replace(tzinfo=dt.UTC)
    return _plafon(max(0.0, (t - acum).total_seconds()))


def _reset(valoare: str | None, acum: dt.datetime) -> dt.datetime | None:
    """Un reset poate fi durată, RFC 3339 sau milisecunde de la epocă."""
    if not valoare:
        return None
    v = valoare.strip()
    if v.isdigit() and len(v) >= 12:  # milisecunde de la epocă (OpenRouter)
        try:
            t = dt.datetime.fromtimestamp(int(v) / 1000, dt.UTC)
        except (OverflowError, OSError, ValueError):
            return None
        return t if 0 <= (t - acum).total_seconds() <= MAXIM_SEC else None
    moment = _moment_rfc3339(v) if ("-" in v and ":" in v) else None
    if moment is not None:
        return moment
    sec = durata_sec(v)
    return None if sec is None else acum + dt.timedelta(seconds=sec)


def citeste(antete: Mapping[str, str], acum: dt.datetime) -> AntetLimita:
    """Normalizează antetele unui răspuns (chei în orice literă)."""
    h = {k.lower(): v for k, v in antete.items()}

    def primul(*chei: str) -> str | None:
        return next((h[c] for c in chei if c in h), None)

    return AntetLimita(
        ramas_cereri=_intreg(
            primul(
                "x-ratelimit-remaining-requests",
                "anthropic-ratelimit-requests-remaining",
                "x-ratelimit-remaining",
            )
        ),
        ramas_tokeni=_intreg(
            primul(
                "x-ratelimit-remaining-tokens",
                "anthropic-ratelimit-tokens-remaining",
                "anthropic-ratelimit-input-tokens-remaining",
            )
        ),
        limita_cereri=_intreg(
            primul("x-ratelimit-limit-requests", "anthropic-ratelimit-requests-limit", "x-ratelimit-limit")
        ),
        limita_tokeni=_intreg(
            primul(
                "x-ratelimit-limit-tokens",
                "anthropic-ratelimit-tokens-limit",
                "anthropic-ratelimit-input-tokens-limit",
            )
        ),
        reset_cereri_la=_reset(
            primul("x-ratelimit-reset-requests", "anthropic-ratelimit-requests-reset", "x-ratelimit-reset"),
            acum,
        ),
        reset_tokeni_la=_reset(
            primul(
                "x-ratelimit-reset-tokens",
                "anthropic-ratelimit-tokens-reset",
                "anthropic-ratelimit-input-tokens-reset",
            ),
            acum,
        ),
        retry_dupa_sec=retry_after(primul("retry-after"), acum),
    )
