"""CRM-ul minimal al agenției (F12.1, docs/17 §17.1, §17.7): firme, contacte, lead-uri pe etape, istoricul
consimțământului, unirea duplicatelor și sarcinile de urmărire.

- **O singură ușă de intrare, `primeste`.** Orice lead (formularul de audit, o recomandare introdusă de om,
  mai târziu reclamele și inboxul) trece pe aici, cu sursă și temei. Același lead trimis de două ori nu se
  dublează: contactul se caută după email, firma după domeniul site-ului (sau după numele normalizat), iar un
  contact are cel mult un lead deschis.
- **Consimțământul e un istoric**, doar cu adăugare: acordat sau retras, pe scop, cu sursă, temei și dovadă.
  Starea curentă e ultimul rând pe acel scop.
- **Igiena (J4)** este aici o procedură deterministă, fără model: unește firmele cu același nume normalizat
  când nu există dubiu și creează sarcini de urmărire pentru lead-urile lăsate în așteptare.
- Unirea nu șterge nimic: rândul duplicat rămâne, cu trimitere la cel păstrat.

Datele sunt ale agenției (RLS pe contextul de agenție). Oportunitățile ca obiect separat nu există: etapa
lead-ului le ține locul.
"""

import datetime as dt
import re
import unicodedata
import uuid
from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import event, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.crm.modele import Activitate, Consimtamant, Contact, Firma, LeadCrm, Sarcina
from app.db import sesiune_agentie
from app.logging import get_logger
from app.operare import audit, evenimente, motor

log = get_logger("ama.crm")
NUME_JOB = "crm.igiena"
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,}$")
# Sursa → temeiul contactului (tabelul din 17.1). Conturile-țintă nu intră aici: fără contact automat.
SURSE = {
    "formular_audit": "solicitare_si_opt_in",
    "resursa": "opt_in_dublu",
    "formular_reclama": "acord_in_formular",
    "inbox": "persoana_a_scris_prima",
    "programare": "solicitare_directa",
    "recomandare": "introducere_personala",
}
ETICHETE_SURSA = {
    "formular_audit": "formularul de audit",
    "resursa": "resursă descărcată",
    "formular_reclama": "formular din reclamă",
    "inbox": "mesaj sau comentariu",
    "programare": "programare",
    "recomandare": "recomandare",
}
ETICHETE_TEMEI = {
    "solicitare_si_opt_in": "a cerut auditul și a confirmat adresa",
    "opt_in_dublu": "opt-in dublu",
    "acord_in_formular": "acordul dat în formular",
    "persoana_a_scris_prima": "persoana a scris prima",
    "solicitare_directa": "solicitare directă",
    "introducere_personala": "introducere personală",
}
ETAPE = ("nou", "calificat", "apel_programat", "oferta_trimisa", "castigat", "pierdut")
ETICHETE_ETAPA = {
    "nou": "nou",
    "calificat": "calificat",
    "apel_programat": "apel programat",
    "oferta_trimisa": "ofertă trimisă",
    "castigat": "câștigat",
    "pierdut": "pierdut",
}
INCHISE = ("castigat", "pierdut")
TRANZITII: dict[str, tuple[str, ...]] = {
    "nou": ("calificat", "apel_programat", "pierdut"),
    "calificat": ("apel_programat", "oferta_trimisa", "pierdut"),
    "apel_programat": ("calificat", "oferta_trimisa", "pierdut"),
    "oferta_trimisa": ("apel_programat", "castigat", "pierdut"),
    "castigat": (),
    "pierdut": (),
}
# Ce consimțământ pentru email aduce fiecare sursă. O recomandare, un mesaj sau o programare sunt temei de
# contact făcut de om, nu acord pentru emailuri: de aceea nu scriu niciun rând de consimțământ.
SCOP_CONSIMTAMANT = {
    "formular_audit": "email_audit",
    "resursa": "email_resurse",
    "formular_reclama": "email_oferta",
}
# După câte zile fără mișcare apare o sarcină de urmărire [I]
URMARIRE = {
    "nou": (1, "Ia legătura cu lead-ul nou"),
    "calificat": (3, "Propune un apel"),
    "oferta_trimisa": (5, "Revino după ofertă"),
}
FORME_JURIDICE = {"srl", "srld", "sa", "pfa", "ii", "if", "snc", "scs", "sc", "ong"}
# Domenii care nu identifică o firmă: pagini pe platforme comune
DOMENII_COMUNE = {"facebook.com", "instagram.com", "linkedin.com", "tiktok.com", "youtube.com", "linktr.ee"}
PREFIXE_FORMULA = ("=", "+", "-", "@", "\t", "\r")


class CrmRefuzat(ValueError):
    """Cerere pe care CRM-ul o refuză, cu un motiv de arătat omului."""


# --- nucleu pur ---------------------------------------------------------------------------------------------
def norma_firma(nume: str) -> str:
    """Numele firmei, adus la o formă de comparat: fără diacritice, fără forma juridică, fără punctuație."""
    fara = unicodedata.normalize("NFKD", nume.lower())
    fara = "".join(c for c in fara if not unicodedata.combining(c))
    fara = re.sub(r"\bsrl\s*-\s*d\b", "srld", fara.replace(".", ""))
    cuvinte = re.sub(r"[^a-z0-9]+", " ", fara).split()
    utile = [c for c in cuvinte if c not in FORME_JURIDICE]
    return " ".join(utile or cuvinte)[:200]


def domeniu(site_url: str) -> str | None:
    """Domeniul site-ului, ca identitate a firmei; `None` când lipsește sau e pagină pe o platformă comună."""
    url = site_url.strip().lower()
    if not url:
        return None
    gazda = urlsplit(url if "://" in url else "https://" + url).hostname or ""
    gazda = gazda.removeprefix("www.")
    if "." not in gazda or len(gazda) > 253 or gazda in DOMENII_COMUNE:
        return None
    return gazda


def celula_csv(valoare: object) -> str:
    """O celulă de export care nu poate fi citită ca formulă de un program de calcul tabelar."""
    s = "" if valoare is None else str(valoare)
    return "'" + s if s.startswith(PREFIXE_FORMULA) else s


# --- intrarea -----------------------------------------------------------------------------------------------
def _firma(db: Session, nume: str, site_url: str) -> Firma:
    d, norm = domeniu(site_url), norma_firma(nume)
    q = select(Firma).where(Firma.unita_in.is_(None)).order_by(Firma.creat_la).limit(1)
    gasita = db.execute(q.where(Firma.domeniu == d)).scalar_one_or_none() if d else None
    if gasita is None:
        # după nume, doar dacă nu se contrazic domeniile (două firme cu același nume pot fi diferite)
        for f in db.execute(q.limit(None).where(Firma.nume_norm == norm)).scalars():
            if d is None or f.domeniu is None:
                gasita = f
                break
    if gasita is None:
        gasita = Firma(nume=nume, nume_norm=norm, domeniu=d)
        db.add(gasita)
        db.flush()
    elif gasita.domeniu is None and d is not None:
        gasita.domeniu = d
    return gasita


def consimtamant_curent(db: Session, contact_id: uuid.UUID, scop: str) -> Consimtamant | None:
    return db.execute(
        select(Consimtamant)
        .where(Consimtamant.contact_id == contact_id, Consimtamant.scop == scop)
        .order_by(Consimtamant.la.desc(), Consimtamant.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def are_consimtamant(db: Session, contact_id: uuid.UUID, scop: str) -> bool:
    c = consimtamant_curent(db, contact_id, scop)
    return c is not None and c.acordat


def scopuri_acordate(db: Session, contact_id: uuid.UUID) -> list[str]:
    scopuri = db.execute(
        select(Consimtamant.scop).where(Consimtamant.contact_id == contact_id).distinct()
    ).scalars()
    return sorted(s for s in scopuri if are_consimtamant(db, contact_id, s))


def noteaza_consimtamant(
    db: Session,
    contact_id: uuid.UUID,
    scop: str,
    *,
    acordat: bool,
    sursa: str,
    temei: str,
    dovada: str = "",
    acum: dt.datetime | None = None,
) -> bool:
    """Adaugă un rând în istoric doar dacă schimbă starea. Întoarce dacă a adăugat."""
    c = consimtamant_curent(db, contact_id, scop)
    if c is not None and c.acordat == acordat:
        return False
    if c is None and not acordat:
        temei = temei or "retragere"
    db.add(
        Consimtamant(
            contact_id=contact_id,
            scop=scop,
            acordat=acordat,
            sursa=sursa,
            temei=temei,
            dovada=dovada.strip()[:300],
            la=acum or dt.datetime.now(dt.UTC),
        )
    )
    db.flush()
    audit.record(
        db,
        "crm.consimtamant_acordat" if acordat else "crm.consimtamant_retras",
        obiect_tip="contact",
        obiect_id=contact_id,
        detalii={"scop": scop, "sursa": sursa},
    )
    return True


def _activitate(
    db: Session, lead_id: uuid.UUID, tip: str, mesaj: str, utilizator_id: uuid.UUID | None = None
) -> None:
    db.add(Activitate(lead_id=lead_id, tip=tip, text=mesaj[:1000], utilizator_id=utilizator_id))


def adauga_activitate(
    db: Session, lead_id: uuid.UUID, tip: str, mesaj: str, utilizator_id: uuid.UUID | None = None
) -> None:
    """O activitate pe lead, pentru pașii F12 de mai târziu (calificare, programare, ofertă, mesaj)."""
    _activitate(db, lead_id, tip, mesaj, utilizator_id)


def dupa_commit(db: Session, f: Callable[[], object]) -> None:
    """Rulează `f` doar după ce tranzacția s-a salvat (notificări, porniri de joburi)."""

    def _rulare(_s: Session) -> None:
        try:
            f()
        except Exception as exc:  # cel mai bun efort: acțiunea s-a salvat deja
            log.warning("acțiune după commit nereușită", extra={"tip_eroare": type(exc).__name__})

    event.listen(db, "after_commit", _rulare, once=True)


def primeste(
    db: Session,
    *,
    email: str,
    firma: str,
    sursa: str,
    site_url: str = "",
    nume: str = "",
    telefon: str = "",
    dovada: str = "",
    lead_site_id: uuid.UUID | None = None,
    utilizator_id: uuid.UUID | None = None,
    acum: dt.datetime | None = None,
) -> tuple[LeadCrm, bool]:
    """Ușa de intrare a lead-urilor. Întoarce lead-ul și dacă e nou. Repetarea aceleiași cereri nu creează
    nimic: nici contact, nici firmă, nici lead, nici rând de consimțământ. `dovada` descrie de unde știm
    (opt-in confirmat, cine a făcut prezentarea)."""
    if sursa not in SURSE:
        raise CrmRefuzat("sursă necunoscută")
    temei = SURSE[sursa]
    email, firma = email.strip().lower(), firma.strip()
    if not EMAIL.match(email) or not 6 <= len(email) <= 254:
        raise CrmRefuzat("adresa de email nu este validă")
    if not 2 <= len(firma) <= 200:
        raise CrmRefuzat("numele firmei trebuie să aibă între 2 și 200 de caractere")
    acum = acum or dt.datetime.now(dt.UTC)
    # două cereri simultane cu aceeași adresă intră pe rând
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:e))"), {"e": "crm:" + email})
    contact = db.execute(
        select(Contact).where(Contact.email == email, Contact.unit_in.is_(None))
    ).scalar_one_or_none()
    if contact is None:
        f = _firma(db, firma, site_url)
        contact = Contact(
            firma_id=f.id, email=email, nume=nume.strip()[:200], telefon=telefon.strip()[:40],
            sursa=sursa, temei=temei, creat_la=acum,
        )  # fmt: skip
        db.add(contact)
        db.flush()
    else:
        if nume.strip() and not contact.nume:
            contact.nume = nume.strip()[:200]
        if telefon.strip() and not contact.telefon:
            contact.telefon = telefon.strip()[:40]
    scop = SCOP_CONSIMTAMANT.get(sursa)
    if scop is not None:
        noteaza_consimtamant(
            db, contact.id, scop, acordat=True, sursa=sursa, temei=temei, dovada=dovada, acum=acum
        )
    lead = None
    if lead_site_id is not None:
        lead = db.execute(select(LeadCrm).where(LeadCrm.lead_site_id == lead_site_id)).scalar_one_or_none()
    if lead is None:
        lead = db.execute(
            select(LeadCrm).where(LeadCrm.contact_id == contact.id, LeadCrm.etapa.not_in(INCHISE))
        ).scalar_one_or_none()
    if lead is not None:
        if lead_site_id is not None and lead.lead_site_id is None:
            lead.lead_site_id = lead_site_id
        if lead.sursa != sursa:
            ultima = db.execute(
                select(Activitate.text)
                .where(Activitate.lead_id == lead.id, Activitate.tip == "intrare")
                .order_by(Activitate.la.desc(), Activitate.id.desc())
                .limit(1)
            ).scalar_one_or_none()
            mesaj = f"A venit din nou, prin: {ETICHETE_SURSA[sursa]}."
            if ultima != mesaj:
                _activitate(db, lead.id, "intrare", mesaj, utilizator_id)
        db.flush()
        return lead, False
    lead = LeadCrm(
        contact_id=contact.id, firma_id=contact.firma_id, sursa=sursa, temei=temei,
        lead_site_id=lead_site_id, creat_la=acum, actualizat_la=acum,
    )  # fmt: skip
    db.add(lead)
    db.flush()
    mesaj = f"Lead nou, prin: {ETICHETE_SURSA[sursa]}." + (f" {dovada.strip()}" if dovada.strip() else "")
    _activitate(db, lead.id, "intrare", mesaj, utilizator_id)
    audit.record(
        db,
        "crm.lead_primit",
        obiect_tip="lead_crm",
        obiect_id=lead.id,
        utilizator_id=utilizator_id,
        actor_tip="utilizator" if utilizator_id else "sistem",
        detalii={"sursa": sursa, "temei": temei},
    )
    db.flush()
    return lead, True


# --- etape, note, sarcini -----------------------------------------------------------------------------------
def _lead(db: Session, lead_id: uuid.UUID) -> LeadCrm:
    r = db.execute(select(LeadCrm).where(LeadCrm.id == lead_id).with_for_update()).scalar_one_or_none()
    if r is None:
        raise CrmRefuzat("lead-ul nu există")
    return r


def muta_etapa(
    db: Session,
    lead_id: uuid.UUID,
    etapa: str,
    *,
    utilizator_id: uuid.UUID | None,
    motiv: str = "",
    acum: dt.datetime | None = None,
) -> LeadCrm:
    lead = _lead(db, lead_id)
    if etapa not in TRANZITII.get(lead.etapa, ()):
        raise CrmRefuzat(
            f"din „{ETICHETE_ETAPA[lead.etapa]}” nu se poate trece în „{ETICHETE_ETAPA.get(etapa, etapa)}”"
        )
    motiv = motiv.strip()
    if etapa == "pierdut" and len(motiv) < 3:
        raise CrmRefuzat("scrie de ce s-a pierdut lead-ul")
    veche = lead.etapa
    lead.etapa, lead.actualizat_la = etapa, acum or dt.datetime.now(dt.UTC)
    if etapa == "pierdut":
        lead.motiv_pierdere = motiv[:300]
    db.flush()
    mesaj = f"Etapă: {ETICHETE_ETAPA[veche]} → {ETICHETE_ETAPA[etapa]}." + (
        f" Motiv: {motiv}" if motiv else ""
    )
    _activitate(db, lead.id, "etapa", mesaj, utilizator_id)
    # sarcinile de urmărire ale etapei vechi nu mai au rost
    for s in db.execute(
        select(Sarcina).where(
            Sarcina.lead_id == lead.id, Sarcina.stare == "deschisa", Sarcina.cheie.like("urmarire:%")
        )
    ).scalars():
        s.stare, s.inchisa_la = "anulata", lead.actualizat_la
    audit.record(
        db,
        "crm.lead_etapa",
        obiect_tip="lead_crm",
        obiect_id=lead.id,
        utilizator_id=utilizator_id,
        actor_tip="utilizator" if utilizator_id else "sistem",
        detalii={"din": veche, "in": etapa, "motiv": motiv[:120]},
    )
    if etapa in INCHISE:  # 17.9: lead-urile câștigate și pierdute, cu motiv, intră în învățare
        evenimente.emite(
            db,
            f"lead.{etapa}",
            sursa="crm",
            obiect_tip="lead_crm",
            obiect_id=lead.id,
            date={"sursa": lead.sursa, "motiv": motiv[:120]},
        )
    db.flush()
    return lead


def adauga_nota(db: Session, lead_id: uuid.UUID, nota: str, *, utilizator_id: uuid.UUID) -> None:
    lead = _lead(db, lead_id)
    if len(nota.strip()) < 2:
        raise CrmRefuzat("nota e goală")
    _activitate(db, lead.id, "nota", nota.strip(), utilizator_id)
    lead.actualizat_la = dt.datetime.now(dt.UTC)
    db.flush()


def creeaza_sarcina(
    db: Session, lead_id: uuid.UUID, titlu: str, scadenta: dt.date, *, cheie: str | None = None
) -> bool:
    """Întoarce dacă sarcina a fost creată (aceeași cheie nu se creează de două ori)."""
    titlu = titlu.strip()
    if not 3 <= len(titlu) <= 200:
        raise CrmRefuzat("titlul sarcinii trebuie să aibă între 3 și 200 de caractere")
    r = db.execute(
        insert(Sarcina)
        .values(lead_id=lead_id, cheie=cheie or f"manual:{uuid.uuid4().hex}", titlu=titlu, scadenta=scadenta)
        .on_conflict_do_nothing(index_elements=["cheie"])
        .returning(Sarcina.id)
    ).first()
    return r is not None


def inchide_sarcina(db: Session, sarcina_id: uuid.UUID) -> None:
    s = db.execute(select(Sarcina).where(Sarcina.id == sarcina_id).with_for_update()).scalar_one_or_none()
    if s is None or s.stare != "deschisa":
        raise CrmRefuzat("sarcina nu există sau e deja închisă")
    s.stare, s.inchisa_la = "facuta", dt.datetime.now(dt.UTC)
    db.flush()


def urmarire(db: Session, acum: dt.datetime | None = None) -> int:
    """Sarcini de urmărire pentru lead-urile lăsate în așteptare. Idempotent: o sarcină pe lead și etapă."""
    acum = acum or dt.datetime.now(dt.UTC)
    create = 0
    for etapa, (zile, titlu) in URMARIRE.items():
        for lead in db.execute(
            select(LeadCrm).where(
                LeadCrm.etapa == etapa, LeadCrm.actualizat_la <= acum - dt.timedelta(days=zile)
            )
        ).scalars():
            cheie = f"urmarire:{lead.id}:{etapa}:{lead.actualizat_la.date().isoformat()}"
            create += creeaza_sarcina(db, lead.id, titlu, acum.date(), cheie=cheie)
    return create


# --- unirea duplicatelor ------------------------------------------------------------------------------------
def _uneste_firma(db: Session, pastrata: Firma, duplicat: Firma, utilizator_id: uuid.UUID | None) -> None:
    for c in db.execute(select(Contact).where(Contact.firma_id == duplicat.id)).scalars():
        c.firma_id = pastrata.id
    for lead in db.execute(select(LeadCrm).where(LeadCrm.firma_id == duplicat.id)).scalars():
        lead.firma_id = pastrata.id
        mesaj = f"Firma „{duplicat.nume}” a fost unită cu „{pastrata.nume}”."
        _activitate(db, lead.id, "unire", mesaj, utilizator_id)
    if pastrata.domeniu is None and duplicat.domeniu is not None:
        pastrata.domeniu, duplicat.domeniu = duplicat.domeniu, None
        db.flush()
    duplicat.unita_in = pastrata.id
    db.flush()
    audit.record(
        db,
        "crm.firme_unite",
        obiect_tip="firma",
        obiect_id=pastrata.id,
        utilizator_id=utilizator_id,
        actor_tip="utilizator" if utilizator_id else "sistem",
        detalii={"duplicat": str(duplicat.id)},
    )


def uneste_firme_duplicate(db: Session) -> int:
    """Unește firmele cu același nume normalizat, doar când nu există dubiu: cel mult una dintre ele are
    domeniu. Două firme cu același nume și domenii diferite rămân separate (pot fi firme diferite)."""
    repetate = db.execute(
        select(Firma.nume_norm)
        .where(Firma.unita_in.is_(None))
        .group_by(Firma.nume_norm)
        .having(func.count() > 1)
    ).scalars()
    unite = 0
    for norm in list(repetate):
        grup = list(
            db.execute(
                select(Firma)
                .where(Firma.nume_norm == norm, Firma.unita_in.is_(None))
                .order_by(Firma.creat_la, Firma.id)
                .with_for_update()
            ).scalars()
        )
        cu_domeniu = [f for f in grup if f.domeniu is not None]
        if len(cu_domeniu) > 1:
            continue
        pastrata = cu_domeniu[0] if cu_domeniu else grup[0]
        for f in grup:
            if f.id != pastrata.id:
                _uneste_firma(db, pastrata, f, None)
                unite += 1
    return unite


def uneste_contacte(
    db: Session, pastrat_id: uuid.UUID, duplicat_id: uuid.UUID, *, utilizator_id: uuid.UUID
) -> None:
    """Unire hotărâtă de om (aceeași persoană cu două adrese). O retragere de consimțământ a oricăruia
    dintre cele două contacte rămâne retragere pe contactul păstrat."""
    if pastrat_id == duplicat_id:
        raise CrmRefuzat("alege două contacte diferite")
    randuri = {
        c.id: c
        for c in db.execute(
            select(Contact).where(Contact.id.in_((pastrat_id, duplicat_id))).with_for_update()
        ).scalars()
    }
    pastrat, duplicat = randuri.get(pastrat_id), randuri.get(duplicat_id)
    if pastrat is None or duplicat is None or pastrat.unit_in or duplicat.unit_in:
        raise CrmRefuzat("contactele nu există sau au fost deja unite")
    scopuri = db.execute(
        select(Consimtamant.scop).where(Consimtamant.contact_id == duplicat.id).distinct()
    ).scalars()
    for scop in list(scopuri):
        al_duplicatului = consimtamant_curent(db, duplicat.id, scop)
        al_pastratului = consimtamant_curent(db, pastrat.id, scop)
        if al_duplicatului is not None and (not al_duplicatului.acordat or al_pastratului is None):
            noteaza_consimtamant(
                db, pastrat.id, scop, acordat=al_duplicatului.acordat, sursa=al_duplicatului.sursa,
                temei=al_duplicatului.temei, dovada=f"preluat la unire de la {duplicat.email}",
            )  # fmt: skip
    deschis = db.execute(
        select(LeadCrm).where(LeadCrm.contact_id == pastrat.id, LeadCrm.etapa.not_in(INCHISE))
    ).scalar_one_or_none()
    for lead in db.execute(select(LeadCrm).where(LeadCrm.contact_id == duplicat.id)).scalars():
        if deschis is not None and lead.etapa not in INCHISE:
            lead.etapa, lead.motiv_pierdere = "pierdut", "duplicat al altui lead"
            db.flush()
        lead.contact_id, lead.firma_id = pastrat.id, pastrat.firma_id
        mesaj = f"Contactul {duplicat.email} a fost unit cu {pastrat.email}."
        _activitate(db, lead.id, "unire", mesaj, utilizator_id)
        db.flush()
    if not pastrat.telefon:
        pastrat.telefon = duplicat.telefon
    if not pastrat.nume:
        pastrat.nume = duplicat.nume
    duplicat.unit_in = pastrat.id
    db.flush()
    audit.record(
        db, "crm.contacte_unite", obiect_tip="contact", obiect_id=pastrat.id, utilizator_id=utilizator_id,
        detalii={"duplicat": str(duplicat.id)},
    )  # fmt: skip


# --- citire -------------------------------------------------------------------------------------------------
def lista(
    db: Session, etapa: str | None = None, *, limita: int = 200
) -> list[tuple[LeadCrm, Contact, Firma]]:
    q = (
        select(LeadCrm, Contact, Firma)
        .join(Contact, Contact.id == LeadCrm.contact_id)
        .join(Firma, Firma.id == LeadCrm.firma_id)
        .order_by(LeadCrm.actualizat_la.desc())
        .limit(limita)
    )
    if etapa is not None:
        q = q.where(LeadCrm.etapa == etapa)
    return [(a, b, c) for a, b, c in db.execute(q).all()]


def numar_pe_etape(db: Session) -> dict[str, int]:
    gasite = dict(db.execute(select(LeadCrm.etapa, func.count()).group_by(LeadCrm.etapa)).all())
    return {e: int(gasite.get(e, 0)) for e in ETAPE}


def fisa(db: Session, lead_id: uuid.UUID) -> dict[str, Any] | None:
    r = db.execute(
        select(LeadCrm, Contact, Firma)
        .join(Contact, Contact.id == LeadCrm.contact_id)
        .join(Firma, Firma.id == LeadCrm.firma_id)
        .where(LeadCrm.id == lead_id)
    ).first()
    if r is None:
        return None
    lead, contact, firma = r
    return {
        "lead": lead,
        "contact": contact,
        "firma": firma,
        "consimtamant": list(
            db.execute(
                select(Consimtamant)
                .where(Consimtamant.contact_id == contact.id)
                .order_by(Consimtamant.la.desc(), Consimtamant.id.desc())
            ).scalars()
        ),
        "activitati": list(
            db.execute(
                select(Activitate).where(Activitate.lead_id == lead.id).order_by(Activitate.la, Activitate.id)
            ).scalars()
        ),
        "sarcini": list(
            db.execute(
                select(Sarcina).where(Sarcina.lead_id == lead.id).order_by(Sarcina.scadenta, Sarcina.id)
            ).scalars()
        ),
        "tranzitii": TRANZITII[lead.etapa],
    }


def sarcini_deschise(db: Session, *, limita: int = 100) -> list[tuple[Sarcina, Firma]]:
    q = (
        select(Sarcina, Firma)
        .join(LeadCrm, LeadCrm.id == Sarcina.lead_id)
        .join(Firma, Firma.id == LeadCrm.firma_id)
        .where(Sarcina.stare == "deschisa")
        .order_by(Sarcina.scadenta, Sarcina.id)
        .limit(limita)
    )
    return [(a, b) for a, b in db.execute(q).all()]


COLOANE_EXPORT = (
    "firma", "domeniu", "email", "nume", "telefon", "sursa", "temei", "etapa", "motiv_pierdere",
    "consimtamant_email", "creat_la", "actualizat_la",
)  # fmt: skip


def export(db: Session) -> Iterable[list[str]]:
    """Exportul complet (17.7): un rând pe lead, cu firma, contactul, sursa, temeiul și starea
    consimțământului. Celulele sunt apărate de citirea ca formulă."""
    yield list(COLOANE_EXPORT)
    for lead, contact, firma in lista(db, limita=100_000):
        valori = [
            firma.nume, firma.domeniu, contact.email, contact.nume, contact.telefon, lead.sursa, lead.temei,
            lead.etapa, lead.motiv_pierdere,
            ", ".join(scopuri_acordate(db, contact.id)),
            lead.creat_la.isoformat(), lead.actualizat_la.isoformat(),
        ]  # fmt: skip
        yield [celula_csv(v) for v in valori]


# --- jobul zilnic de igienă (J4) ----------------------------------------------------------------------------
def igiena(acum: dt.datetime | None = None) -> tuple[int, int]:
    with sesiune_agentie() as db:
        return uneste_firme_duplicate(db), urmarire(db, acum)


@motor.pas("crm.pas_igiena")
def _pas() -> str:
    unite, sarcini = igiena()
    return f"{unite} firme unite, {sarcini} sarcini"


@motor.flux(NUME_JOB)
def flux(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _pas()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME_JOB, "10 6 * * *", flux)


declara_programari()
