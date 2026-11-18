"""Conturile de reclame și citirea rezultatelor (F13.1 Meta, F13.2 Google; docs/16 §16.7, §16.10).

Citirea trece prin ușa executorului (`app.operare.efecte.reclame`), în afara tranzacției. Zilele recente se
recitesc la fiecare rulare (`ZILE_RECITITE`): platformele corectează cifrele după atribuire, iar panoul
trebuie
să arate exact ce arată managerul de reclame. Totalul contului e suma campaniilor (rândurile pe reclamă sunt
detaliul lor și nu se adună încă o dată).
"""

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.connectors.contract import RandReclame
from app.db import sesiune_agentie
from app.logging import get_logger
from app.operare import audit, motor
from app.operare.efecte import reclame as usa_reclame
from app.reclame.modele import ContReclame, RezultatReclame

log = get_logger("app.reclame.rezultate")
PLATFORME = ("meta", "google", "tiktok")
ETICHETE_PLATFORME = {"meta": "Meta (Facebook și Instagram)", "google": "Google Ads", "tiktok": "TikTok Ads"}
ZILE_RECITITE = 3
ZILE_PRIMA_CITIRE = 30


class ContInvalid(ValueError):
    """Contul nu poate fi adăugat așa (platformă necunoscută, plafoane incoerente)."""


def adauga_cont(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    platforma: str,
    cont_extern: str,
    nume: str,
    plafon_zilnic_bani: int,
    plafon_lunar_bani: int,
    plafon_campanie_bani: int,
    al_agentiei: bool = False,
    moneda: str = "RON",
    utilizator_id: uuid.UUID | None = None,
) -> ContReclame:
    """Leagă un cont de reclame de un client, cu plafoanele din contract (16.1)."""
    if platforma not in PLATFORME:
        raise ContInvalid(f"platformă necunoscută: {platforma}")
    if not 0 < plafon_campanie_bani <= plafon_zilnic_bani <= plafon_lunar_bani:
        raise ContInvalid("plafoanele cer: campanie ≤ zilnic ≤ lunar, toate pozitive")
    c = ContReclame(
        tenant_id=tenant_id,
        platforma=platforma,
        cont_extern=cont_extern.strip(),
        nume=nume.strip(),
        moneda=moneda,
        al_agentiei=al_agentiei,
        plafon_zilnic_bani=plafon_zilnic_bani,
        plafon_lunar_bani=plafon_lunar_bani,
        plafon_campanie_bani=plafon_campanie_bani,
    )
    db.add(c)
    db.flush()
    audit.record(
        db,
        "reclame.cont_adaugat",
        obiect_tip="reclame_cont",
        obiect_id=c.id,
        tenant_id=tenant_id,
        utilizator_id=utilizator_id,
        actor_tip=None if utilizator_id else "sistem",
        detalii={
            "platforma": platforma,
            "plafon_zilnic_bani": plafon_zilnic_bani,
            "plafon_lunar_bani": plafon_lunar_bani,
        },
    )
    return c


def conturi(db: Session, *, doar_active: bool = True) -> list[ContReclame]:
    q = select(ContReclame).order_by(ContReclame.al_agentiei.desc(), ContReclame.nume)
    if doar_active:
        q = q.where(ContReclame.activ.is_(True))
    return list(db.execute(q).scalars())


def _scrie(db: Session, cont: ContReclame, randuri: list[RandReclame], acum: dt.datetime) -> int:
    for r in randuri:
        valori = {
            "nume": r.nume[:300],
            "parinte_extern": r.parinte_extern,
            "cheltuiala_bani": max(0, r.cheltuiala_bani),
            "afisari": max(0, r.afisari),
            "clicuri": max(0, r.clicuri),
            "rezultate": max(0, r.rezultate),
            "citit_la": acum,
        }
        db.execute(
            pg_insert(RezultatReclame)
            .values(
                tenant_id=cont.tenant_id,
                cont_id=cont.id,
                nivel=r.nivel,
                obiect_extern=r.id_extern,
                zi=r.zi,
                **valori,
            )
            .on_conflict_do_update(index_elements=["cont_id", "nivel", "obiect_extern", "zi"], set_=valori)
        )
    return len(randuri)


def citeste_cont(cont_id: uuid.UUID, acum: dt.datetime | None = None) -> str:
    """Citește rezultatele unui cont: `citit:<rânduri>`, `fara_conector`, `amanat` (eroare temporară) sau
    `autentificare` (tokenul a expirat; F13.5 tratează asta ca anomalie)."""
    acum = acum or dt.datetime.now(dt.UTC)
    with sesiune_agentie() as db:
        cont = db.get(ContReclame, cont_id)
        if cont is None or not cont.activ:
            return "inactiv"
        tenant, platforma, extern = cont.tenant_id, cont.platforma, cont.cont_extern
        zile = ZILE_RECITITE if cont.citit_la else ZILE_PRIMA_CITIRE
    if not usa_reclame.are_cititor(platforma):
        return "fara_conector"
    azi = acum.date()
    try:
        randuri = usa_reclame.rezultate(tenant, platforma, extern, azi - dt.timedelta(days=zile - 1), azi)
    except (motor.EroareTemporara, motor.EroareDefinitiva) as exc:
        stare = "autentificare" if isinstance(exc, motor.EroareAutentificare) else "amanat"
        log.info(
            "rezultate de reclame necitite", extra={"platforma": platforma, "tip_eroare": type(exc).__name__}
        )
        with sesiune_agentie() as db:
            c = db.get(ContReclame, cont_id)
            if c is not None:
                c.eroare_citire = f"{type(exc).__name__}: {exc}"[:300]
        return stare
    with sesiune_agentie() as db:
        cont = db.get(ContReclame, cont_id)
        if cont is None:
            return "inactiv"
        n = _scrie(db, cont, randuri, acum)
        cont.citit_la, cont.eroare_citire = acum, None
    return f"citit:{n}"


def citeste_toate(acum: dt.datetime | None = None) -> dict[str, int]:
    with sesiune_agentie() as db:
        ids = [c.id for c in conturi(db)]
    numar: dict[str, int] = {}
    for cid in ids:
        r = citeste_cont(cid, acum).split(":")[0]
        numar[r] = numar.get(r, 0) + 1
    return numar


@dataclass(frozen=True)
class Totaluri:
    cheltuiala_bani: int = 0
    afisari: int = 0
    clicuri: int = 0
    rezultate: int = 0

    @property
    def cost_pe_rezultat_bani(self) -> int | None:
        return round(self.cheltuiala_bani / self.rezultate) if self.rezultate else None

    @property
    def rata_clic(self) -> float | None:
        return self.clicuri / self.afisari if self.afisari else None

    @property
    def cost_pe_clic_bani(self) -> int | None:
        return round(self.cheltuiala_bani / self.clicuri) if self.clicuri else None

    @property
    def cost_pe_mie_bani(self) -> int | None:
        return round(self.cheltuiala_bani * 1000 / self.afisari) if self.afisari else None


SUME = (
    func.coalesce(func.sum(RezultatReclame.cheltuiala_bani), 0),
    func.coalesce(func.sum(RezultatReclame.afisari), 0),
    func.coalesce(func.sum(RezultatReclame.clicuri), 0),
    func.coalesce(func.sum(RezultatReclame.rezultate), 0),
)


def _filtru(
    cont_id: uuid.UUID, de_la: dt.date, pana_la: dt.date, nivel: str
) -> tuple[ColumnElement[bool], ...]:
    return (
        RezultatReclame.cont_id == cont_id,
        RezultatReclame.nivel == nivel,
        RezultatReclame.zi >= de_la,
        RezultatReclame.zi <= pana_la,
    )


def totaluri(
    db: Session,
    cont_id: uuid.UUID,
    de_la: dt.date,
    pana_la: dt.date,
    *,
    obiect_extern: str | None = None,
    nivel: str = "campanie",
) -> Totaluri:
    q = select(*SUME).where(*_filtru(cont_id, de_la, pana_la, nivel))
    if obiect_extern is not None:
        q = q.where(RezultatReclame.obiect_extern == obiect_extern)
    c, a, k, r = db.execute(q).one()
    return Totaluri(int(c), int(a), int(k), int(r))


def pe_obiecte(
    db: Session,
    cont_id: uuid.UUID,
    de_la: dt.date,
    pana_la: dt.date,
    *,
    nivel: str = "campanie",
    parinte_extern: str | None = None,
) -> list[tuple[str, str, Totaluri]]:
    """(id extern, nume, totaluri) pe campanie (sau pe reclamă), cele mai scumpe primele."""
    q = select(RezultatReclame.obiect_extern, func.max(RezultatReclame.nume), *SUME).where(
        *_filtru(cont_id, de_la, pana_la, nivel)
    )
    if parinte_extern is not None:
        q = q.where(RezultatReclame.parinte_extern == parinte_extern)
    q = q.group_by(RezultatReclame.obiect_extern).order_by(SUME[0].desc(), RezultatReclame.obiect_extern)
    return [(str(o), str(n), Totaluri(int(c), int(a), int(k), int(r))) for o, n, c, a, k, r in db.execute(q)]


def pe_zile(
    db: Session, cont_id: uuid.UUID, de_la: dt.date, pana_la: dt.date
) -> list[tuple[dt.date, Totaluri]]:
    q = (
        select(RezultatReclame.zi, *SUME)
        .where(*_filtru(cont_id, de_la, pana_la, "campanie"))
        .group_by(RezultatReclame.zi)
        .order_by(RezultatReclame.zi)
    )
    return [(z, Totaluri(int(c), int(a), int(k), int(r))) for z, c, a, k, r in db.execute(q)]
