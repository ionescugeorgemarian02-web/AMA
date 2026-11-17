"""Modulul analiza (F10): colectorul de metrici (K1) și raportul lunar.

from app import analiza

analiza.colector.colecteaza()                       # jobul `analiza.colector`, la 10 minute
analiza.colector.ale_livrabilului(db, livrabil_id)  # citirile pe intervale ale unei postări
"""

from app.analiza import colector, etichete, raport_lunar, retentie, sanatate, trafic
from app.analiza.modele import CurbaRetentie, EtichetePostare, MetriciPostare

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
