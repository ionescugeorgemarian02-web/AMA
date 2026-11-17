"""Trasabilitatea totală (faza FT): jurnalul unic de urme, append-only, cu fir de corelare și cauză.

from app.operare import urme
with urme.span("gateway", "apel", tenant_id=t, intrari={...}) as s:
    ...; s.cost, s.unitate_cost = pret, "usd_umbra"
urme.inregistreaza(db, "aprobare", "respinsa", rezultat="respins", motiv=motiv, obiect_id=ap.id)
"""

from app.operare.urme.jurnal import (
    REZULTATE,
    Span,
    active,
    actor_curent,
    cauza_curenta,
    corelare,
    corelare_curenta,
    emite,
    inregistreaza,
    span,
    tenant_curent,
)
from app.operare.urme.modele import Urma
from app.operare.urme.rezumat import mascheaza, rezuma

__all__ = [
    "REZULTATE",
    "Span",
    "Urma",
    "active",
    "actor_curent",
    "cauza_curenta",
    "corelare",
    "corelare_curenta",
    "emite",
    "inregistreaza",
    "mascheaza",
    "rezuma",
    "span",
    "tenant_curent",
]
