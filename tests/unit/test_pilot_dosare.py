"""Datele de pilot acoperă porțile reale de onboarding pentru ambele tipuri de client."""

from app.onboarding import citate, interviu, piata
from tests.pilot_clienti import CAZURI


def test_dosarele_sustin_onboardingul_din_informatii_brute() -> None:
    for dosar in CAZURI.values():
        assert set(dosar.raspunsuri) == {q.cod for q in interviu.intrebari()}
        assert len(set(dosar.recenzii)) >= citate.MINIM_CITATE
        assert piata.MIN_CONCURENTI <= len(dosar.concurenti) <= piata.MAX_CONCURENTI
        assert dosar.pret in dosar.raspunsuri["preturi"]
        assert dosar.produs in dosar.raspunsuri["preturi"]
