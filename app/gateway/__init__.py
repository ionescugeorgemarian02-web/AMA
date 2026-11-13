"""Gateway-ul de modele (ADR-04, docs/08): singura cale a aplicației spre modelele de limbaj.

Orice apel la un model trece pe aici: `gateway.apeleaza(db, prompt=…, variabile=…, schema=…, tenant_id=…,
componenta=…,
prioritate=…)`. Garda `scripts/check_gateway.py` (în `make guards`) interzice adaptoarele, clientul
intern și adresele
furnizorilor în afara acestui pachet. Puncte de extensie: interceptori înainte / după apel
(`adauga_interceptor`),
profiluri și lanțuri ca date, adaptoare noi pe tip de API (F3.5), scorurile modelelor (F3.6).
"""

from app.gateway import bugete, evaluare, garda, inventar, jurnal, prompturi, registru, situatie
from app.gateway.amanare import cheie_reluare, reprogrameaza
from app.gateway.apel import ContextApel, Rezultat
from app.gateway.candidat import Candidat
from app.gateway.ceas import acum
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
from app.gateway.mascare import detecteaza as detecteaza_date_personale
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
from app.gateway.vectori import ModelVectori, vectorizeaza, vectorizeaza_cu_model
from app.gateway.vectori import dimensiune as dimensiune_vectori
from app.gateway.vectori import model_activ as model_vectori

bugete.inregistreaza()
garda.inregistreaza()

__all__ = [
    "INSTRUCTIUNE_DATE_EXTERNE",
    "Amanat",
    "Apel",
    "ApelContinut",
    "ApelRefuzat",
    "Candidat",
    "ContextApel",
    "EroareGateway",
    "Furnizor",
    "FurnizoriIndisponibili",
    "Iesire",
    "IesireInvalida",
    "Interceptor",
    "ModelLlm",
    "ModelVectori",
    "NuSePoateActiva",
    "PromptGateway",
    "Rezultat",
    "activeaza",
    "acum",
    "adauga_interceptor",
    "apeleaza",
    "bugete",
    "cheie_configurata",
    "cheie_reluare",
    "detecteaza_date_personale",
    "dezactiveaza",
    "dimensiune_vectori",
    "elimina_interceptor",
    "evaluare",
    "furnizor",
    "furnizori",
    "inventar",
    "jurnal",
    "marcheaza_extern",
    "model_vectori",
    "modele",
    "poate_fi_activat",
    "prompturi",
    "registru",
    "reprogrameaza",
    "situatie",
    "vectorizeaza",
    "vectorizeaza_cu_model",
]
