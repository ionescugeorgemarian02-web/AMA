"""Email către abonați (F12.2, docs/17 §17.3–17.4, docs/21 §21.8).

**O singură ușă pentru emailul comercial: `trimite`.** Înainte de orice trimitere verifică, în ordine:
lista de suprimare, matricea pe țări (o țară fără rând e blocată), consimțământul pe scopul cerut, pragurile
de oprire (respingeri și plângeri), limita zilnică (volumul crește treptat) și existența domeniului adresei.
Fiecare mesaj pleacă marcat `categorie = marketing`, cu dezabonare dintr-un clic în antet și în text.

Lista de suprimare se mai verifică o dată în executorul de efecte, în clipa trimiterii (`efecte.sistem`):
un mesaj cerut înainte de dezabonare nu mai pleacă după ea. Emailurile tranzacționale (confirmarea adresei,
facturi, resetări) nu trec pe aici și nu sunt oprite de dezabonare.

Furnizorul real de email nu există încă: se trimite prin cutia poștală simulată (`AMA_EMAIL_FURNIZOR`).
"""

import base64
import datetime as dt
import hashlib
import hmac
import secrets
import socket
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crm import registru
from app.crm.modele import Contact, RegulaTara, Suprimare, Trimitere
from app.operare import audit
from app.operare.efecte import sistem

MOTIVE_SUPRIMARE = ("dezabonat", "respins", "plangere", "manual")
ETICHETE_MOTIV = {
    "dezabonat": "s-a dezabonat",
    "respins": "adresă respinsă",
    "plangere": "plângere de spam",
    "manual": "adăugată de om",
}
ETICHETE_REFUZ = {
    "contact_inexistent": "contactul nu există",
    "suprimat": "adresa este în lista de suprimare",
    "tara_blocata": "țara contactului nu are încă regulă verificată de avocat",
    "fara_consimtamant": "contactul nu și-a dat acordul pentru acest fel de emailuri",
    "oprit_praguri": "trimiterea e oprită: prea multe respingeri sau plângeri",
    "limita_zilnica": "limita zilnică de trimitere a fost atinsă",
    "domeniu_inexistent": "domeniul adresei nu există",
}
PRAG_RESPINGERI = 0.02  # 17.3 [I]
PRAG_PLANGERI = 0.001  # 17.3 [I]
FEREASTRA_RATE = dt.timedelta(days=30)
MINIM_PENTRU_RATE = 50  # sub atâtea trimiteri, ratele nu spun nimic și nu opresc
# Volumul crește treptat (17.3): limita pe zi, după săptămâna de la prima trimitere [I]
VOLUM_PE_SAPTAMANA = (50, 100, 200, 400, 800)
_CHEIE_LOCALA = secrets.token_bytes(32)
# Verificarea domeniului: doar DNS, fără sondarea serverelor de email. Înlocuibilă în teste.
REZOLVA: Callable[[str], bool] | None = None


@dataclass(frozen=True)
class Rezultat:
    trimis: bool
    motiv: str = ""  # cheie din ETICHETE_REFUZ; gol la succes

    @property
    def explicatie(self) -> str:
        return ETICHETE_REFUZ.get(self.motiv, self.motiv)


# --- nucleu pur ---------------------------------------------------------------------------------------------
def _cheie() -> bytes:
    s = get_settings().secret_key.get_secret_value()
    return s.encode() if len(s) >= 32 else _CHEIE_LOCALA


def jeton_dezabonare(email: str) -> str:
    """Jeton fără stare: adresa și semnătura ei. Nu expiră: linkul de dezabonare trebuie să meargă oricând."""
    adresa = email.strip().lower().encode()
    semn = hmac.new(_cheie(), b"dezabonare:" + adresa, hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(adresa).decode().rstrip("=") + "." + semn


def email_din_jeton(jeton: str) -> str | None:
    corp, _, semn = jeton.partition(".")
    try:
        adresa = base64.urlsafe_b64decode(corp + "=" * (-len(corp) % 4)).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    if not adresa or not hmac.compare_digest(jeton, jeton_dezabonare(adresa)) or not semn:
        return None
    return adresa


def limita_zilnica(prima_trimitere: dt.datetime | None, acum: dt.datetime) -> int:
    if prima_trimitere is None:
        return VOLUM_PE_SAPTAMANA[0]
    saptamana = max(0, (acum - prima_trimitere).days // 7)
    return VOLUM_PE_SAPTAMANA[min(saptamana, len(VOLUM_PE_SAPTAMANA) - 1)]


def praguri_depasite(trimise: int, respinse: int, plangeri: int) -> bool:
    if trimise < MINIM_PENTRU_RATE:
        return False
    return respinse / trimise > PRAG_RESPINGERI or plangeri / trimise > PRAG_PLANGERI


def domeniu_exista(domeniu: str) -> bool:
    """Există domeniul în DNS? Nu se contactează serverul de email al destinatarului."""
    if REZOLVA is not None:
        return REZOLVA(domeniu)
    try:
        socket.getaddrinfo(domeniu, None)
    except OSError:
        return False
    return True


# --- suprimarea ---------------------------------------------------------------------------------------------
def suprimat(db: Session, email: str) -> bool:
    return db.get(Suprimare, email.strip().lower()) is not None


def suprima(db: Session, email: str, motiv: str, *, sursa: str = "") -> bool:
    """Pune adresa în lista de suprimare și retrage orice consimțământ de email al contactului. Întoarce
    dacă adresa a fost adăugată acum. Nu există operația inversă."""
    email = email.strip().lower()
    if motiv not in MOTIVE_SUPRIMARE:
        raise registru.CrmRefuzat("motiv de suprimare necunoscut")
    if not registru.EMAIL.match(email) or not 6 <= len(email) <= 254:
        raise registru.CrmRefuzat("adresa de email nu este validă")
    noua = db.execute(
        insert(Suprimare)
        .values(email=email, motiv=motiv, sursa=sursa[:120])
        .on_conflict_do_nothing(index_elements=["email"])
        .returning(Suprimare.email)
    ).first()
    for contact_id in db.execute(select(Contact.id).where(Contact.email == email)).scalars():
        for scop in registru.scopuri_acordate(db, contact_id):
            registru.noteaza_consimtamant(
                db, contact_id, scop, acordat=False, sursa="suprimare", temei=motiv, dovada=sursa
            )
    if noua is not None:
        audit.record(db, "crm.adresa_suprimata", obiect_tip="suprimare", detalii={"motiv": motiv})
    return noua is not None


def dezaboneaza(db: Session, jeton: str) -> bool:
    """Dezabonarea dintr-un clic. `False` doar pentru un jeton care nu e al nostru."""
    adresa = email_din_jeton(jeton)
    if adresa is None:
        return False
    suprima(db, adresa, "dezabonat", sursa="linkul de dezabonare")
    return True


# --- matricea pe țări ---------------------------------------------------------------------------------------
def regula_tarii(db: Session, tara: str, tip_destinatar: str = "firma") -> RegulaTara | None:
    return db.get(RegulaTara, (tara, tip_destinatar))


def seteaza_regula(
    db: Session,
    *,
    tara: str,
    tip_destinatar: str,
    regula: str,
    mentiuni: str,
    verificat_de: str,
    utilizator_id: uuid.UUID,
) -> None:
    tara = tara.strip().upper()
    if len(tara) != 2 or not tara.isalpha() or not tara.isascii():
        raise registru.CrmRefuzat("țara se scrie cu codul de două litere (de exemplu RO)")
    if tip_destinatar not in ("firma", "persoana") or regula not in ("doar_cu_consimtamant", "blocat"):
        raise registru.CrmRefuzat("regulă necunoscută")
    if len(verificat_de.strip()) < 3:
        raise registru.CrmRefuzat("scrie cine a verificat regula (avocatul și data avizului)")
    valori = {
        "regula": regula,
        "mentiuni": mentiuni.strip()[:500],
        "verificat_de": verificat_de.strip()[:200],
        "verificat_la": dt.datetime.now(dt.UTC),
    }
    db.execute(
        insert(RegulaTara)
        .values(tara=tara, tip_destinatar=tip_destinatar, **valori)
        .on_conflict_do_update(index_elements=["tara", "tip_destinatar"], set_=valori)
    )
    audit.record(
        db,
        "crm.regula_tara",
        obiect_tip="matrice_tari",
        obiect_id=f"{tara}:{tip_destinatar}",
        utilizator_id=utilizator_id,
        detalii={"regula": regula},
    )


def matrice(db: Session) -> list[RegulaTara]:
    return list(db.execute(select(RegulaTara).order_by(RegulaTara.tara, RegulaTara.tip_destinatar)).scalars())


# --- starea trimiterii --------------------------------------------------------------------------------------
def stare(db: Session, acum: dt.datetime | None = None) -> dict[str, Any]:
    acum = acum or dt.datetime.now(dt.UTC)
    de_la = acum - FEREASTRA_RATE
    trimise = db.execute(select(func.count()).select_from(Trimitere).where(Trimitere.la > de_la)).scalar_one()
    pe_motiv = dict(
        db.execute(
            select(Suprimare.motiv, func.count()).where(Suprimare.la > de_la).group_by(Suprimare.motiv)
        ).all()
    )
    azi = db.execute(
        select(func.count()).select_from(Trimitere).where(func.date(Trimitere.la) == acum.date())
    ).scalar_one()
    prima = db.execute(select(func.min(Trimitere.la))).scalar_one()
    respinse, plangeri = int(pe_motiv.get("respins", 0)), int(pe_motiv.get("plangere", 0))
    return {
        "trimise": int(trimise),
        "respinse": respinse,
        "plangeri": plangeri,
        "oprit": praguri_depasite(int(trimise), respinse, plangeri),
        "azi": int(azi),
        "limita": limita_zilnica(prima, acum),
        "suprimate": int(db.execute(select(func.count()).select_from(Suprimare)).scalar_one()),
    }


# --- ușa de trimitere ---------------------------------------------------------------------------------------
def _refuz(db: Session, contact_id: uuid.UUID, campanie: str, motiv: str) -> Rezultat:
    audit.record(
        db,
        "crm.email_refuzat",
        obiect_tip="contact",
        obiect_id=contact_id,
        rezultat="esec",
        detalii={"campanie": campanie[:80], "motiv": motiv},
    )
    return Rezultat(False, motiv)


def trimite(
    db: Session,
    contact_id: uuid.UUID,
    *,
    campanie: str,
    scop: str,
    subiect: str,
    text: str,
    acum: dt.datetime | None = None,
) -> Rezultat:
    """Trimite un email comercial unui contact, o singură dată pe campanie. Refuzul e un rezultat cu motiv."""
    acum = acum or dt.datetime.now(dt.UTC)
    contact = db.get(Contact, contact_id)
    if contact is None or contact.unit_in is not None:
        return Rezultat(False, "contact_inexistent")
    cheie = f"{campanie}:{contact.id}"
    if db.execute(select(Trimitere.id).where(Trimitere.cheie == cheie)).first() is not None:
        return Rezultat(True)  # deja cerut pentru această campanie
    if suprimat(db, contact.email):
        return _refuz(db, contact.id, campanie, "suprimat")
    regula = regula_tarii(db, contact.tara)
    if regula is None or regula.regula == "blocat":
        return _refuz(db, contact.id, campanie, "tara_blocata")
    if not registru.are_consimtamant(db, contact.id, scop):
        return _refuz(db, contact.id, campanie, "fara_consimtamant")
    s = stare(db, acum)
    if s["oprit"]:
        return _refuz(db, contact.id, campanie, "oprit_praguri")
    if s["azi"] >= s["limita"]:
        return _refuz(db, contact.id, campanie, "limita_zilnica")
    if not domeniu_exista(contact.email.rpartition("@")[2]):
        return _refuz(db, contact.id, campanie, "domeniu_inexistent")
    link = f"{get_settings().site_url.rstrip('/')}/dezabonare/{jeton_dezabonare(contact.email)}"
    subsol = f"\n\n--\nNu mai vrei aceste emailuri? Dezabonează-te dintr-un clic: {link}"
    if regula.mentiuni:
        subsol += f"\n{regula.mentiuni}"
    db.add(Trimitere(contact_id=contact.id, email=contact.email, campanie=campanie, cheie=cheie, la=acum))
    db.flush()
    sistem.cere(
        db,
        "email",
        cheie=f"crm:{cheie}",
        payload={
            "catre": contact.email,
            "subiect": subiect,
            "text": text.rstrip() + subsol,
            "categorie": "marketing",
            "antete": {
                "List-Unsubscribe": f"<{link}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
        },
    )
    return Rezultat(True)
