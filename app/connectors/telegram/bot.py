"""Comenzile botului (în română) și apărarea intrării: chat permis, actualizare deduplicată.

Fluxul unei actualizări: 1) id-ul se reține (a doua oară: ignorat); 2) conversația trebuie să fie cea permisă
(altfel: ignorat și auditat); 3) comanda se execută într-o singură tranzacție cu auditul ei; 4) răspunsul se
trimite după commit, iar eșecul trimiterii nu schimbă nimic.
"""

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.connectors.telegram.client import TelegramClient, TelegramEroare
from app.connectors.telegram.modele import Actualizare
from app.conturi import cauta_clienti
from app.db import sesiune_agentie
from app.logging import get_logger
from app.operare import audit, backup, health, opriri
from app.operare.opriri import Oprire
from app.operare.tabele import ActualizareTelegram, ConfirmareTelegram

log = get_logger("app.telegram")

VALABILITATE_COD = timedelta(minutes=5)
PASTRARE_ACTUALIZARI = timedelta(days=7)
TIPURI = {
    "publicare": Oprire.PUBLICARE,
    "reclame": Oprire.RECLAME,
    "invatare": Oprire.INVATARE,
    "apeluri_platite": Oprire.APELURI_PLATITE,
}
AJUTOR = (
    "Comenzi:\n"
    "/stare — starea sistemului\n"
    "/opreste <publicare|reclame|invatare|apeluri_platite> — oprește\n"
    "/opreste_client <id sau nume> — oprește un client\n"
    "/porneste <tip> și /porneste_client <id sau nume> — repornire (cere confirmare cu cod)\n"
    "/confirma <cod> — confirmă o repornire\n"
    "/ajutor — acest text"
)
NOTA_STEAGURI = (
    "Notă: oprirea este înregistrată, dar modulele care o citesc (publicare, reclame) "
    "apar în fazele următoare."
)


@dataclass(frozen=True)
class Rezultat:
    """Ce s-a întâmplat (pentru teste și jurnale) și ce se răspunde."""

    rezultat: str
    raspuns: str | None = None


def _hash(cod: str) -> bytes:
    return hashlib.sha256(cod.encode()).digest()


def proceseaza(update: Actualizare, client: TelegramClient | None) -> str:
    """Procesează o actualizare. Întoarce rezultatul (`duplicat`, `chat_necunoscut`, `ignorat`, `comanda`)."""
    with sesiune_agentie() as db:
        rez = _in_tranzactie(db, update)
    if rez.raspuns and client is not None and update.message is not None:
        try:
            client.send_message(update.message.chat.id, rez.raspuns)
        except TelegramEroare as exc:
            log.warning("răspunsul Telegram nu a plecat", extra={"eroare": str(exc)[:200]})
    return rez.rezultat


def _in_tranzactie(db: Session, update: Actualizare) -> Rezultat:
    nou = db.execute(
        pg_insert(ActualizareTelegram)
        .values(update_id=update.update_id)
        .on_conflict_do_nothing()
        .returning(ActualizareTelegram.update_id)
    ).first()
    if nou is None:
        return Rezultat("duplicat")
    db.execute(
        delete(ActualizareTelegram).where(ActualizareTelegram.primit_la < func.now() - PASTRARE_ACTUALIZARI)
    )
    msg = update.message
    if msg is None:
        return Rezultat("ignorat")
    if str(msg.chat.id) != get_settings().telegram_chat_id:
        audit.record(
            db,
            "telegram.chat_necunoscut",
            rezultat="refuzat",
            actor_tip="anonim",
            obiect_tip="telegram",
            detalii={"chat": msg.chat.id, "update": update.update_id},
        )
        return Rezultat("chat_necunoscut")  # fără răspuns: nu confirmăm nimic unui necunoscut
    comanda, _, arg = (msg.text or "").strip().partition(" ")
    comanda = comanda.split("@", 1)[0].lower()
    arg = arg.strip()
    handler = {
        "/stare": lambda: _stare(db),
        "/opreste": lambda: _opreste(db, arg),
        "/opreste_client": lambda: _opreste_client(db, arg),
        "/porneste": lambda: _cere_pornire(db, msg.chat.id, arg, client=False),
        "/porneste_client": lambda: _cere_pornire(db, msg.chat.id, arg, client=True),
        "/confirma": lambda: _confirma(db, msg.chat.id, arg),
    }.get(comanda)
    if handler is None:
        return Rezultat("comanda_necunoscuta", AJUTOR)
    return Rezultat(f"comanda:{comanda[1:]}", handler())


def _stare(db: Session) -> str:
    try:
        db.execute(text("SELECT 1"))
        baza = "ok"
    except Exception:
        baza = "EROARE"
    s = get_settings()
    active = opriri.active(db)
    globale = [o.tip for o in active if o.tip != "client"]
    clienti = sum(1 for o in active if o.tip == "client")
    parti = list(globale) + ([f"{clienti} client(i)"] if clienti else [])
    indicatori = [f"{k} {'ok' if v.bun else 'atenție'}" for k, v in health.indicatori().items()]
    return "\n".join(
        [
            "AMA — stare",
            f"Versiune: {s.version} (aplicația {__version__})",
            f"Mediu: {s.env}",
            f"Baza de date: {baza}",
            f"Opriri active: {', '.join(parti) if parti else 'niciuna'}",
            f"Backup: {backup.rezumat()}",
            f"Indicatori: {', '.join(indicatori) or '–'}",
            NOTA_STEAGURI,
        ]
    )


def _opreste(db: Session, arg: str) -> str:
    tip = TIPURI.get(arg.lower())
    if tip is None:
        return f"Tip necunoscut. Folosește: {', '.join(TIPURI)}."
    schimbat = opriri.seteaza(db, tip, True, canal="telegram", motiv="comandă Telegram")
    return f"{'Oprit' if schimbat else 'Era deja oprit'}: {opriri.ETICHETE[tip]}.\n{NOTA_STEAGURI}"


def _client(db: Session, arg: str) -> tuple[tuple[uuid.UUID, str] | None, str]:
    """(client, mesaj de eroare). Clientul e (id, nume)."""
    if not arg:
        return None, "Dă identificatorul sau numele clientului."
    gasite = cauta_clienti(db, arg)
    if not gasite:
        return None, "Nu am găsit niciun client cu acest id sau nume."
    if len(gasite) > 1:
        return None, "Mai mulți clienți se potrivesc; folosește identificatorul."
    return (gasite[0].id, gasite[0].nume), ""


def _opreste_client(db: Session, arg: str) -> str:
    c, eroare = _client(db, arg)
    if c is None:
        return eroare
    schimbat = opriri.seteaza(
        db, Oprire.CLIENT, True, canal="telegram", motiv="comandă Telegram", tenant_id=c[0]
    )
    return f"{'Oprit' if schimbat else 'Era deja oprit'}: clientul {c[1]}.\n{NOTA_STEAGURI}"


def _cere_pornire(db: Session, chat_id: int, arg: str, *, client: bool) -> str:
    tenant: uuid.UUID | None = None
    tip: Oprire | None
    if client:
        c, eroare = _client(db, arg)
        if c is None:
            return eroare
        tenant, tip, eticheta = c[0], Oprire.CLIENT, f"clientul {c[1]}"
    else:
        tip = TIPURI.get(arg.lower())
        if tip is None:
            return f"Tip necunoscut. Folosește: {', '.join(TIPURI)}."
        eticheta = opriri.ETICHETE[tip].lower()
    cod = f"{secrets.randbelow(10**6):06d}"
    db.execute(delete(ConfirmareTelegram).where(ConfirmareTelegram.chat_id == chat_id))
    db.add(
        ConfirmareTelegram(
            chat_id=chat_id,
            cod_hash=_hash(cod),
            tip=tip.value,
            tenant_id=tenant,
            expira_la=func.now() + VALABILITATE_COD,
        )
    )
    return (
        f"Repornirea ({eticheta}) cere confirmare. În 5 minute trimite:\n/confirma {cod}\n"
        "Dacă nu ai cerut tu repornirea, ignoră mesajul."
    )


def _confirma(db: Session, chat_id: int, cod: str) -> str:
    rand = db.execute(
        select(ConfirmareTelegram, ConfirmareTelegram.expira_la > func.now()).where(
            ConfirmareTelegram.chat_id == chat_id
        )
    ).first()
    if rand is None or not rand[1]:
        return "Nu există nicio repornire în așteptare (sau codul a expirat). Cere-o din nou cu /porneste."
    conf = rand[0]
    if not hmac.compare_digest(conf.cod_hash, _hash(cod)):
        audit.record(
            db, "telegram.confirmare_gresita", rezultat="refuzat", actor_tip="sistem", obiect_tip="telegram"
        )
        db.delete(conf)  # o singură încercare: codul are 6 cifre, deci nu lăsăm loc de ghicit
        return "Cod greșit. Cererea de repornire a fost anulată; cere-o din nou cu /porneste."
    tip = Oprire(conf.tip)
    db.delete(conf)
    opriri.seteaza(db, tip, False, canal="telegram", motiv="confirmat în Telegram", tenant_id=conf.tenant_id)
    return f"Repornit: {opriri.ETICHETE[tip]}."
