"""Predictorul de performanță (F14.3, N6, docs/11 §11.2): șansa de succes a unei postări înainte de publicare,
doar peste pragul de date (`PRAG` publicări cu recompensă pe client și canal).

- **Datele trecute:** rândurile din `etichete_postari` ale clientului, pe canal, cu recompensa citită (F10.3).
  Succes = recompensa peste mediana perioadei de antrenare (primele 70%, în ordinea publicării).
- **Trăsăturile:** tiparul hook-ului, formatul, pilonul, unghiul, ziua săptămânii (categorii) și ora.
- **Gata:** pe testul din urmă, AUC-ul modelului bate alegerea la întâmplare cu marja măsurată (marginea de
  jos
  a intervalului bootstrap > `predictiv.MARJA`). Altfel `nu_bate` și nu se folosește la nimic.
- Datele unui client antrenează doar modelul lui (Constituția, punctul 7). Jobul săptămânal reîncearcă.
"""

import datetime as dt
import statistics
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analiza import EtichetePostare
from app.db import sesiune_agentie, sesiune_tenant
from app.invatare import predictiv
from app.invatare.modele import ModelPredictiv
from app.logging import get_logger
from app.operare import motor

log = get_logger("app.invatare.predictor")
NUME = "invatare.predictor"
PRAG = 500  # publicări cu recompensă pe client și canal (docs/11 §11.2: 500–1.000)


def trasaturi(r: Any) -> dict[str, Any]:
    return {"tipar_hook": r.tipar_hook or "-", "format": r.format or "-", "pilon": r.pilon or "-",
            "unghi": r.unghi or "-", "zi": str(r.zi_saptamana), "ora": float(r.ora)}  # fmt: skip


def exemple(randuri: list[Any]) -> list[predictiv.Exemplu]:
    """Nucleu pur: rânduri cu etichete și recompensă → exemple etichetate (succes = peste mediana
    antrenării)."""
    ordonate = sorted(randuri, key=lambda r: r.publicat_la)
    if not ordonate:
        return []
    taie = max(1, int(len(ordonate) * (1 - predictiv.FRACTIE_TEST)))
    mediana = statistics.median(float(r.recompensa) for r in ordonate[:taie])
    return [
        predictiv.Exemplu(trasaturi(r), int(float(r.recompensa) > mediana), r.publicat_la) for r in ordonate
    ]


def _randuri(db: Session, tenant_id: uuid.UUID, canal: str) -> list[EtichetePostare]:
    return list(
        db.execute(
            select(EtichetePostare).where(
                EtichetePostare.tenant_id == tenant_id,
                EtichetePostare.canal == canal,
                EtichetePostare.recompensa.is_not(None),
            )
        ).scalars()
    )


def ruleaza_client(
    db: Session, tenant_id: uuid.UUID, canal: str, *, prag: int = PRAG, acum: dt.datetime | None = None
) -> ModelPredictiv:
    return predictiv.ruleaza(
        db, tip="performanta", exemple=exemple(_randuri(db, tenant_id, canal)), prag=prag,
        referinta="intamplare",
        tenant_id=tenant_id, canal=canal, acum=acum,
    )  # fmt: skip


def sansa(db: Session, tenant_id: uuid.UUID, canal: str, etichete: dict[str, Any]) -> float | None:
    """Șansa de succes a unei postări planificate, doar dacă ultimul model al clientului pe canal e
    `valid`."""
    r = predictiv.ultimul(db, "performanta", tenant_id=tenant_id, canal=canal)
    return None if r is None else predictiv.prezice(r, etichete)


def ruleaza(acum: dt.datetime | None = None) -> int:
    """Jobul săptămânal: o încercare pe fiecare client și canal cu postări cu recompensă. Întoarce câte
    sunt valide."""
    with sesiune_agentie() as db:
        perechi = db.execute(
            select(EtichetePostare.tenant_id, EtichetePostare.canal)
            .where(EtichetePostare.recompensa.is_not(None))
            .group_by(EtichetePostare.tenant_id, EtichetePostare.canal)
            .having(func.count() > 0)
        ).all()
    valide = 0
    for tenant_id, canal in perechi:
        try:
            with sesiune_tenant(tenant_id) as db:
                valide += ruleaza_client(db, tenant_id, canal, acum=acum).stare == "valid"
        except Exception as exc:
            log.warning("predictor neantrenat", extra={"tip_eroare": type(exc).__name__})
    return valide


@motor.pas("invatare.pas_predictor")
def _pas() -> str:
    return str(ruleaza())


@motor.flux(NUME)
def flux(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _pas()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME, "30 3 * * 0", flux)


declara_programari()
