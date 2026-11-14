"""Auditul gratuit (F7.2, docs/19 §19.1, docs/17): captare cu opt-in dublu, raport de la motorul de audit,
lead.

1. `cere`: firma completează formularul (cu acord explicit); se creează lead-ul `neconfirmat` și se cere
emailul
   de confirmare (efect de sistem, idempotent). Jetonul se ține doar ca SHA-256.
2. `confirma`: linkul din email confirmă adresa (opt-in dublu) și pornește auditul (job durabil).
3. `produ`: motorul de audit (adaptor, BigBrain) scrie raportul; lead-ul devine `audit_gata` și primește
emailul
   cu linkul raportului. Fără confirmare nu se rulează nimic și nu se trimite nimic în afară de confirmare.
Anti-spam: câmp-capcană ascuns, timp minim de completare (jeton semnat), un audit pe adresă."""

import datetime as dt
import hashlib
import hmac
import re
import secrets
import uuid
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import sesiune_agentie
from app.ids import new_id
from app.logging import get_logger
from app.operare import audit as jurnal
from app.operare import evenimente, motor
from app.operare.efecte import sistem
from app.site import motor_audit
from app.site.modele import Audit, Lead

EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,}$")
TIMP_MINIM_SEC = 3
TIMP_MAXIM_SEC = 24 * 3600
_CHEIE_LOCALA = secrets.token_bytes(32)
log = get_logger("app.site.audit")


class CerereInvalida(ValueError):
    """Formularul nu e valid (mesaj pentru om, în română)."""


def _cheie() -> bytes:
    s = get_settings().secret_key.get_secret_value()
    return s.encode() if len(s) >= 32 else _CHEIE_LOCALA


def jeton_formular(acum: float | None = None) -> str:
    """Momentul afișării formularului, semnat (anti-spam: nimeni nu completează în sub 3 secunde)."""
    t = str(int(acum if acum is not None else dt.datetime.now(dt.UTC).timestamp()))
    return t + "." + hmac.new(_cheie(), t.encode(), hashlib.sha256).hexdigest()[:32]


def verifica_jeton_formular(jeton: str, acum: float | None = None) -> bool:
    t, _, semn = jeton.partition(".")
    if not t.isdigit() or not hmac.compare_digest(semn, jeton_formular(int(t)).partition(".")[2]):
        return False
    varsta = (acum if acum is not None else dt.datetime.now(dt.UTC).timestamp()) - int(t)
    return TIMP_MINIM_SEC <= varsta <= TIMP_MAXIM_SEC


def hash_jeton(jeton: str) -> str:
    return hashlib.sha256(jeton.encode()).hexdigest()


def site_valid(url: str) -> str:
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname or "." not in p.hostname or len(url) > 300:
        raise CerereInvalida("Adresa site-ului nu este validă.")
    return url


def _url(cale: str) -> str:
    return get_settings().site_url.rstrip("/") + cale


def cere(
    db: Session, *, email: str, firma: str, site_url: str, acord: bool, capcana: str = "", jeton: str = ""
) -> Lead | None:
    """Înregistrează cererea și trimite emailul de confirmare. `None` = cerere tăcut ignorată (spam)."""
    if capcana or not verifica_jeton_formular(jeton):
        return None
    email = email.strip().lower()
    if not EMAIL.match(email):
        raise CerereInvalida("Adresa de email nu este validă.")
    firma = firma.strip()
    if not 2 <= len(firma) <= 200:
        raise CerereInvalida("Numele firmei trebuie să aibă între 2 și 200 de caractere.")
    site_url = site_valid(site_url)
    if not acord:
        raise CerereInvalida("Ca să primești raportul, bifează acordul pentru emailuri despre audit.")
    existent = db.execute(
        select(Lead).where(func.lower(Lead.email) == email, Lead.stare != "retras").with_for_update()
    ).scalar_one_or_none()
    jeton_nou = secrets.token_urlsafe(32)
    acum = dt.datetime.now(dt.UTC)
    if existent is not None and existent.stare != "neconfirmat":
        return existent  # un audit pe adresă; nu se trimite nimic nou
    if existent is None:
        lead = Lead(
            id=new_id(),
            email=email,
            firma=firma,
            site_url=site_url,
            jeton_hash=hash_jeton(jeton_nou),
            consimtamant_la=acum,
        )
        db.add(lead)
    else:
        lead = existent
        lead.firma, lead.site_url, lead.jeton_hash, lead.consimtamant_la = (
            firma,
            site_url,
            hash_jeton(jeton_nou),
            acum,
        )
    db.flush()
    sistem.cere(
        db,
        "email",
        cheie=f"lead:{lead.id}:confirmare:{lead.jeton_hash[:12]}",
        payload={
            "catre": email,
            "subiect": "Confirmă cererea de audit",
            "text": (
                f"Ai cerut un audit gratuit pentru {firma}. Confirmă adresa ca să pornim auditul:\n"
                f"{_url('/audit/confirma/' + jeton_nou)}\n\nDacă nu ai cerut tu auditul, ignoră acest mesaj."
            ),
        },
    )
    jurnal.record(db, "lead.cerut", obiect_tip="lead", obiect_id=lead.id, actor_tip="anonim")
    return lead


def lead_dupa_jeton(db: Session, jeton: str) -> Lead | None:
    if not 20 <= len(jeton) <= 100:
        return None
    return db.execute(select(Lead).where(Lead.jeton_hash == hash_jeton(jeton))).scalar_one_or_none()


def confirma(db: Session, jeton: str) -> Lead | None:
    """Opt-in dublu: linkul din email confirmă adresa și pornește auditul (o singură dată)."""
    lead = lead_dupa_jeton(db, jeton)
    if lead is None or lead.stare == "retras":
        return None
    if lead.stare != "neconfirmat":
        return lead
    lead.stare, lead.confirmat_la = "confirmat", dt.datetime.now(dt.UTC)
    a = Audit(id=new_id(), lead_id=lead.id, motor=motor_audit.motor().nume)
    db.add(a)
    db.flush()
    jurnal.record(db, "lead.confirmat", obiect_tip="lead", obiect_id=lead.id, actor_tip="anonim")
    evenimente.emite(
        db, "lead.confirmat", sursa="site", obiect_tip="lead", obiect_id=lead.id, date={"sursa": lead.sursa}
    )
    lead_id = lead.id

    def dupa(_s: Session) -> None:
        try:
            motor.trimite(ruleaza_auditul, str(lead_id), cheie=f"audit:{lead_id}")
        except Exception:  # cererea e salvată; auditul se poate reporni din panou
            log.warning("auditul nu a pornit", extra={"lead": str(lead_id)})

    event.listen(db, "after_commit", dupa, once=True)
    return lead


def produ(lead_id: uuid.UUID, jeton_raport: str | None = None) -> str:
    """Rulează motorul de audit și salvează raportul; trimite emailul cu linkul raportului. Idempotent."""
    with sesiune_agentie() as db:
        lead = db.get(Lead, lead_id)
        a = db.execute(select(Audit).where(Audit.lead_id == lead_id)).scalar_one_or_none()
        if lead is None or a is None:
            return "lipsa"
        if a.stare == "gata":
            return "gata"
        firma, site_url = lead.firma, lead.site_url
    try:
        raport: dict[str, Any] = motor_audit.motor().ruleaza(firma, site_url)
    except motor_audit.EroareAudit as exc:
        with sesiune_agentie() as db:
            a = db.execute(select(Audit).where(Audit.lead_id == lead_id).with_for_update()).scalar_one()
            a.stare, a.eroare = "esuat", str(exc)[:300]
        return "esuat"
    if len(raport.get("recomandari", [])) != 3 or not raport.get("rezumat"):
        raise motor.EroareDefinitiva("raportul motorului de audit nu respectă contractul")
    with sesiune_agentie() as db:
        a = db.execute(select(Audit).where(Audit.lead_id == lead_id).with_for_update()).scalar_one()
        lead = db.get(Lead, lead_id)
        if lead is None or a.stare == "gata":
            return "gata"
        a.stare, a.raport, a.gata_la = "gata", raport, dt.datetime.now(dt.UTC)
        if lead.stare == "confirmat":
            lead.stare = "audit_gata"
        # Linkul raportului: jeton nou, de citire (cel de confirmare a fost folosit).
        jeton = jeton_raport or secrets.token_urlsafe(32)
        lead.jeton_hash = hash_jeton(jeton)
        sistem.cere(
            db,
            "email",
            cheie=f"lead:{lead.id}:raport",
            payload={
                "catre": lead.email,
                "subiect": f"Raportul de audit pentru {lead.firma}",
                "text": f"{raport['rezumat']}\n\nRaportul complet: {_url('/audit/raport/' + jeton)}",
            },
        )
        jurnal.record(
            db,
            "audit.gata",
            obiect_tip="lead",
            obiect_id=lead.id,
            actor_tip="sistem",
            detalii={"motor": a.motor},
        )
    return "gata"


@motor.pas(reincercari=3, pauza_sec=5.0)
def _pas_audit(lead_id: str) -> str:
    return produ(uuid.UUID(lead_id))


@motor.flux("site.audit")
def ruleaza_auditul(lead_id: str) -> str:
    return _pas_audit(lead_id)


def raport(db: Session, jeton: str) -> tuple[Lead, Audit] | None:
    lead = lead_dupa_jeton(db, jeton)
    if lead is None:
        return None
    a = db.execute(select(Audit).where(Audit.lead_id == lead.id)).scalar_one_or_none()
    return (lead, a) if a is not None and a.stare == "gata" else None


def leaduri(db: Session, *, limita: int = 100) -> list[tuple[Lead, Audit | None]]:
    rows = db.execute(
        select(Lead, Audit)
        .outerjoin(Audit, Audit.lead_id == Lead.id)
        .order_by(Lead.creat_la.desc())
        .limit(limita)
    ).all()
    return [(r[0], r[1]) for r in rows]
