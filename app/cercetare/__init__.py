"""Cercetarea (docs/12): colectorul de surse (F4.2). Restul aplicației folosește doar ce se exportă aici:

    from app import cercetare

    with sesiune_tenant(t, u) as db:
        s = cercetare.creeaza_sursa(db, tenant_id=t, tip="site", statut_cod="site_client", nume="Site",
        url="https://…")
    colectare_id = cercetare.porneste_colectare(t, s.id)        # flux durabil pe coada `io`; apoi
    `cercetare.pagini(...)`
    cercetare.adauga_text(db, tenant_id=t, sursa_id=m.id, titlu="…", text="…")   # material lipit de un om
    cercetare.ca_continut_extern(document)                      # singura cale a textului colectat spre un
    prompt

Descărcarea de pagini este CITIRE, nu efect extern (AGENTS.md: efectele externe trec prin executor): trăiește
aici,
nu în `app/connectors/`, care rămâne rezervat conectorilor de publicare. Apărările (SSRF, robots.txt, limite)
sunt
în `ssrf`, `robots` și `descarcator`; vezi `docs/specs/F4.2.md`.
"""

from app.cercetare.colectare import (
    MOTIVE,
    ColectareInvalida,
    FormatNeacceptat,
    adauga_fisier,
    adauga_text,
    ca_continut_extern,
    creeaza_sursa,
    document,
    documente,
    dupa_colectare,
    motive_sarire,
    pagini,
    porneste_colectare,
    pregateste_colectare,
    stare_colectare,
    sursa,
    surse,
)
from app.cercetare.descarcator import Limite
from app.cercetare.modele import Colectare, Document, PaginaColectata, SursaColectare
from app.cercetare.statut import DOMENII_FARA_CRAWL, STATUTE, StatutSursa, SursaInterzisa

__all__ = [
    "DOMENII_FARA_CRAWL",
    "MOTIVE",
    "STATUTE",
    "Colectare",
    "ColectareInvalida",
    "Document",
    "FormatNeacceptat",
    "Limite",
    "PaginaColectata",
    "StatutSursa",
    "SursaColectare",
    "SursaInterzisa",
    "adauga_fisier",
    "adauga_text",
    "ca_continut_extern",
    "creeaza_sursa",
    "document",
    "documente",
    "dupa_colectare",
    "motive_sarire",
    "pagini",
    "porneste_colectare",
    "pregateste_colectare",
    "stare_colectare",
    "sursa",
    "surse",
]
