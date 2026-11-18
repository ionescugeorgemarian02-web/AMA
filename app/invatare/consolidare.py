"""Consolidarea nocturnă a memoriei de performanță (F14.6, docs/10 §10.4, docs/11 §11.3): playbook-ul fiecărui
client rămâne fără dubluri, iar lecțiile nefolosite ies din rotația activă.

- **Duplicatele:** lecțiile active sau propuse ale aceluiași client, pe același domeniu, cu același text după
  normalizare (fără diacritice, majuscule, punctuație și spații în plus) sunt aceeași lecție. Rămâne una:
  cea activă aprobată cel mai recent de om (§10.4: la conflict câștigă cea aprobată mai recent); fără activă,
  cea mai veche propunere. Contoarele „a ajutat” / „a dăunat” se adună în ea, dovezile o notează; celelalte
  ies (`retrasa` dacă erau active, `respinsa` dacă erau propuse), cu motiv și audit.
- **Rotația:** o lecție activă nefolosită de `ZILE_ROTATIE` (90) zile (ultima folosire din `lectii_folosite`;
  fără folosire, de la aprobare) se retrage: nu mai intră în context. Rămâne în istoric (memoria păstrează și
  eșecurile), deci se poate reaproba.
- Rulează pe fiecare client, în sesiunea lui, ca flux de învățare (Constituția); urme pe client.
"""

import datetime as dt
import re
import unicodedata
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import sesiune_agentie, sesiune_tenant
from app.invatare import constitutie
from app.invatare.modele import Lectie, LectieFolosita
from app.logging import get_logger
from app.operare import audit, motor, urme

log = get_logger("app.invatare.consolidare")
NUME = "invatare.consolidare"
ZILE_ROTATIE = 90


def normalizeaza(text: str) -> str:
    fara = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", fara.lower()).strip()


def grupuri_duplicate(lectii: list[Any]) -> list[list[Any]]:
    """Nucleu pur: grupurile cu mai mult de o lecție, fiecare cu păstrata pe primul loc."""
    grupuri: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
    for r in lectii:
        grupuri[(r.domeniu_tip, r.domeniu, normalizeaza(r.text))].append(r)
    out = []
    for g in grupuri.values():
        if len(g) > 1:
            active = sorted(
                (r for r in g if r.stare == "activa"), key=lambda r: r.decis_la or r.creat_la, reverse=True
            )
            prima = active[0] if active else min(g, key=lambda r: r.creat_la)
            out.append([prima, *(r for r in g if r is not prima)])
    return out


def _iese(db: Session, r: Lectie, stare: str, motiv: str, actiune: str, acum: dt.datetime) -> None:
    r.stare, r.motiv, r.actualizat_la = stare, motiv[:300], acum
    db.flush()
    audit.record(
        db, actiune, obiect_tip="lectie", obiect_id=r.id, tenant_id=r.tenant_id, actor_tip="sistem",
        detalii={"lectie": r.cheie, "motiv": motiv[:120]},
    )  # fmt: skip


def consolideaza(db: Session, tenant_id: uuid.UUID, *, acum: dt.datetime | None = None) -> dict[str, int]:
    acum = acum or dt.datetime.now(dt.UTC)
    with urme.span(NUME, "consolideaza", db=db, obiect_tip="client", obiect_id=tenant_id) as s, \
            constitutie.flux_invatare(db):  # fmt: skip
        lectii = list(
            db.execute(
                select(Lectie).where(Lectie.tenant_id == tenant_id, Lectie.stare.in_(("activa", "propusa")))
            ).scalars()
        )
        unite = 0
        for pastrata, *dubluri in grupuri_duplicate(lectii):
            for d in dubluri:
                pastrata.a_ajutat += d.a_ajutat
                pastrata.a_daunat += d.a_daunat
                pastrata.dovezi = [
                    *pastrata.dovezi,
                    {"tip": "unire", "lectie": d.cheie, "la": acum.isoformat()},
                ]
                stare = "retrasa" if d.stare == "activa" else "respinsa"
                _iese(db, d, stare, f"duplicat, unit în {pastrata.cheie}", "invatare.lectie_unita", acum)
                unite += 1
            pastrata.actualizat_la = acum
        ultima = (
            select(LectieFolosita.lectie_id, func.max(LectieFolosita.folosita_la).label("la"))
            .group_by(LectieFolosita.lectie_id)
            .subquery()
        )
        limita = acum - dt.timedelta(days=ZILE_ROTATIE)
        vechi = db.execute(
            select(Lectie)
            .outerjoin(ultima, ultima.c.lectie_id == Lectie.id)
            .where(
                Lectie.tenant_id == tenant_id,
                Lectie.stare == "activa",
                func.coalesce(ultima.c.la, Lectie.decis_la, Lectie.creat_la) < limita,
            )
        ).scalars()
        scoase = 0
        for r in vechi:
            _iese(db, r, "retrasa", f"nefolosită de {ZILE_ROTATIE} de zile: iese din rotație",
                  "invatare.lectie_scoasa_din_rotatie", acum)  # fmt: skip
            scoase += 1
        rez = {"unite": unite, "scoase": scoase, "verificate": len(lectii)}
        s.iesiri = rez
        s.rezultat = "ok" if unite or scoase else "info"
        return rez


def ruleaza(acum: dt.datetime | None = None) -> dict[str, int]:
    """Rularea nocturnă, pe fiecare client cu lecții active sau propuse."""
    with sesiune_agentie() as db:
        clienti = list(
            db.execute(
                select(Lectie.tenant_id).where(Lectie.stare.in_(("activa", "propusa"))).distinct()
            ).scalars()
        )
    total = {"unite": 0, "scoase": 0}
    for t in clienti:
        try:
            with sesiune_tenant(t) as db:
                r = consolideaza(db, t, acum=acum)
            total = {k: total[k] + r[k] for k in total}
        except Exception as exc:
            log.warning("consolidare eșuată", extra={"tip_eroare": type(exc).__name__})
    return total


@motor.pas("invatare.pas_consolidare")
def _pas() -> str:
    r = ruleaza()
    return f"{r['unite']} unite, {r['scoase']} scoase"


@motor.flux(NUME)
def flux(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _pas()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME, "10 3 * * *", flux)


declara_programari()
