"""Indicatorii pe componentă (FT.3): volum, rezultate, rata de eșec, cost, durate p50/p95, coduri."""
# ruff: noqa: S608  (FILTRU e o constantă a modulului; valorile merg doar ca parametri legați)

import datetime as dt
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

RELE = ("esec", "respins", "blocat")


@dataclass(frozen=True)
class Indicator:
    componenta: str
    total: int
    pe_rezultat: dict[str, int]
    cost: dict[str, Decimal]
    durata_p50_ms: float | None
    durata_p95_ms: float | None
    coduri: list[tuple[str, int]] = field(default_factory=list)

    @property
    def rele(self) -> int:
        return sum(self.pe_rezultat.get(r, 0) for r in RELE)

    @property
    def rata_esec(self) -> float:
        """Partea urmelor rele (eșec, respins, blocat) din cele cu verdict (fără `info`)."""
        cu_verdict = self.total - self.pe_rezultat.get("info", 0)
        return round(self.rele / cu_verdict, 4) if cu_verdict else 0.0

    def ca_dict(self) -> dict[str, object]:
        return {
            "componenta": self.componenta, "total": self.total, "pe_rezultat": self.pe_rezultat,
            "rata_esec": self.rata_esec, "cost": {k: float(v) for k, v in self.cost.items()},
            "durata_p50_ms": self.durata_p50_ms, "durata_p95_ms": self.durata_p95_ms,
            "coduri": [list(c) for c in self.coduri],
        }  # fmt: skip


FILTRU = (
    "la >= :de_la AND la < :pana_la AND (CAST(:tenant AS uuid) IS NULL OR tenant_id = CAST(:tenant AS uuid))"
)


def calculeaza(
    db: Session, de_la: dt.datetime, pana_la: dt.datetime, *, tenant_id: uuid.UUID | None = None
) -> list[Indicator]:
    """Indicatorii fiecărei componente în `[de_la, pana_la)`, ordonați după volum. RLS decide ce se vede."""
    p = {"de_la": de_la, "pana_la": pana_la, "tenant": tenant_id}
    baza = db.execute(
        text(
            f"SELECT componenta, count(*), percentile_cont(0.5) WITHIN GROUP (ORDER BY durata_ms), "
            "percentile_cont(0.95) WITHIN GROUP (ORDER BY durata_ms) "
            f"FROM urme WHERE {FILTRU} GROUP BY componenta"
        ),
        p,
    ).all()
    rezultate: dict[str, dict[str, int]] = {}
    for c, r, n in db.execute(
        text(f"SELECT componenta, rezultat, count(*) FROM urme WHERE {FILTRU} GROUP BY 1, 2"), p
    ):
        rezultate.setdefault(c, {})[r] = n
    costuri: dict[str, dict[str, Decimal]] = {}
    for c, u, s in db.execute(
        text(
            f"SELECT componenta, unitate_cost, sum(cost) FROM urme WHERE {FILTRU} AND cost > 0 GROUP BY 1, 2"
        ),
        p,
    ):
        costuri.setdefault(c, {})[u] = Decimal(s)
    coduri: dict[str, list[tuple[str, int]]] = {}
    for c, cod, n in db.execute(
        text(
            f"SELECT componenta, cod, count(*) FROM urme WHERE {FILTRU} AND cod <> '' "
            "AND rezultat IN ('esec', 'respins', 'blocat', 'amanat') GROUP BY 1, 2 ORDER BY 3 DESC, 2"
        ),
        p,
    ):
        if len(coduri.setdefault(c, [])) < 5:
            coduri[c].append((cod, n))
    out = [
        Indicator(
            c,
            n,
            rezultate.get(c, {}),
            costuri.get(c, {}),
            None if p50 is None else float(p50),
            None if p95 is None else float(p95),
            coduri.get(c, []),
        )
        for c, n, p50, p95 in baza
    ]
    return sorted(out, key=lambda i: (-i.total, i.componenta))
