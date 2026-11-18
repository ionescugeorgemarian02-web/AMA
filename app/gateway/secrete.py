"""Secretele furnizorilor (G-pool): de unde se citesc și când e un furnizor complet.

Ordinea pentru fiecare nume din `catalog.PROVIDER_SECRETS`: variabila de mediu cu numele EXACT, apoi seiful
(`seif.py`). Pentru cheia de API (primul secret) mai e acceptat și numele vechi al registrului (`AMA_CHEIE_*`,
coloana `cheie_env`), ca instalările existente (de exemplu OpenRouter cu `AMA_CHEIE_OPENROUTER`) să meargă la
fel. Un furnizor din catalog fără TOATE secretele e dezactivat automat: rutarea îl sare (`fara_cheie`).

Valorile se citesc doar aici și se dau clientului la trimitere; nu se loghează și nu se afișează.
"""

import dataclasses
import os
import re

from app.gateway import seif
from app.gateway.candidat import Candidat
from app.gateway.catalog import NUME_SECRETE, POOL, PROVIDER_SECRETS

NUME_VECHI = re.compile(r"^AMA_CHEIE_[A-Z0-9_]{1,40}$")


def citeste_cheie_env(nume_variabila: str) -> str | None:
    """Valoarea unei variabile `AMA_CHEIE_*` (numele vechi din registru); orice alt nume e refuzat."""
    if not NUME_VECHI.match(nume_variabila):
        return None
    valoare = os.environ.get(nume_variabila, "").strip()
    return valoare or None


def citeste(nume: str) -> str | None:
    """Valoarea unui secret din catalog: mediul, apoi seiful. Alte nume nu se citesc."""
    if nume not in NUME_SECRETE:
        return None
    valoare = os.environ.get(nume, "").strip()
    return valoare or seif.citeste(nume)


def cheie(furnizor: str, cheie_env: str = "") -> str | None:
    """Cheia de API a furnizorului (antetul cererii): primul secret din catalog, apoi numele vechi."""
    secrete = PROVIDER_SECRETS.get(furnizor, ())
    valoare = citeste(secrete[0]) if secrete else None
    return valoare or (citeste_cheie_env(cheie_env) if cheie_env else None)


def lipsa(furnizor: str, cheie_env: str = "") -> list[str]:
    """Numele secretelor care lipsesc (gol = furnizor complet). Pentru un furnizor necunoscut catalogului
    contează doar numele vechi din registru."""
    secrete = PROVIDER_SECRETS.get(furnizor)
    if secrete is None:
        return [] if cheie_env and citeste_cheie_env(cheie_env) else [cheie_env or "cheie"]
    lipsesc = [] if cheie(furnizor, cheie_env) else [secrete[0]]
    return lipsesc + [s for s in secrete[1:] if citeste(s) is None]


def complet(furnizor: str, cheie_env: str = "") -> bool:
    return not lipsa(furnizor, cheie_env)


def completeaza(c: Candidat) -> Candidat:
    """Parametrii adresei luați din secrete (de exemplu `account_id` Cloudflare) și adresa de bază înlocuită
    când furnizorul o primește dintr-un secret (NVIDIA NIM). Un parametru deja setat în registru rămâne."""
    f = POOL.get(c.furnizor)
    if f is None:
        return c
    parametri = dict(c.parametri)
    for secret, parametru in f.parametri_din.items():
        if not parametri.get(parametru) and (v := citeste(secret)):
            parametri[parametru] = v
    url = c.url_baza
    if f.url_din and (v := citeste(f.url_din)) and v.startswith("https://"):
        url = v
    if parametri == c.parametri and url == c.url_baza:
        return c
    return dataclasses.replace(c, parametri=parametri, url_baza=url)
