"""Aduce prompturile versionate din `prompts/` în registrul gateway-ului (idempotent), când un judecător nu
găsește
promptul cerut."""

from pathlib import Path

from app import gateway
from app.db import sesiune_agentie

DIRECTOR = Path(__file__).resolve().parents[2] / "prompts"


def asigura() -> list[str]:
    with sesiune_agentie() as db:
        return gateway.prompturi.sincronizeaza(db, DIRECTOR)
