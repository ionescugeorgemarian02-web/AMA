"""Biroul de aprobări (F5.9, docs/18 §18.3): ce vede omul pe un card și editarea pe loc.

- `coada(db, acum)`: cererile în așteptare, în ordinea biroului (urgente, termen, prioritate, slot), fiecare
cu textul pe canal,
  verdictele ultimei rulări (cu dovezi și avertismente), pachetul de context (faptele și ofertele aprobate,
  valabile la data
  livrabilului), istoricul versiunilor (cu diferența față de cea anterioară) și întrebările deschise către
  client.
- `editeaza(...)`: o versiune nouă prin `validare.continut.scrie`; cererea veche se anulează și livrabilul se
întoarce ÎN
  VALIDARE (`asteapta_aprobare → in_validare`, doar cu om). După ce trece din nou cascada, revine la
  aprobare (`ciclu`).
  Diferența se salvează în audit ca exemplu de editare.
- `verificare_validata`: înregistrată în `productie.aprobari` — nicio APROBARE pe o versiune care nu a trecut
validarea.
- `statistica_motive(db)`: motivele de respingere, pentru învățare și pentru ecran.
"""

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import creier, productie
from app.operare import audit
from app.productie import Stare, aprobari
from app.productie.reguli_aprobare import MOTIVE_RESPINGERE, StareAprobare
from app.validare import birou_nucleu as nucleu
from app.validare import continut as continut_mod
from app.validare import depozit, intrebari
from app.validare.modele import ContinutLivrabil, VerdictSalvat

COMPONENTA = "om"


class EditareInvalida(ValueError):
    """Editarea nu se poate face (cerere decisă, versiune veche, text gol)."""


def verificare_validata(db: Session, livrabil: productie.Livrabil) -> str | None:
    """Motivul refuzului unei aprobări sau `None`. Un livrabil cu conținut (F5+) se aprobă doar dacă
    versiunea curentă
    a trecut cascada; livrabilele fără conținut salvat (fluxurile de probă din F2) nu sunt atinse."""
    if continut_mod.rand(db, livrabil.id, livrabil.versiune) is None:
        exista = db.execute(
            select(ContinutLivrabil.id).where(ContinutLivrabil.livrabil_id == livrabil.id).limit(1)
        ).first()
        if exista is None:
            return None
        return f"versiunea {livrabil.versiune} nu are conținut validat"
    r = depozit.ultima_rulare(db, livrabil.id)
    if r is None or r.versiune != livrabil.versiune or r.decizie != "trece":
        return f"versiunea {livrabil.versiune} nu a trecut validarea; nu se poate aproba"
    return None


aprobari.inregistreaza_verificare(verificare_validata)


@dataclass
class Card:
    aprobare: productie.Aprobare
    livrabil: productie.Livrabil
    text: str = ""
    campuri: dict[str, Any] = field(default_factory=dict)
    verdicte: list[VerdictSalvat] = field(default_factory=list)
    decizie_validare: str = ""
    fapte: list[Any] = field(default_factory=list)
    oferte: list[Any] = field(default_factory=list)
    versiuni: list[dict[str, Any]] = field(default_factory=list)
    intrebari: list[Any] = field(default_factory=list)
    urgent: bool = False


def _versiuni(db: Session, livrabil_id: uuid.UUID) -> list[dict[str, Any]]:
    randuri = continut_mod.versiuni(db, livrabil_id)
    iesire: list[dict[str, Any]] = []
    anterior = ""
    for r in randuri:
        iesire.append(
            {
                "versiune": r.versiune,
                "autor": r.autor,
                "creat_la": r.creat_la,
                "diferenta": nucleu.diferenta(anterior, r.text) if anterior else [],
            }
        )
        anterior = r.text
    return list(reversed(iesire))


def card(db: Session, ap: productie.Aprobare, lv: productie.Livrabil, acum: dt.datetime) -> Card:
    c = Card(ap, lv, urgent=ap.termen_la - acum < nucleu.URGENT)
    try:
        cont = continut_mod.citeste(db, lv.id)
        c.text, c.campuri = cont.text, dict(cont.campuri)
    except continut_mod.FaraContinut:
        pass
    r = depozit.ultima_rulare(db, lv.id)
    if r is not None:
        c.decizie_validare = r.decizie if r.versiune == lv.versiune else "versiune_noua"
        c.verdicte = [v for v in depozit.verdicte_rulare(db, r.id) if v.rezultat != "trece"]
    la = lv.termen_la or acum
    c.fapte = creier.fapte.pentru_context(db, lv.tenant_id, la)[:12]
    c.oferte = creier.oferte.pentru_context(db, lv.tenant_id, la)[:6]
    c.versiuni = _versiuni(db, lv.id)
    c.intrebari = [q for q in intrebari.ale_livrabilului(db, lv.id) if q.stare == "deschisa"]
    return c


def coada(db: Session, acum: dt.datetime, *, limita: int = 50) -> list[Card]:
    perechi = {str(a.id): (a, lv) for a, lv in aprobari.listeaza(db, doar_in_asteptare=True, limita=500)}
    ordine = nucleu.ordoneaza(
        (nucleu.Cheie(i, a.termen_la, lv.tip, lv.termen_la) for i, (a, lv) in perechi.items()), acum
    )
    return [card(db, *perechi[i], acum) for i in ordine[:limita]]


def editeaza(
    db: Session,
    aprobare_id: uuid.UUID,
    *,
    versiune: int,
    text: str,
    utilizator_id: uuid.UUID,
    campuri: dict[str, Any] | None = None,
) -> productie.Livrabil:
    """Editarea pe loc a versiunii văzute: versiune nouă, cererea se anulează, livrabilul se întoarce în
    validare."""
    text = text.strip()
    if not text:
        raise EditareInvalida("textul nu poate fi gol")
    ap = aprobari.citeste(db, aprobare_id)
    if ap is None:
        raise aprobari.AprobareInexistenta(str(aprobare_id))
    if ap.stare != StareAprobare.IN_ASTEPTARE.value:
        raise EditareInvalida("cererea nu mai așteaptă o decizie")
    lv = productie.blocheaza(db, ap.livrabil_id)
    if ap.versiune != versiune or lv.versiune != versiune:
        raise EditareInvalida(f"ai văzut versiunea {versiune}, iar livrabilul e la versiunea {lv.versiune}")
    vechi = continut_mod.citeste(db, lv.id)
    if text == vechi.text and (campuri is None or campuri == vechi.campuri):
        raise EditareInvalida("textul nu s-a schimbat")
    nou = continut_mod.scrie(
        db,
        lv.id,
        text=text,
        campuri=dict(vechi.campuri if campuri is None else campuri),
        active=list(vechi.active),
        autor=COMPONENTA,
        utilizator_id=utilizator_id,
    )
    productie.muta(
        db,
        lv.id,
        Stare.ASTEAPTA_APROBARE,
        Stare.IN_VALIDARE,
        componenta=COMPONENTA,
        utilizator_id=utilizator_id,
        motiv="editare pe loc în biroul de aprobări",
        detalii={"aprobare": str(ap.id), "versiune": nou.versiune},
    )
    dif = nucleu.diferenta(vechi.text, text)
    audit.record(
        db,
        "aprobare.editare",
        obiect_tip="livrabil",
        obiect_id=lv.id,
        utilizator_id=utilizator_id,
        tenant_id=lv.tenant_id,
        detalii={
            "aprobare": str(ap.id),
            "versiune_veche": versiune,
            "versiune_noua": nou.versiune,
            "scos": [b.text for b in dif if b.tip == "scos"][:20],
            "adaugat": [b.text for b in dif if b.tip == "adaugat"][:20],
        },
    )
    db.refresh(lv)
    return lv


def statistica_motive(db: Session) -> list[tuple[str, str, int]]:
    rows = db.execute(
        select(productie.Aprobare.motiv_cod).where(productie.Aprobare.stare == StareAprobare.RESPINS.value)
    ).scalars()
    return nucleu.statistica_motive(rows, MOTIVE_RESPINGERE)


def a_mai_fost_la_aprobare(db: Session, livrabil_id: uuid.UUID) -> productie.Aprobare | None:
    """Ultima cerere a livrabilului anulată printr-o editare (pentru întoarcerea la aprobare după
    revalidare)."""
    for a in reversed(aprobari.ale_livrabilului(db, livrabil_id)):
        if a.stare == StareAprobare.ANULAT.value:
            return a
    return None
