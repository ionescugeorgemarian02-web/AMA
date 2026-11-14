"""Modulul analiza (F10): colectorul de metrici (K1) și raportul lunar.

from app import analiza

analiza.colector.colecteaza()                       # jobul `analiza.colector`, la 10 minute
analiza.colector.ale_livrabilului(db, livrabil_id)  # citirile pe intervale ale unei postări
"""

from app.analiza import colector, raport_lunar, retentie
from app.analiza.modele import CurbaRetentie, MetriciPostare

__all__ = ["CurbaRetentie", "MetriciPostare", "colector", "raport_lunar", "retentie"]
