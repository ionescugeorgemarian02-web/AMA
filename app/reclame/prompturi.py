"""Aduce prompturile versionate din `prompts/` în registrul gateway-ului (idempotent), înainte de un apel."""

from pathlib import Path

from app import gateway
from app.db import sesiune_agentie

DIRECTOR = Path(__file__).resolve().parents[2] / "prompts"


def asigura() -> list[str]:
    with sesiune_agentie() as db:
        return gateway.prompturi.sincronizeaza(db, DIRECTOR)
