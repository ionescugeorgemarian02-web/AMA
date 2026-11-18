"""Inboxul social (F12.7, docs/17 §17.8): citirea mesajelor și a comentariilor de pe canalele aprobate, cu
clasificare.

- **Doar canalele aprobate de proprietar** (`aproba_canal`) se citesc; restul nu există pentru platformă.
  Citirea trece prin ușa executorului (`app.operare.efecte.inbox`), ca orice atingere a unei platforme.
- **O singură dată pe mesaj:** cheia e canalul și id-ul extern; recitirea nu dublează nimic.
- **Clasificarea e pe reguli** (componentă D, D-024), în ordinea prudenței: spam/abuz, subiect sensibil
  (sănătate, juridic, bani), critică, cerere de preț, întrebare, laudă, altfel neclar. Un mesaj care pare și
  critică și întrebare e critică: ajunge la om. Textul se compară fără diacritice și fără majuscule.
- Ce face platforma cu fiecare clasă (răspuns, escaladare, ascundere) e în `app.crm.raspunsuri` (F12.8).
- Jobul `crm.inbox` citește la 5 minute (ținta de răspuns la întrebările simple e sub 15 minute [I]).
"""

import datetime as dt
import re
import unicodedata
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.crm.modele import CanalInbox, MesajInbox
from app.crm.registru import CrmRefuzat
from app.db import sesiune_agentie
from app.operare import audit, motor, urme
from app.operare.efecte import inbox as usa_inbox

NUME_JOB = "crm.inbox"
CLASE = ("intrebare", "cerere_pret", "lauda", "critica", "sensibil", "spam", "neclar")
ETICHETE_CLASA = {
    "intrebare": "întrebare",
    "cerere_pret": "cerere de preț sau ofertă",
    "lauda": "laudă",
    "critica": "critică sau reclamație",
    "sensibil": "subiect sensibil",
    "spam": "spam, înșelătorie sau abuz",
    "neclar": "mesaj neclar",
}


def _norma(text: str) -> str:
    fara = unicodedata.normalize("NFKD", text)
    return "".join(c for c in fara if not unicodedata.combining(c)).lower()


def _r(*cuvinte: str) -> re.Pattern[str]:
    return re.compile(r"(?<![a-z])(?:" + "|".join(cuvinte) + r")", re.IGNORECASE)


# Reguli [I], pe text fără diacritice. Ordinea contează (prima potrivire câștigă).
REGULI: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "spam",
        "link și momeală",
        _r(
            r"(?:castig|bitcoin|crypto|forex|investitie garantat|premiu|click aici)[^\n]*https?://",
            r"https?://\S+[^\n]*(?:castig|bitcoin|crypto|premiu)",
        ),
    ),
    (
        "spam",
        "înșelătorie sau reclamă nesolicitată",
        _r(
            r"ai castigat",
            r"bitcoin",
            r"crypto",
            r"forex",
            r"urmaritori gratuit",
            r"followers",
            r"promoveaza-ti contul",
            r"dm pentru colaborare platit",
        ),
    ),
    ("spam", "limbaj abuziv", _r(r"idiot", r"proast[ai]", r"dobitoc", r"handicapat", r"jeg", r"nenorocit")),
    (
        "sensibil",
        "sănătate",
        _r(r"medic", r"boala", r"tratament", r"diagnostic", r"simptom", r"sarcina", r"medicament", r"alergi"),
    ),
    (
        "sensibil",
        "juridic",
        _r(
            r"avocat",
            r"proces",
            r"instant",
            r"juridic",
            r"amenda",
            r"anpc",
            r"plangere penala",
            r"gdpr",
            r"date personale",
        ),
    ),
    (
        "sensibil",
        "bani",
        _r(r"credit", r"imprumut", r"datori", r"rambursa", r"banii inapoi", r"chargeback", r"rate la"),
    ),
    (
        "critica",
        "nemulțumire",
        _r(
            r"dezamagit",
            r"nemultumit",
            r"reclamati",
            r"groaznic",
            r"oribil",
            r"jalnic",
            r"nu (?:mai )?recomand",
            r"nu functioneaza",
            r"nu a mers",
            r"n-a mers",
            r"intarzi",
            r"nu mi-a raspuns",
            r"teapa",
            r"bataie de joc",
        ),
    ),
    (
        "cerere_pret",
        "preț sau ofertă",
        _r(r"pret", r"cat costa", r"costul", r"tarif", r"oferta", r"pachet", r"abonament"),
    ),
    ("intrebare", "întrebare", re.compile(r"\?|^(?:cum|cand|unde|ce|care|aveti|se poate|lucrati|faceti)\b")),
    (
        "lauda",
        "laudă",
        _r(
            r"multumesc",
            r"multumim",
            r"super",
            r"bravo",
            r"minunat",
            r"excelent",
            r"felicitari",
            r"genial",
            r"top",
            r"❤",
            r"👏",
            r"😍",
        ),
    ),
)


def clasifica(text: str) -> tuple[str, str]:
    """Clasa și motivul (pur). Un text gol sau fără niciun semnal e „neclar”."""
    t = _norma(text).strip()
    for clasa, motiv, regula in REGULI:
        if t and regula.search(t):
            return clasa, motiv
    return "neclar", "niciun semnal"


def canale_posibile() -> tuple[str, ...]:
    return usa_inbox.canale()


def aproba_canal(db: Session, canal: str, *, utilizator_id: uuid.UUID, nivel: str = "L1") -> None:
    """Aprobă citirea canalului, cu nivelul de autonomie al răspunsurilor (L0–L4; implicit L1: se propune)."""
    if canal not in usa_inbox.canale():
        raise CrmRefuzat("canal necunoscut sau fără cititor oficial")
    if nivel not in ("L0", "L1", "L2", "L3", "L4"):
        raise CrmRefuzat("nivel de autonomie necunoscut")
    db.execute(
        insert(CanalInbox)
        .values(canal=canal, aprobat_de=utilizator_id, activ=True, nivel=nivel)
        .on_conflict_do_update(
            index_elements=["canal"], set_={"activ": True, "aprobat_de": utilizator_id, "nivel": nivel}
        )
    )
    audit.record(
        db,
        "crm.inbox_canal_aprobat",
        obiect_tip="canal",
        obiect_id=canal,
        utilizator_id=utilizator_id,
        detalii={"nivel": nivel},
    )
    urme.inregistreaza(db, "crm", "inbox_canal_aprobat", obiect_tip="canal", obiect_id=canal)


def opreste_canal(db: Session, canal: str, *, utilizator_id: uuid.UUID) -> None:
    c = db.get(CanalInbox, canal)
    if c is None:
        raise CrmRefuzat("canalul nu a fost aprobat")
    c.activ = False
    audit.record(
        db, "crm.inbox_canal_oprit", obiect_tip="canal", obiect_id=canal, utilizator_id=utilizator_id
    )


def citeste(db: Session, acum: dt.datetime | None = None) -> dict[str, int]:
    """Citește canalele aprobate și active. Întoarce câte mesaje noi pe clasă."""
    acum = acum or dt.datetime.now(dt.UTC)
    noi: dict[str, int] = {}
    for c in db.scalars(
        select(CanalInbox).where(CanalInbox.activ.is_(True)).with_for_update(skip_locked=True)
    ):
        try:
            primite = usa_inbox.citeste(c.canal, c.citit_pana_la)
        except LookupError:
            continue
        for m in primite:
            clasa, motiv = clasifica(m["text"])
            r = db.execute(
                insert(MesajInbox)
                .values(
                    canal=c.canal,
                    id_extern=str(m["id_extern"])[:200],
                    tip=m["tip"],
                    fir=str(m["fir"])[:200],
                    autor=str(m["autor"])[:200],
                    text=str(m["text"])[:4000],
                    primit_la=m["primit_la"],
                    clasa=clasa,
                    motiv_clasa=motiv,
                    citit_la=acum,
                )
                .on_conflict_do_nothing(index_elements=["canal", "id_extern"])
                .returning(MesajInbox.id)
            ).first()
            if r is None:
                continue
            noi[clasa] = noi.get(clasa, 0) + 1
            urme.inregistreaza(
                db, "inbox", "clasificare", obiect_tip="mesaj_inbox", obiect_id=str(r[0]),
                intrari={"canal": c.canal, "tip": m["tip"]}, iesiri={"clasa": clasa, "motiv": motiv},
            )  # fmt: skip
            c.citit_pana_la = max(c.citit_pana_la or m["primit_la"], m["primit_la"])
    return noi


def mesaje(db: Session, *, clasa: str = "", limita: int = 200) -> list[MesajInbox]:
    q = select(MesajInbox).order_by(MesajInbox.primit_la.desc()).limit(limita)
    if clasa:
        q = q.where(MesajInbox.clasa == clasa)
    return list(db.scalars(q))


def canale(db: Session) -> list[CanalInbox]:
    return list(db.scalars(select(CanalInbox).order_by(CanalInbox.canal)))


def ruleaza(acum: dt.datetime | None = None) -> dict[str, int]:
    """Citește și apoi tratează mesajele noi (F12.8), în aceeași tranzacție."""
    from app.crm import raspunsuri  # import târziu: răspunsurile folosesc clasele de aici

    with sesiune_agentie() as db:
        noi = citeste(db, acum)
        raspunsuri.trateaza(db, acum)
        return noi


@motor.pas("crm.pas_inbox")
def _pas() -> str:
    return f"{sum(ruleaza().values())} mesaje noi"


@motor.flux(NUME_JOB)
def flux(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _pas()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME_JOB, "*/5 * * * *", flux)


declara_programari()
