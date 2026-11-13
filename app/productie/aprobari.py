"""Cererile de aprobare (F2.8, 7.3, 18.3, 19.4): obiectul de aprobare, decizia legată de versiune, termene.

- `cere`: livrabilul `validat` primește o cerere pentru versiunea lui curentă, adresată unui operator sau
  clientului, cu termen (48 h, dar nu după slotul livrabilului) și reamintire; livrabilul trece în `așteaptă
  aprobare`; se anunță omul.
- `decide`: aprobă sau respinge (respingerea cere un motiv). Verifică dreptul rolului pentru acest decident
  și că decizia privește versiunea CURENTĂ; o aprobare dată pe o versiune veche nu aprobă versiunea nouă.
  Două decizii simultane pe aceeași cerere: una singură reușește (livrabilul e blocat întâi, apoi cererea;
  ordinea e aceeași peste tot, deci nu există blocaj reciproc).
- `expira_restante`: o cerere neprimită la timp devine `expirat`, livrabilul devine `expirat` (de unde se
  reprogramează); NICIODATĂ nu se aprobă singură (7.3, „fără aprobare automată”). Rulează din jobul programat.
- `trimite_reamintiri`: anunț înainte de termen, o singură dată pe cerere.

Toate funcțiile scriu auditul (cine, când, ce versiune) și emit evenimente; anunțurile pleacă după commit.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.conturi.roluri import Rol
from app.logging import get_logger
from app.operare import audit, evenimente
from app.operare.notificari import Nivel
from app.productie import aprobari_baza, autonomie, reguli_aprobare
from app.productie.anunturi import anunta
from app.productie.modele import Aprobare, Livrabil
from app.productie.reguli_aprobare import Decident, Hotarare, StareAprobare
from app.productie.reguli_autonomie import Decizie
from app.productie.stari import Stare
from app.productie.tranzitii import EroareProductie, Temei, blocheaza, muta

log = get_logger("app.productie")
COMPONENTA = "L2"  # Biroul de aprobări (5.13)


class EroareAprobare(EroareProductie):
    """Baza erorilor cererilor de aprobare."""


class AprobareInexistenta(EroareAprobare):
    """Nu există, sau aparține altui client (izolarea pe client o ascunde)."""


class FaraDrept(EroareAprobare):
    """Rolul nu are voie să decidă o cerere adresată acestui decident."""


class DejaDecisa(EroareAprobare):
    def __init__(self, stare: str) -> None:
        super().__init__(f"cererea nu mai este în așteptare (este „{reguli_aprobare.ETICHETE_STARE[stare]}”)")
        self.stare = stare


class VersiuneVeche(EroareAprobare):
    """Decizia privește o altă versiune decât cea curentă a livrabilului."""


class MotivLipsa(EroareAprobare):
    """Respingerea cere un motiv (cel puțin 3 caractere)."""


class NivelUmbra(EroareAprobare):
    """Nivelul de autonomie al clientului este L0 (umbră): livrabilul nu merge spre aprobare sau publicare."""


class NuSeCereAprobare(EroareAprobare):
    """Livrabilul nu este în starea în care se poate cere o aprobare."""


TermenTrecut = reguli_aprobare.TermenTrecut


class VersiuneNevalidata(EroareAprobare):
    """Versiunea de aprobat nu a trecut validarea (F5.9: nicio aprobare pe o versiune nevalidată)."""


# Verificări înainte de o APROBARE, înregistrate de modulele de deasupra (validarea, F5.9): primesc
# livrabilul blocat și
# întorc motivul refuzului sau `None`. Producția nu importă validarea; validarea se înregistrează aici la
# import.
VERIFICARI_APROBARE: list[Callable[[Session, Livrabil], str | None]] = []


def inregistreaza_verificare(f: Callable[[Session, Livrabil], str | None]) -> None:
    if f not in VERIFICARI_APROBARE:
        VERIFICARI_APROBARE.append(f)


# Punct de extensie (F6): ce urmează după o decizie aplicată, în aceeași tranzacție (pachetul de publicare
# asistată la aprobare, exemplele pozitive și negative din feedback). Fiecare funcție decide singură dacă
# livrabilul e al ei.
DUPA_DECIZIE: list[Callable[[Session, Aprobare, Livrabil, Hotarare], None]] = []


def inregistreaza_dupa_decizie(f: Callable[[Session, Aprobare, Livrabil, Hotarare], None]) -> None:
    if f not in DUPA_DECIZIE:
        DUPA_DECIZIE.append(f)


@dataclass(frozen=True)
class RezultatDecizie:
    aprobare: Aprobare
    aplicat: bool  # decizia omului s-a aplicat (altfel cererea expirase între timp)
    stare_livrabil: Stare


def _acum(acum: dt.datetime | None) -> dt.datetime:
    return acum or dt.datetime.now(dt.UTC)


def _ora(t: dt.datetime) -> str:
    return t.astimezone(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")


# --- citire ---------------------------------------------------------------------------------------------


def citeste(db: Session, aprobare_id: uuid.UUID) -> Aprobare | None:
    return aprobari_baza.gaseste(db, aprobare_id)


def cerere_activa(db: Session, livrabil_id: uuid.UUID) -> Aprobare | None:
    return aprobari_baza.in_asteptare(db, livrabil_id)


def listeaza(
    db: Session, *, doar_in_asteptare: bool = True, limita: int = 100
) -> list[tuple[Aprobare, Livrabil]]:
    """Cererile (cele în așteptare primele, după termen) împreună cu livrabilul lor."""
    q = select(Aprobare, Livrabil).join(Livrabil, Livrabil.id == Aprobare.livrabil_id)
    if doar_in_asteptare:
        q = q.where(Aprobare.stare == StareAprobare.IN_ASTEPTARE.value)
    q = q.order_by(
        (Aprobare.stare != StareAprobare.IN_ASTEPTARE.value), Aprobare.termen_la, Aprobare.creat_la.desc()
    ).limit(limita)
    return [(a, liv) for a, liv in db.execute(q).all()]


def ale_livrabilului(db: Session, livrabil_id: uuid.UUID) -> list[Aprobare]:
    """Toate cererile unui livrabil (urma lui, 18.4), cele mai vechi primele."""
    return list(
        db.execute(
            select(Aprobare).where(Aprobare.livrabil_id == livrabil_id).order_by(Aprobare.creat_la)
        ).scalars()
    )


def anuleaza_cererea_in_asteptare(db: Session, livrabil_id: uuid.UUID) -> Aprobare | None:
    """Livrabilul a fost anulat: cererea lui în așteptare (dacă are una) devine `anulat`, ca să nu mai
    apară la
    aprobări."""
    return aprobari_baza.anuleaza_in_asteptare(db, livrabil_id)


def numar_in_asteptare(db: Session) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(Aprobare)
            .where(Aprobare.stare == StareAprobare.IN_ASTEPTARE.value)
        ).scalar_one()
    )


# --- creare ---------------------------------------------------------------------------------------------


def cere(
    db: Session,
    livrabil_id: uuid.UUID,
    *,
    decident: Decident = Decident.OPERATOR,
    utilizator_id: uuid.UUID | None = None,
    componenta: str = COMPONENTA,
    acum: dt.datetime | None = None,
) -> Aprobare:
    """Deschide o cerere pentru versiunea curentă a livrabilului și îl mută în `așteaptă aprobare`.

    Livrabilul trebuie să fie `validat` (sau deja `așteaptă aprobare`, fără cerere activă). Aruncă
    `TermenTrecut` dacă slotul livrabilului a trecut (nu se scrie nimic: apelantul îl mută în `expirat`)."""
    acum = _acum(acum)
    s = get_settings()
    livrabil = blocheaza(db, livrabil_id)
    stare = Stare(livrabil.stare)
    if stare not in (Stare.VALIDAT, Stare.ASTEAPTA_APROBARE):
        raise NuSeCereAprobare(f"aprobarea se cere pentru un livrabil validat, nu „{stare.value}”")
    if aprobari_baza.in_asteptare(db, livrabil.id) is not None:
        raise NuSeCereAprobare("livrabilul are deja o cerere de aprobare în așteptare")
    if autonomie.decide(db, livrabil) is Decizie.UMBRA:
        raise NivelUmbra(
            "nivelul de autonomie L0 (umbră): livrabilul se produce, dar nu se aprobă și nu se publică"
        )
    termen, reamintire = reguli_aprobare.calculeaza_termene(
        acum, livrabil.termen_la, termen_ore=s.aprobare_termen_ore, reamintire_ore=s.aprobare_reamintire_ore
    )
    ap = aprobari_baza.deschide(
        db, livrabil, decident, termen_la=termen, reamintire_la=reamintire, creat_de=utilizator_id
    )
    if stare == Stare.VALIDAT:
        muta(
            db,
            livrabil.id,
            Stare.VALIDAT,
            Stare.ASTEAPTA_APROBARE,
            componenta=componenta,
            motiv=f"cerere de aprobare pentru versiunea {ap.versiune}",
            utilizator_id=utilizator_id,
            temei=Temei.aprobare(ap.id),
        )
    audit.record(
        db,
        "aprobare.creata",
        obiect_tip="aprobare",
        obiect_id=ap.id,
        utilizator_id=utilizator_id,
        tenant_id=ap.tenant_id,
        actor_tip=None if utilizator_id else "sistem",
        detalii={
            "livrabil": livrabil.id,
            "versiune": ap.versiune,
            "decident": decident.value,
            "termen_la": _ora(termen),
        },
    )
    evenimente.emite(
        db,
        "aprobare.creata",
        sursa="productie",
        obiect_tip="aprobare",
        obiect_id=ap.id,
        tenant_id=ap.tenant_id,
        date={"livrabil": str(livrabil.id), "versiune": ap.versiune, "decident": decident.value},
    )
    anunta(
        db,
        Nivel.IMPORTANT,
        "Aprobare nouă în așteptare",
        f"Un livrabil ({livrabil.tip}, {livrabil.canal}) așteaptă decizia {decident.value}ului "
        f"până la {_ora(termen)}.",
        url="/aprobari",
    )
    return ap


# --- decizia ----------------------------------------------------------------------------------------------


def decide(
    db: Session,
    aprobare_id: uuid.UUID,
    hotarare: Hotarare,
    *,
    utilizator_id: uuid.UUID,
    rol: Rol | str,
    versiune: int | None = None,
    motiv_standard: str | None = None,
    motiv: str = "",
    acum: dt.datetime | None = None,
) -> RezultatDecizie:
    """Aprobă sau respinge o cerere. `versiune`: versiunea văzută de om (o decizie pe alta e refuzată).

    Aruncă `AprobareInexistenta`, `FaraDrept`, `DejaDecisa`, `VersiuneVeche`, `MotivLipsa`. Dacă termenul
    a trecut între timp, cererea EXPIRĂ (nu se aprobă) și rezultatul spune `aplicat=False`."""
    acum = _acum(acum)
    motiv = motiv.strip()
    initiala = aprobari_baza.gaseste(db, aprobare_id)
    if initiala is None:
        raise AprobareInexistenta(str(aprobare_id))
    if not reguli_aprobare.poate_decide(rol, Decident(initiala.decident)):
        raise FaraDrept(f"rolul nu poate decide o cerere adresată {initiala.decident}ului")
    if hotarare is Hotarare.RESPINS and not motiv_standard and not reguli_aprobare.motiv_valid(motiv):
        raise MotivLipsa("respingerea cere un motiv: unul din listă sau o frază (cel puțin 3 caractere)")
    if motiv_standard is not None and motiv_standard not in reguli_aprobare.MOTIVE_RESPINGERE:
        raise MotivLipsa("motiv standard necunoscut")
    livrabil = blocheaza(db, initiala.livrabil_id)  # întâi livrabilul, apoi cererea: aceeași ordine peste tot
    if hotarare is Hotarare.APROBAT and autonomie.decide(db, livrabil) is Decizie.UMBRA:
        raise NivelUmbra(
            "nivelul de autonomie al clientului a coborât la L0 (umbră): nu se aprobă pentru publicare"
        )
    if hotarare is Hotarare.APROBAT:
        for verificare in VERIFICARI_APROBARE:
            refuz = verificare(db, livrabil)
            if refuz:
                raise VersiuneNevalidata(refuz)
    ap = aprobari_baza.gaseste(db, aprobare_id, blocheaza=True)
    if ap is None:  # pragmatic: nu dispare, dar tipurile o cer
        raise AprobareInexistenta(str(aprobare_id))
    if ap.stare != StareAprobare.IN_ASTEPTARE.value:
        raise DejaDecisa(ap.stare)
    if ap.versiune != livrabil.versiune or (versiune is not None and versiune != ap.versiune):
        raise VersiuneVeche(
            f"cererea e pentru versiunea {ap.versiune}, iar livrabilul e la versiunea {livrabil.versiune}"
            + (
                f" (ai văzut versiunea {versiune})"
                if versiune is not None and versiune != ap.versiune
                else ""
            )
        )
    if acum >= ap.termen_la:
        _expira(db, ap, livrabil, acum)
        return RezultatDecizie(ap, aplicat=False, stare_livrabil=Stare(livrabil.stare))
    ap.stare = StareAprobare.APROBAT.value if hotarare is Hotarare.APROBAT else StareAprobare.RESPINS.value
    ap.decis_de = utilizator_id
    ap.decis_la = func.now()
    if hotarare is Hotarare.RESPINS:
        text_motiv = motiv or reguli_aprobare.MOTIVE_RESPINGERE.get(motiv_standard or "", "")
        ap.motiv, ap.motiv_cod = text_motiv[: reguli_aprobare.MOTIV_MAXIM], motiv_standard
    elif motiv:
        ap.motiv = motiv[: reguli_aprobare.MOTIV_MAXIM]
    db.flush()
    tinta = Stare.APROBAT if hotarare is Hotarare.APROBAT else Stare.RESPINS
    muta(
        db,
        livrabil.id,
        Stare.ASTEAPTA_APROBARE,
        tinta,
        componenta=COMPONENTA,
        motiv=(motiv or f"{hotarare.value} pentru versiunea {ap.versiune}")[:300],
        utilizator_id=utilizator_id,
        temei=Temei.aprobare(ap.id),
    )
    audit.record(
        db,
        f"aprobare.{'aprobata' if hotarare is Hotarare.APROBAT else 'respinsa'}",
        obiect_tip="aprobare",
        obiect_id=ap.id,
        utilizator_id=utilizator_id,
        tenant_id=ap.tenant_id,
        detalii={
            "livrabil": livrabil.id,
            "versiune": ap.versiune,
            "decident": ap.decident,
            "motiv": motiv,
            "motiv_standard": motiv_standard,
        },
    )
    evenimente.emite(
        db,
        f"aprobare.{hotarare.value}",
        sursa="productie",
        obiect_tip="aprobare",
        obiect_id=ap.id,
        tenant_id=ap.tenant_id,
        utilizator_id=utilizator_id,
        date={"livrabil": str(livrabil.id), "versiune": ap.versiune},
    )
    for dupa in DUPA_DECIZIE:
        dupa(db, ap, livrabil, hotarare)
    db.refresh(livrabil)
    return RezultatDecizie(ap, aplicat=True, stare_livrabil=Stare(livrabil.stare))


# --- expirare și reamintiri (jobul programat) ---------------------------------------------------


def _expira(db: Session, ap: Aprobare, livrabil: Livrabil, acum: dt.datetime) -> None:
    """Cererea (blocată, în așteptare) expiră; livrabilul care o aștepta expiră și el. Nu se aprobă nimic."""
    ap.stare = StareAprobare.EXPIRAT.value
    ap.decis_la = func.now()
    db.flush()
    if Stare(livrabil.stare) == Stare.ASTEAPTA_APROBARE and livrabil.versiune == ap.versiune:
        muta(
            db,
            livrabil.id,
            Stare.ASTEAPTA_APROBARE,
            Stare.EXPIRAT,
            componenta=COMPONENTA,
            motiv=f"termenul de aprobare ({_ora(ap.termen_la)}) a trecut fără decizie",
            temei=Temei.aprobare(ap.id),
        )
    audit.record(
        db,
        "aprobare.expirata",
        obiect_tip="aprobare",
        obiect_id=ap.id,
        tenant_id=ap.tenant_id,
        actor_tip="sistem",
        detalii={"livrabil": livrabil.id, "versiune": ap.versiune, "termen_la": _ora(ap.termen_la)},
    )
    evenimente.emite(
        db,
        "aprobare.expirata",
        sursa="productie",
        obiect_tip="aprobare",
        obiect_id=ap.id,
        tenant_id=ap.tenant_id,
        date={"livrabil": str(livrabil.id), "versiune": ap.versiune},
    )


def expira_restante(db: Session, *, acum: dt.datetime | None = None, limita: int = 200) -> list[uuid.UUID]:
    """Expiră cererile al căror termen a trecut. Sesiune de agenție (toți clienții); fiecare cerere are
    propriul savepoint, deci una stricată nu le oprește pe celelalte. Întoarce cererile expirate."""
    acum = _acum(acum)
    candidate = db.execute(
        select(Aprobare.id, Aprobare.livrabil_id)
        .where(Aprobare.stare == StareAprobare.IN_ASTEPTARE.value, Aprobare.termen_la <= acum)
        .order_by(Aprobare.termen_la)
        .limit(limita)
    ).all()
    expirate: list[uuid.UUID] = []
    for ap_id, livrabil_id in candidate:
        try:
            with db.begin_nested():
                livrabil = blocheaza(db, livrabil_id)
                ap = aprobari_baza.gaseste(db, ap_id, blocheaza=True)
                if ap is None or ap.stare != StareAprobare.IN_ASTEPTARE.value or ap.termen_la > acum:
                    continue
                _expira(db, ap, livrabil, acum)
                tip, canal = livrabil.tip, livrabil.canal
        except Exception as exc:
            log.error("expirarea unei cereri a eșuat", extra={"tip_eroare": type(exc).__name__})
            continue
        expirate.append(ap_id)
        anunta(
            db,
            Nivel.IMPORTANT,
            "Aprobare expirată",
            f"Un livrabil ({tip}, {canal}) nu a primit decizie la timp: nu se publică și se reprogramează.",
            url="/aprobari",
        )
    return expirate


def trimite_reamintiri(db: Session, *, acum: dt.datetime | None = None, limita: int = 200) -> list[uuid.UUID]:
    """Anunț înainte de termen, o singură dată pe cerere. Sesiune de agenție."""
    acum = _acum(acum)
    cereri = (
        db.execute(
            select(Aprobare)
            .where(
                Aprobare.stare == StareAprobare.IN_ASTEPTARE.value,
                Aprobare.reamintire_la <= acum,
                Aprobare.reamintit_la.is_(None),
                Aprobare.termen_la > acum,
            )
            .order_by(Aprobare.termen_la)
            .limit(limita)
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )
    trimise: list[uuid.UUID] = []
    for ap in cereri:
        ap.reamintit_la = func.now()
        trimise.append(ap.id)
        anunta(
            db,
            Nivel.IMPORTANT,
            "Reamintire: aprobare în așteptare",
            f"O cerere de aprobare expiră la {_ora(ap.termen_la)}. Fără decizie, livrabilul nu se publică.",
            url="/aprobari",
        )
    db.flush()
    return trimise
