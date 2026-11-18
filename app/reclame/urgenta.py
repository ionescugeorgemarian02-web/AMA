"""Anomaliile și oprirea de urgență (F13.5, I6, docs/16 §16.5). Reguli fixe, fără model.

`supravegheaza` rulează după fiecare citire (orar). O anomalie pe orice cont:
- pune oprirea globală `reclame` (executorul nu mai lasă să plece decât punerea pe pauză);
- propune și aplică pauza pentru TOATE campaniile active, ca propuneri `urgenta` (urmă completă, anulabile
doar
  după repornire);
- te anunță pe canalul critic (push + Telegram).
Repornirea e întotdeauna manuală: oprirea se ridică din panou (Operare), iar campaniile se activează una
câte una.

Semnalele (16.5): cheltuiala de azi peste `MULTIPLU_RITM` × ritmul planificat; urmărirea conversiilor
tăcută (ieri
multe clicuri, zero rezultate, după zile cu rezultate); costul pe clic sau pe mia de afișări sărit de
`MULTIPLU_COST` ori față de media pe 7 zile; contul cu problemă la platformă (politică, plată); eroare de
autentificare; pagina de destinație care nu răspunde.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import sesiune_agentie
from app.logging import get_logger
from app.operare import motor, notificari, opriri
from app.operare.efecte import reclame as usa_reclame
from app.reclame import pagina, propuneri, rezultate
from app.reclame.modele import Anunt, Campanie, ContReclame

log = get_logger("app.reclame.urgenta")
MULTIPLU_RITM = 3.0
MULTIPLU_COST = 2.5
CLICURI_MINIME_URMARIRE = 50
CHELTUIALA_MINIMA_BANI = 1_000  # sub 10 lei pe zi nu se judecă ritmul


@dataclass(frozen=True)
class Anomalie:
    cont_id: uuid.UUID
    cod: str
    text: str


def _pagina_raspunde(url: str) -> bool:
    """# NEVERIFICAT: verificarea paginii de destinație e un GET simplu; pe VPS trece prin aceeași ieșire."""
    r = pagina.get_sigur(url)  # F15.2: fără SSRF
    return r is not None and r.status_code < 500


VERIFICA_PAGINA: Callable[[str], bool] = _pagina_raspunde


def semnale(db: Session, cont: ContReclame, acum: dt.datetime) -> list[Anomalie]:
    """Semnalele din cifrele salvate și din starea contului (fără apel la platformă)."""
    out: list[Anomalie] = []
    azi = acum.date()
    if cont.eroare_citire and cont.eroare_citire.startswith("EroareAutentificare"):
        out.append(Anomalie(cont.id, "autentificare", "eroare de autentificare la platforma de reclame"))
    active = list(
        db.execute(select(Campanie).where(Campanie.cont_id == cont.id, Campanie.stare == "activa")).scalars()
    )
    planificat = sum(c.buget_zilnic_bani for c in active)
    t_azi = rezultate.totaluri(db, cont.id, azi, azi)
    fractiune = max((acum - dt.datetime.combine(azi, dt.time(), dt.UTC)).total_seconds() / 86400, 1 / 24)
    # fără campanii active nu există ritm planificat (cheltuiala zilei e de dinainte de pauză)
    if (
        planificat
        and t_azi.cheltuiala_bani >= CHELTUIALA_MINIMA_BANI
        and t_azi.cheltuiala_bani > MULTIPLU_RITM * max(1, planificat) * min(1.0, fractiune)
    ):
        out.append(Anomalie(cont.id, "ritm", "cheltuiala de azi depășește de câteva ori ritmul planificat"))
    ieri = rezultate.totaluri(db, cont.id, azi - dt.timedelta(days=1), azi - dt.timedelta(days=1))
    inainte = rezultate.totaluri(db, cont.id, azi - dt.timedelta(days=8), azi - dt.timedelta(days=2))
    if ieri.clicuri >= CLICURI_MINIME_URMARIRE and ieri.rezultate == 0 and inainte.rezultate > 0:
        out.append(Anomalie(cont.id, "urmarire", "urmărirea conversiilor nu mai trimite evenimente"))
    referinta = inainte.cost_pe_clic_bani, inainte.cost_pe_mie_bani
    for actual, medie, nume in (
        (t_azi.cost_pe_clic_bani, referinta[0], "costul pe clic"),
        (t_azi.cost_pe_mie_bani, referinta[1], "costul pe mia de afișări"),
    ):
        if (
            actual
            and medie
            and t_azi.cheltuiala_bani >= CHELTUIALA_MINIMA_BANI
            and actual > MULTIPLU_COST * medie
        ):
            out.append(Anomalie(cont.id, "cost", f"{nume} a sărit brusc"))
    return out


def _pagini(db: Session, cont: ContReclame) -> set[str]:
    q = (
        select(Anunt.link)
        .join(Campanie, Campanie.id == Anunt.campanie_id)
        .where(Campanie.cont_id == cont.id, Campanie.stare == "activa")
    )
    return {link.split("?")[0] for link in db.execute(q).scalars()}


def opreste_tot(motiv: str, acum: dt.datetime | None = None) -> int:
    """Oprirea de urgență: oprirea globală + pauza tuturor campaniilor active + anunț critic."""
    with sesiune_agentie() as db:
        schimbat = opriri.seteaza(db, opriri.Oprire.RECLAME, True, canal="sistem", motiv=motiv)
        active = list(db.execute(select(Campanie).where(Campanie.stare == "activa")).scalars())
        for c in active:
            p = propuneri.propune(
                db,
                c.id,
                "stare",
                {"stare": "pauza"},
                motiv=f"Oprire de urgență: {motiv}",
                sursa="urgenta",
                acum=acum,
            )
            propuneri.aproba(db, p.id)
    if schimbat or active:
        notificari.notifica(
            notificari.Nivel.CRITIC,
            "Reclamele au fost oprite",
            f"{len(active)} campanii puse pe pauză; dacă platforma refuză pauza (token expirat),"
            f" oprește-le din managerul de reclame. Repornirea e manuală. Motiv: {motiv}",
            url="/reclame",
        )
    return len(active)


def opreste_cont(cont_id: uuid.UUID, motiv: str, acum: dt.datetime | None = None) -> int:
    """Pauza campaniilor active ale unui singur cont (o problemă a clientului, nu a platformei), cu anunț."""
    with sesiune_agentie() as db:
        active = list(
            db.execute(
                select(Campanie).where(Campanie.cont_id == cont_id, Campanie.stare == "activa")
            ).scalars()
        )
        for c in active:
            p = propuneri.propune(
                db,
                c.id,
                "stare",
                {"stare": "pauza"},
                motiv=f"Oprire pe cont: {motiv}",
                sursa="urgenta",
                acum=acum,
            )
            propuneri.aproba(db, p.id)
    if active:
        notificari.notifica(
            notificari.Nivel.CRITIC,
            "Reclamele unui client au fost oprite",
            f"{len(active)} campanii puse pe pauză. Motiv: {motiv}. Repornirea e manuală.",
            url="/reclame",
        )
    return len(active)


def supravegheaza(acum: dt.datetime | None = None) -> list[Anomalie]:
    """Verifică toate conturile active; la prima anomalie oprește tot (o singură dată)."""
    acum = acum or dt.datetime.now(dt.UTC)
    gasite: list[Anomalie] = []
    with sesiune_agentie() as db:
        propuneri.reconciliaza(db)
        conturi = [(c.id, c.tenant_id, c.platforma, c.cont_extern) for c in rezultate.conturi(db)]
        for c in rezultate.conturi(db):
            gasite.extend(semnale(db, c, acum))
        pagini = {(p, c.id) for c in rezultate.conturi(db) for p in _pagini(db, c)}
    for cid, tenant, platforma, extern in conturi:
        if not usa_reclame.are_cititor(platforma):
            continue
        try:
            st = usa_reclame.stare_cont(tenant, platforma, extern)
        except motor.EroareAutentificare:
            gasite.append(Anomalie(cid, "autentificare", "eroare de autentificare la platforma de reclame"))
            continue
        except (motor.EroareTemporara, motor.EroareDefinitiva) as exc:
            log.info("starea contului necitită", extra={"tip_eroare": type(exc).__name__})
            continue
        if not st.activ:
            gasite.append(Anomalie(cid, "cont", f"platforma semnalează o problemă pe cont: {st.motiv}"))
    # F15.2: pagina căzută a unui client oprește doar campaniile contului acelui client, nu pe ale tuturor
    # (altfel orice client ar putea opri reclamele celorlalți cu o pagină care dă 5xx).
    pe_cont: list[Anomalie] = []
    for adresa, cid in sorted(pagini, key=str):
        if not VERIFICA_PAGINA(adresa):
            pe_cont.append(Anomalie(cid, "pagina", f"pagina de destinație nu răspunde: {adresa}"))
            opreste_cont(cid, pe_cont[-1].text[:280], acum)
    if gasite:
        with sesiune_agentie() as db:
            deja = opriri.este_oprit(db, opriri.Oprire.RECLAME)
            are_active = db.execute(select(Campanie.id).where(Campanie.stare == "activa")).first() is not None
        if not deja or are_active:
            opreste_tot("; ".join(sorted({a.text for a in gasite}))[:280], acum)
    return gasite + pe_cont
