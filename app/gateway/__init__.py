"""Gateway-ul de modele (ADR-04, docs/08): singura cale a aplicației spre modelele de limbaj.

Orice apel la un model trece pe aici: `gateway.apeleaza(db, prompt=…, variabile=…, schema=…, tenant_id=…,
componenta=…,
prioritate=…)`. Garda `scripts/check_gateway.py` (în `make guards`) interzice adaptoarele, clientul
intern și adresele
furnizorilor în afara acestui pachet. Puncte de extensie: interceptori înainte / după apel
(`adauga_interceptor`),
profiluri și lanțuri ca date, adaptoare noi pe tip de API (F3.5), scorurile modelelor (F3.6).
"""

from app.gateway import bugete, garda, inventar, jurnal, prompturi, registru
from app.gateway.amanare import cheie_reluare, reprogrameaza
from app.gateway.apel import ContextApel, Rezultat
from app.gateway.erori import (
    Amanat,
    ApelRefuzat,
    EroareGateway,
    FurnizoriIndisponibili,
    IesireInvalida,
    NuSePoateActiva,
)
from app.gateway.extern import INSTRUCTIUNE as INSTRUCTIUNE_DATE_EXTERNE
from app.gateway.extern import marcheaza_extern
from app.gateway.iesire import Iesire
from app.gateway.interceptori import Interceptor
from app.gateway.interceptori import adauga as adauga_interceptor
from app.gateway.interceptori import elimina as elimina_interceptor
from app.gateway.modele import Apel, ApelContinut, Furnizor, ModelLlm, PromptGateway
from app.gateway.registru import (
    activeaza,
    cheie_configurata,
    dezactiveaza,
    furnizor,
    furnizori,
    modele,
    poate_fi_activat,
)
from app.gateway.serviciu import apeleaza

bugete.inregistreaza()
garda.inregistreaza()

__all__ = [
    "INSTRUCTIUNE_DATE_EXTERNE",
    "Amanat",
    "Apel",
    "ApelContinut",
    "ApelRefuzat",
    "ContextApel",
    "EroareGateway",
    "Furnizor",
    "FurnizoriIndisponibili",
    "Iesire",
    "IesireInvalida",
    "Interceptor",
    "ModelLlm",
    "NuSePoateActiva",
    "PromptGateway",
    "Rezultat",
    "activeaza",
    "adauga_interceptor",
    "apeleaza",
    "bugete",
    "cheie_configurata",
    "cheie_reluare",
    "dezactiveaza",
    "elimina_interceptor",
    "furnizor",
    "furnizori",
    "inventar",
    "jurnal",
    "marcheaza_extern",
    "modele",
    "poate_fi_activat",
    "prompturi",
    "registru",
    "reprogrameaza",
]
