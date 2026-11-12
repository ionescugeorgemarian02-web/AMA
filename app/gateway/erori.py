"""Erorile tipizate ale gateway-ului. Apelantul prinde doar acestea; nicio eroare nu poartă cheia, adresa
cererii sau conținutul promptului (vezi `client`).

Toate sunt `EroareDefinitiva` pentru motor: un pas nu le reîncearcă orbește (reîncercarea cu pauză o face
gateway-ul însuși, pe furnizor). `Amanat` se tratează explicit: apelantul își reprogramează fluxul
(`gateway.reprogrameaza`), nu doarme.
"""

import datetime as dt

from app.operare.motor import EroareDefinitiva


class EroareGateway(EroareDefinitiva):
    """Baza erorilor gateway-ului."""


class Amanat(EroareGateway):
    """Apelul nu se poate face acum (cotă, furnizori opriți, politica profilului), dar se poate face mai
    târziu:
    `pana_la` este momentul (UTC) de la care merită reluat."""

    def __init__(self, pana_la: dt.datetime, motiv: str = "") -> None:
        super().__init__(pana_la, motiv)  # `args` reconstruiesc excepția la deserializare (pașii durabili)
        self.pana_la = pana_la
        self.motiv = motiv

    def __str__(self) -> str:
        return f"amânat până la {self.pana_la.isoformat()}" + (f" ({self.motiv})" if self.motiv else "")


class ApelRefuzat(EroareGateway):
    """Apelul nu are voie (oprire, buget, profil necunoscut, nicio variantă permisă). `cod` este stabil."""

    def __init__(self, cod: str, motiv: str = "") -> None:
        super().__init__(cod, motiv)
        self.cod = cod
        self.motiv = motiv

    def __str__(self) -> str:
        return f"apel refuzat: {self.cod}" + (f" ({self.motiv})" if self.motiv else "")


class IesireInvalida(EroareGateway):
    """Răspunsul nu respectă schema nici după reparație, pe niciun model din lanț."""


class FurnizoriIndisponibili(EroareGateway):
    """Lanțul s-a epuizat din cauza erorilor (nu a cotei) și profilul nu permite amânarea sau degradarea."""


class EroareFurnizor(Exception):
    """Eroarea unui singur apel la un furnizor, deja clasificată (7.5). Interioară gateway-ului."""

    def __init__(
        self, fel: str, *, status: int | None = None, detaliu: str = "", retry_dupa: float | None = None
    ):
        super().__init__(fel, status, detaliu, retry_dupa)
        self.fel = fel  # limita | server | retea | autentificare | cerere | continut
        self.status = status
        self.detaliu = detaliu
        self.retry_dupa = retry_dupa

    def __str__(self) -> str:
        return (
            f"{self.fel}"
            + (f" HTTP {self.status}" if self.status else "")
            + (f": {self.detaliu}" if self.detaliu else "")
        )


class NuSePoateActiva(EroareGateway):
    """Furnizorul nu poate fi activat (8.1): fără uz comercial confirmat sau fără cheie configurată."""
