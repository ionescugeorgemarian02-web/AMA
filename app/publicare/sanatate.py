"""Gardianul sănătății conturilor (F9.8, docs/15 §15.7).

Rulează la oră (`publicare.sanatate`) peste conturile autorizate ale tuturor clienților:
- **tokenul aproape expirat** (sub `PRAG_EXPIRARE` [I]): întâi reîmprospătarea fără om, unde platforma o
  permite; altfel steagul „cere reautorizare” și o alertă (o singură dată), iar canalul trece pe asistat
  până la reautorizare (modul efectiv, F9.1);
- **o serie de erori** (ultimele `SERIE` efecte ale canalului eșuate, fără niciun succes între ele): canalul
se
  pune pe pauză (aceeași pauză ca la eroarea de autentificare: nimic nu pleacă până o ridică un om), cu
  alertă;
- **limitele**: citite de la platformă (endpoint sau antete, „nu ghicește”); aproape epuizate → alertă și
  instantaneul lor în cont, pentru ecranul „Publicare”.
Nu folosește proxy-uri, conturi multiple sau întârzieri care să ascundă automatizarea (15.7).
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import sesiune_agentie, sesiune_tenant
from app.logging import get_logger
from app.operare import audit, efecte, motor, notificari
from app.operare.efecte import autorizare
from app.operare.notificari import Nivel
from app.publicare import canale
from app.publicare.modele import ContCanal

log = get_logger("app.publicare.sanatate")
NUME = "publicare.sanatate"
PRAG_EXPIRARE = dt.timedelta(days=7)  # [I]
SERIE = 3  # [I] eșecuri consecutive


def serie_de_erori(stari: list[tuple[str, str | None]], n: int = SERIE) -> bool:
    """Nucleu pur: ultimele `n` efecte (cele mai noi primele: (stare, cod_eroare)) sunt toate eșecuri."""
    ultimele = stari[:n]
    return len(ultimele) == n and all(s != "trimis" and cod for s, cod in ultimele)


def _anunta(titlu: str, text: str) -> None:
    try:
        notificari.notifica(Nivel.IMPORTANT, titlu, text, url="/publicare")
    except Exception as exc:  # un canal de alertă căzut nu oprește gardianul
        log.warning("alertă netrimisă", extra={"tip_eroare": type(exc).__name__})


def _ultimele(db: Session, tenant_id: uuid.UUID, canal: str) -> list[tuple[str, str | None]]:
    return [
        (s, c)
        for s, c in db.execute(
            select(efecte.Efect.stare, efecte.Efect.eroare_cod)
            .where(efecte.Efect.tenant_id == tenant_id, efecte.Efect.canal == canal)
            .order_by(efecte.Efect.actualizat_la.desc())
            .limit(SERIE)
        ).all()
    ]


def verifica_contul(tenant_id: uuid.UUID, canal: str, acum: dt.datetime) -> list[str]:
    """Verificările unui cont; întoarce reacțiile (pentru jurnal și teste)."""
    reactii: list[str] = []
    with sesiune_tenant(tenant_id) as db:
        c = canale.cont(db, tenant_id, canal)
        if c is None or c.token_criptat is None:
            return reactii
        if c.expira_la is not None and c.expira_la - acum <= PRAG_EXPIRARE and not c.cere_reautorizare:
            if autorizare.reimprospateaza(db, tenant_id, canal):
                reactii.append("reimprospatat")
            elif canale.cere_reautorizare(db, tenant_id, canal, "tokenul expiră curând"):
                reactii.append("reautorizare")
                _anunta(
                    "Reautorizare necesară",
                    f"Contul „{c.nume or canal}” ({canal}) expiră în curând: reautorizează-l.",
                )
        if serie_de_erori(_ultimele(db, tenant_id, canal)) and autorizare.pune_pe_pauza(
            db, tenant_id, canal, f"{SERIE} eșecuri consecutive la publicare"
        ):
            reactii.append("pauza")
            audit.record(
                db,
                "publicare.canal_pauza",
                obiect_tip="canal",
                obiect_id=f"{tenant_id}:{canal}",
                tenant_id=tenant_id,
                actor_tip="sistem",
                rezultat="esec",
                detalii={"canal": canal, "motiv": "serie de erori"},
            )
            _anunta(
                "Canal pus pe pauză", f"Canalul {canal} a eșuat de {SERIE} ori la rând: verifică și reia."
            )
    try:
        lim = autorizare.limite(tenant_id, canal)
    except Exception as exc:  # limita necitită nu e o eroare a contului
        log.info("limite necitite", extra={"canal": canal, "tip_eroare": type(exc).__name__})
        return reactii
    instantaneu: dict[str, Any] = {
        "sursa": lim.sursa,
        "ramase": lim.ramase,
        "total": lim.total,
        "procent": lim.procent_folosit,
        "citit_la": acum.isoformat(),
    }
    with sesiune_tenant(tenant_id) as db:
        c = canale.cont(db, tenant_id, canal)
        if c is not None:
            c.setari = {**(c.setari or {}), "limite": instantaneu}
    if lim.aproape_epuizate:
        reactii.append("limite")
        _anunta(
            "Limită aproape atinsă", f"Canalul {canal}: {lim.sursa}. Publicarea încetinește până la resetare."
        )
    return reactii


def ruleaza(acum: dt.datetime | None = None) -> dict[str, list[str]]:
    acum = acum or dt.datetime.now(dt.UTC)
    with sesiune_agentie() as db:
        conturi = db.execute(
            select(ContCanal.tenant_id, ContCanal.canal).where(ContCanal.token_criptat.is_not(None))
        ).all()
    out: dict[str, list[str]] = {}
    for tenant_id, canal in conturi:
        if not canale.are_api(canal):
            continue
        try:
            r = verifica_contul(tenant_id, canal, acum)
        except Exception as exc:
            log.warning("cont neverificat", extra={"canal": canal, "tip_eroare": type(exc).__name__})
            continue
        if r:
            out[f"{tenant_id}:{canal}"] = r
    return out


@motor.pas("publicare.pas_sanatate")
def _pas() -> str:
    return str(ruleaza())


@motor.flux(NUME)
def flux(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _pas()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME, "17 * * * *", flux)


declara_programari()
