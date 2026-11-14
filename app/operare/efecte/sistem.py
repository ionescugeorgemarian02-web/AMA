"""Efectele externe de sistem (F7): emailuri tranzacționale și apeluri la procesatorul de plăți.

Aceeași ușă ca efectele livrabilelor (F2.5, AGENTS.md): cererea se scrie în tabelul „de trimis” în
tranzacția care
o justifică (cheie de idempotență unică), un job durabil o trimite după commit, cu reîncercări; conectorul se
cheamă DOAR de aici. Diferența: nu există livrabil, deci nici poarta pe starea lui; oprirea pe client
(`Oprire.CLIENT`) ține pe loc efectele clientului.

    from app.operare.efecte import sistem
    sistem.cere(db, "email", cheie="lead:<id>:confirmare", payload={"catre": …, "subiect": …, "text": …})
"""

import datetime as dt
import json
import uuid
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.connectors import registru
from app.connectors.contract import EfectSistem, RezultatPlatforma
from app.db import sesiune_agentie
from app.ids import new_id
from app.logging import get_logger
from app.operare import audit, motor, opriri
from app.operare.efecte.modele import EfectSistemRand
from app.operare.efecte.servicii import EfectRefuzat, _fara_secrete

log = get_logger("app.efecte.sistem")
TIPURI = ("email", "plata")


def _conector(tip: str) -> Any:
    try:
        return registru.conector_sistem(tip)
    except registru.ConectorNecunoscut:
        s = get_settings()
        if tip == "email" and s.email_furnizor == "simulat":
            from app.connectors import email  # SIMULAT: cutia poștală din proces

            registru.inregistreaza_sistem(tip, email.CUTIE)
        elif tip == "plata" and s.plati_procesator == "simulat":
            from app.connectors import plati  # SIMULAT: mediul de probă al procesatorului

            plati.PROCESATOR.secret = s.plati_webhook_secret.get_secret_value()
            registru.inregistreaza_sistem(tip, plati.PROCESATOR)
        return registru.conector_sistem(tip)


def cere(
    db: Session,
    tip: str,
    *,
    cheie: str,
    payload: dict[str, Any],
    tenant_id: uuid.UUID | None = None,
    porneste: bool = True,
) -> EfectSistemRand:
    """Cere un efect de sistem, idempotent pe `cheie`. Pornirea se face după commit."""
    if tip not in TIPURI:
        raise EfectRefuzat(f"tip de efect de sistem necunoscut: {tip}")
    _fara_secrete(payload)
    if len(json.dumps(payload, default=str)) > 16000:
        raise EfectRefuzat("payload prea mare")
    cheie_completa = f"{tip}:{cheie}"
    inserat = db.execute(
        pg_insert(EfectSistemRand)
        .values(id=new_id(), tenant_id=tenant_id, tip=tip, cheia=cheie_completa, payload=payload)
        .on_conflict_do_nothing(index_elements=["cheia"])
        .returning(EfectSistemRand.id)
    ).first()
    e = db.execute(select(EfectSistemRand).where(EfectSistemRand.cheia == cheie_completa)).scalar_one()
    if inserat is not None:
        audit.record(
            db,
            "efect_sistem.cerut",
            obiect_tip="efect_sistem",
            obiect_id=e.id,
            tenant_id=tenant_id,
            actor_tip="sistem",
            detalii={"tip": tip},
        )
        if porneste:
            efect_id = e.id

            def dupa(_s: Session) -> None:
                try:
                    motor.trimite(executa, str(efect_id), cheie=f"efect_sistem:{efect_id}")
                except Exception as exc:  # nu strică tranzacția încheiată; `reia_deschise` repune
                    log.warning("efect de sistem nepornit", extra={"tip_eroare": type(exc).__name__})

            event.listen(db, "after_commit", dupa, once=True)
    return e


def incearca(efect_id: uuid.UUID) -> str:
    """O încercare: `trimis`, `oprit`, `esuat`. Aruncă `EroareTemporara` (rezultatul se reîncearcă)."""
    with sesiune_agentie() as db:
        e = db.execute(
            select(EfectSistemRand).where(EfectSistemRand.id == efect_id).with_for_update()
        ).scalar_one()
        if e.stare in ("trimis", "esuat", "anulat"):
            return e.stare
        if e.tenant_id is not None and opriri.este_oprit(db, opriri.Oprire.CLIENT, tenant_id=e.tenant_id):
            return "oprit"
        e.incercari += 1
        spec = EfectSistem(id=e.id, tip=e.tip, idem=e.cheia, tenant_id=e.tenant_id, payload=dict(e.payload))
    try:
        rezultat: RezultatPlatforma = _conector(spec.tip).trimite(spec)
    except motor.EroareDefinitiva as exc:
        _incheie(efect_id, "esuat", eroare=str(exc)[:500])
        return "esuat"
    except Exception as exc:  # temporară: conectorul e idempotent pe `idem`, deci reîncercarea e sigură
        _incheie(efect_id, None, eroare=f"{type(exc).__name__}: {exc}"[:500])
        raise motor.EroareTemporara(f"{type(exc).__name__}: {exc}"[:300]) from exc
    _incheie(efect_id, "trimis", id_extern=rezultat.id_extern, link=rezultat.link or None)
    return "trimis"


def _incheie(efect_id: uuid.UUID, stare: str | None, **campuri: Any) -> None:
    with sesiune_agentie() as db:
        e = db.execute(
            select(EfectSistemRand).where(EfectSistemRand.id == efect_id).with_for_update()
        ).scalar_one()
        for k, v in campuri.items():
            setattr(e, k, v)
        if stare:
            e.stare = stare
            if stare == "trimis":
                e.trimis_la = dt.datetime.now(dt.UTC)
            audit.record(
                db,
                f"efect_sistem.{stare}",
                obiect_tip="efect_sistem",
                obiect_id=e.id,
                tenant_id=e.tenant_id,
                actor_tip="sistem",
                rezultat="ok" if stare == "trimis" else "esec",
                detalii={"tip": e.tip},
            )


@motor.pas(reincercari=4, pauza_sec=2.0)
def _pas_trimite(efect_id: str) -> str:
    return incearca(uuid.UUID(efect_id))


@motor.flux("efecte.sistem")
def executa(efect_id: str) -> str:
    return _pas_trimite(efect_id)


def citeste(db: Session, efect_id: uuid.UUID) -> EfectSistemRand | None:
    return db.get(EfectSistemRand, efect_id)


def ale_tipului(db: Session, tip: str, *, limita: int = 100) -> list[EfectSistemRand]:
    return list(
        db.execute(
            select(EfectSistemRand)
            .where(EfectSistemRand.tip == tip)
            .order_by(EfectSistemRand.creat_la.desc())
            .limit(limita)
        ).scalars()
    )
