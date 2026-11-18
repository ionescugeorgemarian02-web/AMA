"""Programări (F12.5, docs/17 §17.6): modul propriu, simplu, fără serviciu separat.

- **Un tip de întâlnire** (apelul de 20 de minute despre audit, în sloturi de 30), **un calendar**: zilele
  lucrătoare, 10:00–17:00 ora României [I], cu cel puțin 2 ore înainte și cel mult 14 zile în față.
  Un slot are cel mult o programare confirmată (index unic: două rezervări simultane nu trec amândouă).
- **Rezervarea** trece prin ușa CRM-ului (`registru.primeste`, sursa „programare”: temei de contact, nu acord
  pentru emailuri), mută lead-ul în „apel programat” (deci secvența de hrănire se oprește singură) și, dacă
  persoana a răspuns la întrebări, o califică (F12.4).
- **Invitația de calendar** (.ics, METHOD:REQUEST) pleacă pe email ca mesaj **tranzacțional** (persoana
  a cerut apelul), prin efectele de sistem; la fel reamintirile (cu o zi și cu o oră înainte, jobul
  `crm.reamintiri`) și anularea (din linkul din invitație, METHOD:CANCEL). Calendarul extern: NECONSTRUIT.
"""

import datetime as dt
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crm import calificare, registru
from app.crm.modele import Contact, Programare
from app.crm.registru import CrmRefuzat
from app.db import sesiune_agentie
from app.ids import new_id
from app.operare import audit, motor, urme
from app.operare.efecte import sistem

NUME_JOB = "crm.reamintiri"
FUS = ZoneInfo("Europe/Bucharest")
ORE = (10, 17)  # [I] primul slot la 10:00, ultimul începe la 16:30
PAS = dt.timedelta(minutes=30)
AVANS_MINIM = dt.timedelta(hours=2)
ORIZONT = dt.timedelta(days=14)


@dataclass(frozen=True)
class TipIntalnire:
    titlu: str
    durata: dt.timedelta


TIPURI = {
    "apel_descoperire": TipIntalnire("Apel de 20 de minute despre auditul tău", dt.timedelta(minutes=20))
}


def _rotunjeste(t: dt.datetime) -> dt.datetime:
    t = t.astimezone(FUS).replace(second=0, microsecond=0)
    minute = (t.minute // 30 + 1) * 30 if t.minute % 30 else t.minute
    return t.replace(minute=0) + dt.timedelta(minutes=minute)


def grila(acum: dt.datetime) -> list[dt.datetime]:
    """Toate sloturile calendarului de la `acum + 2 h` la `acum + 14 zile`, în UTC."""
    t, sfarsit, rez = _rotunjeste(acum + AVANS_MINIM), acum + ORIZONT, []
    while t <= sfarsit:
        local = t.astimezone(FUS)
        if local.weekday() < 5 and ORE[0] <= local.hour < ORE[1]:
            rez.append(t.astimezone(dt.UTC))
        t = (local + PAS).astimezone(FUS)
    return rez


def ocupate(db: Session, de_la: dt.datetime, pana_la: dt.datetime) -> set[dt.datetime]:
    return set(
        db.scalars(
            select(Programare.inceput).where(
                Programare.stare == "confirmata", Programare.inceput >= de_la, Programare.inceput <= pana_la
            )
        )
    )


def sloturi(db: Session, acum: dt.datetime | None = None) -> list[dt.datetime]:
    acum = acum or dt.datetime.now(dt.UTC)
    toate = grila(acum)
    if not toate:
        return []
    luate = ocupate(db, toate[0], toate[-1])
    return [s for s in toate if s not in luate]


def eticheta(t: dt.datetime) -> str:
    zile = ("luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică")
    local = t.astimezone(FUS)
    return f"{zile[local.weekday()]}, {local:%d.%m}, ora {local:%H:%M}"


def _ics_data(t: dt.datetime) -> str:
    return t.astimezone(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def ics(p: Programare, email: str, *, metoda: str = "REQUEST") -> str:
    """Invitația de calendar (RFC 5545), în UTC; aceeași UID la anulare."""
    expeditor = get_settings().email_expeditor.rpartition("<")[2].rstrip(">") or "noreply@example.invalid"
    stare = "CANCELLED" if metoda == "CANCEL" else "CONFIRMED"
    linii = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//AMA//Programari//RO", f"METHOD:{metoda}",
        "BEGIN:VEVENT", f"UID:{p.id}@ama", f"DTSTAMP:{_ics_data(dt.datetime.now(dt.UTC))}",
        f"DTSTART:{_ics_data(p.inceput)}", f"DTEND:{_ics_data(p.sfarsit)}",
        f"SUMMARY:{TIPURI[p.tip].titlu}", f"ORGANIZER:mailto:{expeditor}",
        f"ATTENDEE;ROLE=REQ-PARTICIPANT;RSVP=TRUE:mailto:{email}", f"STATUS:{stare}",
        f"SEQUENCE:{1 if metoda == 'CANCEL' else 0}", "END:VEVENT", "END:VCALENDAR",
    ]  # fmt: skip
    return "\r\n".join(linii) + "\r\n"


def _hash(jeton: str) -> str:
    return hashlib.sha256(jeton.encode()).hexdigest()


def _email(
    db: Session, p: Programare, cheie: str, subiect: str, text: str, metoda: str | None = None
) -> None:
    contact = db.get(Contact, p.contact_id)
    if contact is None:
        return
    payload: dict[str, Any] = {"catre": contact.email, "subiect": subiect, "text": text}
    if metoda is not None:
        invitatie = ics(p, contact.email, metoda=metoda)
        payload["atasamente"] = [
            {"nume": "invitatie.ics", "tip": f"text/calendar; method={metoda}", "continut": invitatie}
        ]
    # Tranzacțional: persoana a cerut apelul (F12.2: lista fișierelor care pot cere emailuri necomerciale)
    sistem.cere(db, "email", cheie=f"programare:{p.id}:{cheie}", payload=payload)


def rezerva(
    db: Session,
    *,
    inceput: dt.datetime,
    email: str,
    firma: str,
    nume: str = "",
    telefon: str = "",
    raspunsuri: dict[str, str] | None = None,
    tip: str = "apel_descoperire",
    acum: dt.datetime | None = None,
) -> tuple[Programare, str]:
    """Rezervă un slot. Întoarce programarea și jetonul de anulare (doar în linkul din email)."""
    acum = acum or dt.datetime.now(dt.UTC)
    if tip not in TIPURI:
        raise CrmRefuzat("tip de întâlnire necunoscut")
    inceput = inceput.astimezone(dt.UTC)
    if inceput not in sloturi(db, acum):
        raise CrmRefuzat("intervalul ales nu este disponibil")
    if raspunsuri:
        calificare.valideaza(raspunsuri)  # refuzul vine înainte de orice scriere
    lead, _ = registru.primeste(
        db, email=email, firma=firma, nume=nume, telefon=telefon, sursa="programare",
        dovada="a rezervat un apel din pagina de programare", acum=acum,
    )  # fmt: skip
    jeton = secrets.token_urlsafe(32)
    p = Programare(
        id=new_id(), lead_id=lead.id, contact_id=lead.contact_id, tip=tip, inceput=inceput,
        sfarsit=inceput + TIPURI[tip].durata, jeton_hash=_hash(jeton),
    )  # fmt: skip
    try:
        with db.begin_nested():
            db.add(p)
            db.flush()
    except IntegrityError:
        raise CrmRefuzat("intervalul tocmai a fost rezervat de altcineva; alege altul") from None
    if raspunsuri:
        calificare.califica(db, lead.id, raspunsuri, sursa="formular", acum=acum)
    if lead.etapa in ("nou", "calificat"):
        registru.muta_etapa(db, lead.id, "apel_programat", utilizator_id=None, acum=acum)
    registru.adauga_activitate(db, lead.id, "programare", f"Apel programat: {eticheta(inceput)}.")
    registru.creeaza_sarcina(
        db, lead.id, f"Apel cu {firma.strip()[:60]}: {eticheta(inceput)}", inceput.astimezone(FUS).date(),
        cheie=f"programare:{p.id}",
    )  # fmt: skip
    anulare = f"{get_settings().site_url.rstrip('/')}/programare/anulare/{jeton}"
    _email(
        db, p, "invitatie", f"Confirmat: {TIPURI[tip].titlu}, {eticheta(inceput)}",
        f"Bună ziua,\n\nApelul e confirmat pentru {eticheta(inceput)} (ora României). Invitația de\n"
        f"calendar e atașată. Dacă nu mai puteți, anulați aici: {anulare}",
        metoda="REQUEST",
    )  # fmt: skip
    audit.record(
        db, "crm.apel_programat", obiect_tip="programare", obiect_id=p.id, actor_tip="anonim",
        detalii={"tip": tip, "inceput": inceput.isoformat()},
    )  # fmt: skip
    urme.inregistreaza(
        db, "crm", "programare", obiect_tip="lead_crm", obiect_id=str(lead.id), actor="anonim",
        iesiri={"programare": str(p.id), "inceput": inceput.isoformat(), "calificat": bool(raspunsuri)},
    )  # fmt: skip
    return p, jeton


def dupa_jeton(db: Session, jeton: str) -> Programare | None:
    if not 20 <= len(jeton) <= 100:
        return None
    return db.execute(select(Programare).where(Programare.jeton_hash == _hash(jeton))).scalar_one_or_none()


def anuleaza(db: Session, jeton: str, acum: dt.datetime | None = None) -> Programare | None:
    acum = acum or dt.datetime.now(dt.UTC)
    p = dupa_jeton(db, jeton)
    if p is None or p.stare != "confirmata":
        return p
    p.stare, p.anulat_la = "anulata", acum
    registru.adauga_activitate(
        db, p.lead_id, "programare", f"Apel anulat de persoană: {eticheta(p.inceput)}."
    )
    _email(
        db, p, "anulare", "Apel anulat",
        "Bună ziua,\n\nAm anulat apelul. Puteți alege oricând alt interval din pagina de programare.",
        metoda="CANCEL",
    )  # fmt: skip
    urme.inregistreaza(
        db, "crm", "programare_anulata", obiect_tip="lead_crm", obiect_id=str(p.lead_id), actor="anonim",
        iesiri={"programare": str(p.id)},
    )  # fmt: skip
    return p


def reaminteste(db: Session, acum: dt.datetime | None = None) -> int:
    """Reamintirile scadente: cu o zi și cu o oră înainte, fiecare o singură dată."""
    acum = acum or dt.datetime.now(dt.UTC)
    trimise = 0
    for p in db.scalars(
        select(Programare)
        .where(
            Programare.stare == "confirmata",
            Programare.inceput > acum,
            Programare.inceput <= acum + dt.timedelta(hours=24),
        )
        .with_for_update(skip_locked=True)
    ):
        if p.inceput - acum <= dt.timedelta(hours=1) and not p.reamintit_1h:
            p.reamintit_1h = p.reamintit_24h = True
            _email(db, p, "reamintire-1h", "Ne auzim într-o oră", f"Apelul începe la {eticheta(p.inceput)}.")
        elif not p.reamintit_24h:
            p.reamintit_24h = True
            _email(db, p, "reamintire-24h", "Mâine vorbim", f"Vă reamintim apelul de {eticheta(p.inceput)}.")
        else:
            continue
        trimise += 1
        urme.inregistreaza(
            db, "crm", "programare_reamintire", obiect_tip="lead_crm", obiect_id=str(p.lead_id)
        )
    return trimise


def ruleaza(acum: dt.datetime | None = None) -> int:
    with sesiune_agentie() as db:
        return reaminteste(db, acum)


@motor.pas("crm.pas_reamintiri")
def _pas() -> str:
    return f"{ruleaza()} reamintiri"


@motor.flux(NUME_JOB)
def flux(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _pas()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME_JOB, "*/15 * * * *", flux)


declara_programari()


def pentru_lead(db: Session, lead_id: uuid.UUID) -> list[Programare]:
    return list(
        db.scalars(select(Programare).where(Programare.lead_id == lead_id).order_by(Programare.inceput))
    )
