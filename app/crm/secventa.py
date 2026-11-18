"""Secvența de după audit (F12.3, docs/17 §17.3): patru emailuri, în zile fixe de la confirmarea adresei.

- **Înscrierea** se face o singură dată pe contact (`inscrie`), din confirmarea auditului (opt-in dublu).
- **Fiecare pas trece prin ușa unică `app.crm.email.trimite`**: lista de suprimare, matricea pe țări,
  consimțământul `email_audit`, pragurile și limita zilnică se verifică acolo, iar suprimarea încă o dată în
  executorul de efecte. Secvența nu are altă cale spre furnizor.
- **Oprirea e definitivă:** un refuz definitiv (suprimat, acord retras, țară blocată, domeniu inexistent) sau
  un lead care a avansat (apel programat, ofertă, câștigat, pierdut) opresc secvența; nu insistăm după un
  „nu” și nu trimitem material de hrănire cuiva care a cerut deja un apel. Limita zilnică și pragurile de
  oprire sunt temporare: pasul se reîncearcă la următoarea rulare.
- Jobul `crm.secventa` rulează la fiecare oră; fiecare pas lasă urmă (`crm / secventa_*`).
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crm import email
from app.crm.modele import Contact, Firma, InscriereSecventa, LeadCrm
from app.db import sesiune_agentie
from app.operare import motor, urme

NUME_JOB = "crm.secventa"
SECVENTA = "dupa_audit"
SCOP = "email_audit"
# Refuzuri care nu se repară singure: secvența se oprește. Limita zilnică și pragurile se reîncearcă.
DEFINITIVE = {"suprimat", "fara_consimtamant", "tara_blocata", "domeniu_inexistent", "contact_inexistent"}
# Un lead ajuns aici a trecut de hrănire: un om vorbește deja cu el.
AVANSATE = {"apel_programat", "oferta_trimisa", "castigat", "pierdut"}


@dataclass(frozen=True)
class Pas:
    zile: int  # de la înscriere [I]
    subiect: str
    text: str


PASI: tuple[Pas, ...] = (
    Pas(
        2,
        "Primele trei lucruri de reparat pe site-ul {firma}",
        "Bună ziua,\n\nÎn auditul pentru {firma} am găsit mai multe lucruri; dacă alegeți doar trei,\n"
        "începeți cu cele marcate „prioritar” în raport. Fiecare are pașii scriși, ca să le puteți face\n"
        "și fără noi.",
    ),
    Pas(
        5,
        "Cum arată „înainte și după” la o firmă ca {firma}",
        "Bună ziua,\n\nVă arătăm, pe un exemplu anonimizat din aceeași nișă, ce s-a schimbat după\n"
        "ce au fost reparate problemele din audit: mai multe cereri din site și mai puține abandonuri.",
    ),
    Pas(
        9,
        "Vreți să trecem împreună prin audit?",
        "Bună ziua,\n\nDacă vreți, trecem în 20 de minute prin raportul pentru {firma} și vă spunem\n"
        "ce am face noi în primele 30 de zile. Alegeți un interval aici: {programare}",
    ),
    Pas(
        14,
        "Ultimul mesaj din această serie",
        "Bună ziua,\n\nAcesta e ultimul email din seria despre auditul pentru {firma}. Raportul rămâne al\n"
        "dumneavoastră. Dacă vreți să discutăm mai târziu, ne găsiți oricând aici: {programare}",
    ),
)


def campanie(pas: int) -> str:
    return f"secventa-{SECVENTA}-{pas + 1}"


def inscrie(
    db: Session, contact_id: uuid.UUID, *, lead_id: uuid.UUID | None = None, acum: dt.datetime | None = None
) -> bool:
    """Înscrie contactul în secvența de după audit. Întoarce dacă e o înscriere nouă (a doua oară: nimic)."""
    acum = acum or dt.datetime.now(dt.UTC)
    nou = db.execute(
        insert(InscriereSecventa)
        .values(
            contact_id=contact_id,
            lead_id=lead_id,
            secventa=SECVENTA,
            pornita_la=acum,
            urmatorul_la=acum + dt.timedelta(days=PASI[0].zile),
        )
        .on_conflict_do_nothing(index_elements=["contact_id", "secventa"])
        .returning(InscriereSecventa.id)
    ).first()
    if nou is not None:
        urme.inregistreaza(
            db, "crm", "secventa_inscriere", obiect_tip="contact", obiect_id=str(contact_id),
            iesiri={"secventa": SECVENTA, "pasi": len(PASI)},
        )  # fmt: skip
    return nou is not None


def _opreste(db: Session, s: InscriereSecventa, motiv: str) -> None:
    s.stare, s.motiv_oprire, s.urmatorul_la = "oprita", motiv[:80], None
    urme.inregistreaza(
        db, "crm", "secventa_oprita", rezultat="blocat", motiv=motiv[:80], obiect_tip="contact",
        obiect_id=str(s.contact_id), iesiri={"pas": s.pas},
    )  # fmt: skip


def _text(pas: Pas, firma: str) -> tuple[str, str]:
    programare = f"{get_settings().site_url.rstrip('/')}/programare"
    return pas.subiect.format(firma=firma), pas.text.format(firma=firma, programare=programare)


def avanseaza(db: Session, acum: dt.datetime | None = None) -> dict[str, int]:
    """Trimite pașii scadenți. Întoarce câte s-au trimis, oprit, amânat."""
    acum = acum or dt.datetime.now(dt.UTC)
    rezultat = {"trimise": 0, "oprite": 0, "amanate": 0}
    scadente = db.scalars(
        select(InscriereSecventa)
        .where(InscriereSecventa.stare == "activa", InscriereSecventa.urmatorul_la <= acum)
        .order_by(InscriereSecventa.urmatorul_la)
        .limit(500)
        .with_for_update(skip_locked=True)
    ).all()
    for s in scadente:
        contact = db.get(Contact, s.contact_id)
        lead = db.get(LeadCrm, s.lead_id) if s.lead_id else None
        if lead is not None and lead.etapa in AVANSATE:
            _opreste(db, s, f"lead_{lead.etapa}")
            rezultat["oprite"] += 1
            continue
        firma = db.get(Firma, contact.firma_id) if contact else None
        subiect, corp = _text(PASI[s.pas], firma.nume if firma else "firma dumneavoastră")
        r = email.trimite(
            db, s.contact_id, campanie=campanie(s.pas), scop=SCOP, subiect=subiect, text=corp, acum=acum
        )
        if not r.trimis:
            if r.motiv in DEFINITIVE:
                _opreste(db, s, r.motiv)
                rezultat["oprite"] += 1
            else:
                rezultat["amanate"] += 1
            continue
        s.pas += 1
        if s.pas >= len(PASI):
            s.stare, s.urmatorul_la = "terminata", None
        else:
            s.urmatorul_la = s.pornita_la + dt.timedelta(days=PASI[s.pas].zile)
        urme.inregistreaza(
            db, "crm", "secventa_pas", obiect_tip="contact", obiect_id=str(s.contact_id),
            iesiri={"pas": s.pas, "campanie": campanie(s.pas - 1), "stare": s.stare},
        )  # fmt: skip
        rezultat["trimise"] += 1
    return rezultat


def stare(db: Session, contact_id: uuid.UUID) -> InscriereSecventa | None:
    return db.execute(
        select(InscriereSecventa).where(
            InscriereSecventa.contact_id == contact_id, InscriereSecventa.secventa == SECVENTA
        )
    ).scalar_one_or_none()


def ruleaza(acum: dt.datetime | None = None) -> dict[str, int]:
    with sesiune_agentie() as db:
        return avanseaza(db, acum)


@motor.pas("crm.pas_secventa")
def _pas() -> str:
    r = ruleaza()
    return f"{r['trimise']} trimise, {r['oprite']} oprite, {r['amanate']} amânate"


@motor.flux(NUME_JOB)
def flux(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _pas()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME_JOB, "17 * * * *", flux)


declara_programari()
