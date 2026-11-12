"""Gateway-ul de modele (ADR-04, docs/08): singura cale a aplicației spre modelele de limbaj.

Orice apel la un model trece pe aici; garda `scripts/check_gateway.py` (în `make guards`) interzice
adaptoarele,
clientul intern și adresele furnizorilor în afara acestui pachet. API-ul public se completează pe pași
(F3.1–F3.7).
"""

from app.gateway import inventar, registru
from app.gateway.amanare import cheie_reluare, reprogrameaza
from app.gateway.erori import (
    Amanat,
    ApelRefuzat,
    EroareGateway,
    FurnizoriIndisponibili,
    IesireInvalida,
    NuSePoateActiva,
)
from app.gateway.iesire import Iesire
from app.gateway.modele import Furnizor, ModelLlm
from app.gateway.registru import (
    activeaza,
    cheie_configurata,
    dezactiveaza,
    furnizor,
    furnizori,
    modele,
    poate_fi_activat,
)

__all__ = [
    "Amanat",
    "ApelRefuzat",
    "EroareGateway",
    "Furnizor",
    "FurnizoriIndisponibili",
    "Iesire",
    "IesireInvalida",
    "ModelLlm",
    "NuSePoateActiva",
    "activeaza",
    "cheie_configurata",
    "cheie_reluare",
    "dezactiveaza",
    "furnizor",
    "furnizori",
    "inventar",
    "modele",
    "poate_fi_activat",
    "registru",
    "reprogrameaza",
]
