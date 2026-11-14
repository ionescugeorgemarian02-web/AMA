"""Adaptorul motorului de audit (F7.2): auditul îl face motorul din BigBrain, prin rețea.

Contract: `ruleaza(firma, site_url) -> dict` cu `rezumat`, `constatari` (listă) și `recomandari` (exact 3).
`MotorAuditSimulat` (# SIMULAT) întoarce un raport determinist, fără rețea; adaptorul HTTP spre BigBrain
(`AMA_AUDIT_MOTOR=bigbrain`, adresa și cheia lui) e o resursă externă: NEVERIFICAT, la migrare."""

from typing import Any, Protocol
from urllib.parse import urlsplit

from app.config import get_settings


class EroareAudit(RuntimeError):
    pass


class MotorAudit(Protocol):
    nume: str

    def ruleaza(self, firma: str, site_url: str) -> dict[str, Any]: ...


class MotorAuditSimulat:
    """# SIMULAT: raportul de probă al motorului de audit."""

    nume = "simulat"

    def ruleaza(self, firma: str, site_url: str) -> dict[str, Any]:
        gazda = urlsplit(site_url).hostname or site_url
        return {
            "rezumat": (
                f"{firma}: site-ul {gazda} spune ce vinzi, dar nu spune de ce ești alegerea potrivită."
            ),
            "constatari": [
                "Oferta principală apare abia pe a doua pagină.",
                "Prețurile nu sunt ușor de găsit de pe telefon.",
                "Nu există un apel la acțiune clar pe prima pagină.",
            ],
            "recomandari": [
                "Pune oferta principală și prețul de pornire pe prima pagină.",
                "Adaugă un singur buton de contact, vizibil pe telefon.",
                "Publică săptămânal o postare cu o întrebare frecventă a clienților.",
            ],
        }


_motor: MotorAudit | None = None


def motor() -> MotorAudit:
    global _motor
    if _motor is None:
        if get_settings().audit_motor != "simulat":
            raise EroareAudit("motorul de audit real se configurează la migrare")  # NEVERIFICAT
        _motor = MotorAuditSimulat()
    return _motor


def seteaza(m: MotorAudit | None) -> None:
    global _motor
    _motor = m
