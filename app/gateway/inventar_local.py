"""Sămânța modelului local și a modelului de vectori (F3.5), ca DATE (migrarea `0018`). Totul `[I]`:
presupuneri de proiectare, NEVERIFICATE (identificatori de modele, mărimi, licențe, prețuri-umbră). Se
confirmă la F0.3 și la migrarea pe VPS.

Serverele rulează în rețeaua internă (compose, profilul `local-llm`): adresele sunt nume de servicii, fără
cheie. Furnizorul local pornește `inactiv` și cu `uz_comercial` necunoscut: licența modelului ales se
confirmă înainte de activare.
"""

from typing import Any

FURNIZORI: tuple[dict[str, Any], ...] = (
    {
        "cod": "local",
        "nume": "Model local de text (llama.cpp / Ollama)",
        "tip_api": "local",
        "url_baza": "http://local-llm:8080/v1",
        "cheie_env": "AMA_CHEIE_LOCAL",
        "platit": False,
        "uz_comercial": None,
        "antrenare_pe_date": False,
        "note": "Server separat în rețeaua internă, model ținut încărcat; generarea ocupă un culoar greu. "
        "Licența modelului ales trebuie confirmată înainte de activare.",
        "parametri": {"timeout_sec": 600},
    },
    {
        "cod": "vectori",
        "nume": "Model de vectori (server separat)",
        "tip_api": "local",
        "url_baza": "http://embeddings:8081/v1",
        "cheie_env": "AMA_CHEIE_VECTORI",
        "platit": False,
        "uz_comercial": None,
        "antrenare_pe_date": False,
        "note": "Model multilingv mic, pe propriul server, în afara culoarelor grele.",
        "parametri": {"timeout_sec": 60},
    },
)

# (furnizor, identificator, nume, context, capabilități, dimensiune vector, preț-umbră intrare / ieșire
# la 1 mil.)
MODELE: tuple[tuple[str, str, str, int, tuple[str, ...], int | None, float, float], ...] = (
    (
        "local",
        "qwen2.5-3b-instruct-q4_k_m",
        "Local 3B (cuantizat)",
        8192,
        ("iesire_structurata",),
        None,
        0.05,
        0.15,
    ),
    (
        "local",
        "qwen2.5-7b-instruct-q4_k_m",
        "Local 7B (cuantizat)",
        8192,
        ("iesire_structurata",),
        None,
        0.10,
        0.30,
    ),
    (
        "local",
        "gemma-2-9b-it-q4_k_m",
        "Local 9B (cuantizat)",
        8192,
        ("iesire_structurata",),
        None,
        0.15,
        0.45,
    ),
    ("vectori", "multilingual-e5-small", "Vectori multilingv mic", 512, ("embeddings",), 384, 0.0, 0.0),
)
