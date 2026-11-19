"""Modulul analiza (F10): colectorul de metrici (K1) și raportul lunar.

from app import analiza

analiza.colector.colecteaza()                       # jobul `analiza.colector`, la 10 minute
analiza.colector.ale_livrabilului(db, livrabil_id)  # citirile pe intervale ale unei postări
"""

# Ordinea contează: `app.invatare` (importat de colector / raport) cere `EtichetePostare` și `etichete`
# din pachetul încă parțial inițializat.
from app.analiza.modele import CurbaRetentie, EtichetePostare, MetriciPostare  # isort: skip
from app.analiza import etichete  # isort: skip
from app.analiza import colector, raport_lunar, retentie, sanatate, trafic  # isort: skip

__all__ = [
    "CurbaRetentie",
    "EtichetePostare",
    "MetriciPostare",
    "colector",
    "etichete",
    "raport_lunar",
    "retentie",
    "sanatate",
    "trafic",
]
