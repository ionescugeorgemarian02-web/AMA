"""Abonamentele și facturile (F7.6, docs/19 §19.5).

1. `incepe`: clientul alege planul; se creează abonamentul (`in_asteptare_plata`) și se cere
procesatorului, prin
   efectele de sistem (outbox, idempotent), abonamentul nou. Procesatorul întoarce linkul paginii lui de
   plată.
2. `trateaza_webhook`: webhook-urile procesatorului, verificate (semnătură HMAC, vechime ≤ 5 minute) și
luate o
   singură dată pe eveniment, schimbă starea: `abonament.activ` → activ (+ invitația în portal, prin
   extensie),
   `factura.platita` → factură, perioadă prelungită, restanța ștearsă (și suspendarea ridicată),
   `factura.esuata` → `restant` cu anunț pe email: 7 zile de grație.
3. `verifica_restante` (zilnic): restanțele mai vechi decât grația → `suspendat`: producția se oprește
(oprirea pe
   client), datele rămân. O plată ulterioară reactivează.
Platforma nu vede și nu stochează date de card."""

import datetime as dt
import hashlib
import hmac
import json
import secrets
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import sesiune_agentie
from app.finante import planuri
from app.finante.modele import Abonament, EvenimentPlata, Factura
from app.ids import new_id
from app.logging import get_logger
from app.operare import audit, evenimente, motor, opriri
from app.operare.efecte import sistem

log = get_logger("app.finante")
TOLERANTA_SEC = 300
DupaActivare = Callable[[Session, Abonament], None]
_DUPA_ACTIVARE: list[DupaActivare] = []


class SemnaturaInvalida(ValueError):
    pass


class EroareFacturare(ValueError):
    pass


def inregistreaza_dupa_activare(f: DupaActivare) -> None:
    """Punct de extensie: după prima activare (de exemplu invitația în portal, F7.3)."""
    if f not in _DUPA_ACTIVARE:
        _DUPA_ACTIVARE.append(f)


def hash_jeton(j: str) -> str:
    return hashlib.sha256(j.encode()).hexdigest()


def incepe(db: Session, tenant_id: uuid.UUID, cod_plan: str, *, email: str) -> tuple[Abonament, str]:
    """Abonamentul nou și cererea către procesator. Întoarce și jetonul paginii de plată (de arătat o
    dată)."""
    p = planuri.plan(cod_plan)
    activ = db.execute(
        select(Abonament).where(Abonament.tenant_id == tenant_id, Abonament.stare.in_(("activ", "restant")))
    ).first()
    if activ is not None:
        raise EroareFacturare("clientul are deja un abonament activ")
    jeton = secrets.token_urlsafe(32)
    a = Abonament(
        id=new_id(),
        tenant_id=tenant_id,
        plan=p.cod,
        suma=p.pret_lunar,
        email_facturare=email.strip().lower(),
        jeton_hash=hash_jeton(jeton),
    )
    db.add(a)
    db.flush()
    sistem.cere(
        db,
        "plata",
        cheie=f"abonament:{a.id}:nou",
        tenant_id=tenant_id,
        payload={"op": "abonament_nou", "abonament": str(a.id), "plan": p.cod, "suma": p.pret_lunar},
    )
    audit.record(
        db,
        "abonament.cerut",
        obiect_tip="abonament",
        obiect_id=a.id,
        tenant_id=tenant_id,
        actor_tip="sistem",
        detalii={"plan": p.cod},
    )
    return a, jeton


def dupa_jeton(db: Session, jeton: str) -> Abonament | None:
    if not 20 <= len(jeton) <= 100:
        return None
    return db.execute(select(Abonament).where(Abonament.jeton_hash == hash_jeton(jeton))).scalar_one_or_none()


def link_plata(db: Session, a: Abonament) -> str | None:
    """Linkul paginii de plată a procesatorului, după ce efectul de sistem a fost trimis."""
    for e in sistem.ale_tipului(db, "plata"):
        if e.cheia == f"plata:abonament:{a.id}:nou":
            return e.link if e.stare == "trimis" else None
    return None


def al_clientului(db: Session, tenant_id: uuid.UUID) -> Abonament | None:
    return db.execute(
        select(Abonament).where(Abonament.tenant_id == tenant_id).order_by(Abonament.creat_la.desc()).limit(1)
    ).scalar_one_or_none()


def facturi(db: Session, tenant_id: uuid.UUID) -> list[Factura]:
    return list(
        db.execute(
            select(Factura).where(Factura.tenant_id == tenant_id).order_by(Factura.creat_la.desc())
        ).scalars()
    )


# --- webhook-urile
# ---------------------------------------------------------------------------------------------


def verifica_semnatura(corp: bytes, antet: str, *, acum: float | None = None) -> None:
    secret = get_settings().plati_webhook_secret.get_secret_value()
    if len(secret) < 16:
        raise SemnaturaInvalida("secretul webhook-ului nu este configurat")
    parti = dict(p.split("=", 1) for p in antet.split(",") if "=" in p)
    t, v1 = parti.get("t", ""), parti.get("v1", "")
    if not t.isdigit():
        raise SemnaturaInvalida("antet de semnătură invalid")
    asteptat = hmac.new(secret.encode(), f"{t}.".encode() + corp, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(asteptat, v1):
        raise SemnaturaInvalida("semnătură greșită")
    if abs((acum if acum is not None else dt.datetime.now(dt.UTC).timestamp()) - int(t)) > TOLERANTA_SEC:
        raise SemnaturaInvalida("eveniment prea vechi")


def _data(v: Any) -> dt.datetime:
    return dt.datetime.fromisoformat(str(v))


def _abonament(db: Session, ev: dict[str, Any]) -> Abonament:
    try:
        aid = uuid.UUID(str(ev.get("referinta")))
    except ValueError:
        raise EroareFacturare("referință invalidă") from None
    a = db.execute(select(Abonament).where(Abonament.id == aid).with_for_update()).scalar_one_or_none()
    if a is None:
        raise EroareFacturare("abonament necunoscut")
    if a.id_extern is not None and a.id_extern != ev.get("abonament"):
        raise EroareFacturare("abonamentul procesatorului nu corespunde")
    return a


def _reactiveaza(db: Session, a: Abonament) -> None:
    if a.stare == "suspendat":
        opriri.seteaza(
            db,
            opriri.Oprire.CLIENT,
            False,
            canal="sistem",
            tenant_id=a.tenant_id,
            motiv="plata a fost primită: producția repornește",
        )
    a.stare, a.restant_de_la, a.suspendat_la = "activ", None, None


def _email(db: Session, a: Abonament, cheie: str, subiect: str, text: str) -> None:
    sistem.cere(
        db,
        "email",
        cheie=f"abonament:{a.id}:{cheie}",
        tenant_id=a.tenant_id,
        payload={"catre": a.email_facturare, "subiect": subiect, "text": text},
    )


def trateaza_webhook(corp: bytes, antet: str) -> str:
    """Verifică și aplică un webhook. Întoarce rezultatul (`aplicat`, `duplicat`, `ignorat`)."""
    verifica_semnatura(corp, antet)
    try:
        ev = json.loads(corp)
    except ValueError:
        raise SemnaturaInvalida("corp invalid") from None
    eid, tip = str(ev.get("id", ""))[:100], str(ev.get("tip", ""))
    if not eid:
        raise EroareFacturare("eveniment fără id")
    with sesiune_agentie() as db:
        if db.get(EvenimentPlata, eid) is not None:
            return "duplicat"
        rand = EvenimentPlata(id_extern=eid, tip=tip, corp=ev)
        db.add(rand)
        db.flush()
        a = _abonament(db, ev)
        prima = a.id_extern is None
        a.id_extern = str(ev["abonament"])
        if tip == "abonament.activ":
            _reactiveaza(db, a)
            a.perioada_pana_la = _data(ev["perioada_pana_la"])
            if prima:
                for f in _DUPA_ACTIVARE:
                    f(db, a)
        elif tip in ("factura.platita", "factura.esuata"):
            platita = tip == "factura.platita"
            if db.execute(select(Factura.id).where(Factura.id_extern == str(ev["factura"]))).first() is None:
                db.add(
                    Factura(
                        tenant_id=a.tenant_id,
                        abonament_id=a.id,
                        id_extern=str(ev["factura"]),
                        suma=int(ev["suma"]),
                        moneda=str(ev.get("moneda", "RON")),
                        stare="platita" if platita else "esuata",
                        perioada_de_la=_data(ev["perioada_de_la"]),
                        perioada_pana_la=_data(ev["perioada_pana_la"]),
                    )
                )
            if platita:
                _reactiveaza(db, a)
                a.perioada_pana_la = max(
                    a.perioada_pana_la or _data(ev["perioada_pana_la"]), _data(ev["perioada_pana_la"])
                )
            elif a.stare in ("activ", "in_asteptare_plata"):
                a.stare, a.restant_de_la = "restant", dt.datetime.now(dt.UTC)
                zile = get_settings().plati_gratie_zile
                _email(
                    db,
                    a,
                    f"restant:{eid}",
                    "Plata abonamentului nu a trecut",
                    f"Plata pentru abonamentul AMA nu a reușit. Ai {zile} zile să actualizezi "
                    "metoda de plată; după aceea producția se oprește, iar datele tale rămân.",
                )
        else:
            rand.rezultat = "ignorat"
            return "ignorat"
        rand.rezultat = "aplicat"
        audit.record(
            db,
            f"plata.{tip}",
            obiect_tip="abonament",
            obiect_id=a.id,
            tenant_id=a.tenant_id,
            actor_tip="sistem",
            detalii={"stare": a.stare, "eveniment": eid},
        )
        evenimente.emite(
            db,
            f"plata.{tip}",
            sursa="finante",
            obiect_tip="abonament",
            obiect_id=a.id,
            tenant_id=a.tenant_id,
            date={"stare": a.stare},
        )
    return "aplicat"


def verifica_restante(*, acum: dt.datetime | None = None) -> list[uuid.UUID]:
    """Restanțele trecute de perioada de grație: abonamentul se suspendă, producția clientului se oprește."""
    acum = acum or dt.datetime.now(dt.UTC)
    limita = acum - dt.timedelta(days=get_settings().plati_gratie_zile)
    suspendate = []
    with sesiune_agentie() as db:
        for a in db.execute(
            select(Abonament)
            .where(Abonament.stare == "restant", Abonament.restant_de_la <= limita)
            .with_for_update()
        ).scalars():
            a.stare, a.suspendat_la = "suspendat", acum
            opriri.seteaza(
                db,
                opriri.Oprire.CLIENT,
                True,
                canal="sistem",
                tenant_id=a.tenant_id,
                motiv="abonament neplătit după perioada de grație",
            )
            _email(
                db,
                a,
                f"suspendat:{acum.date()}",
                "Producția a fost oprită",
                "Abonamentul nu a fost plătit în perioada de grație: am oprit producția. Datele tale rămân; "
                "după plată, totul repornește.",
            )
            audit.record(
                db,
                "abonament.suspendat",
                obiect_tip="abonament",
                obiect_id=a.id,
                tenant_id=a.tenant_id,
                actor_tip="sistem",
            )
            suspendate.append(a.id)
    return suspendate


@motor.flux("finante.restante")
def tic_restante(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return str(len(_pas_restante()))


@motor.pas()
def _pas_restante() -> list[str]:
    return [str(x) for x in verifica_restante()]


def declara_programari() -> None:
    motor.programeaza_recurent("finante.restante", "20 6 * * *", tic_restante)


declara_programari()
