"""Carantina și contestațiile (F5.10, docs/09 §9.8).

- Un livrabil blocat critic stă în `carantina`, cu dovezile vizibile (`lista`, `detaliu`).
- Iese DOAR printr-o decizie umană înregistrată (`productie.muta` cu `utilizator_id`, motiv obligatoriu,
audit):
  `elibereaza(..., spre="validare" | "reparatie")` îl trimite înapoi în cascadă sau la autor,
`respinge_definitiv`
  îl anulează. Mașina de stări nu are drum din carantină spre aprobare sau publicare.
- Orice verdict salvat se poate contesta (`contesta`): contestația este un exemplu PROPUS pentru setul de aur
  (`exemple_propuse`, sursa `contestatie`, eticheta așteptată = opusul verdictului) și intră în statistica
  validatorului (`statistica_contestatii`). Un om îl promovează (`exemple.promoveaza`); cel promovat intră în
banc.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import productie
from app.operare import audit
from app.productie import Stare
from app.validare import continut as continut_mod
from app.validare import depozit, exemple
from app.validare.modele import ExempluPropus, VerdictSalvat

MOTIV_MINIM = 5
SPRE = {"validare": Stare.IN_VALIDARE, "reparatie": Stare.IN_REPARATIE}


class DecizieInvalida(ValueError):
    """Decizia nu respectă regulile (motiv lipsă, livrabil care nu e în carantină, destinație necunoscută)."""


def _motiv(motiv: str) -> str:
    m = motiv.strip()
    if len(m) < MOTIV_MINIM:
        raise DecizieInvalida("decizia cere un motiv (cel puțin câteva cuvinte)")
    return m[:500]


@dataclass(frozen=True)
class InCarantina:
    livrabil: productie.Livrabil
    verdicte: list[VerdictSalvat]  # eșecurile din ultima rulare (dovezile critice primele)


def _esecuri_ultimei_rulari(db: Session, livrabil_id: uuid.UUID) -> list[VerdictSalvat]:
    r = depozit.ultima_rulare(db, livrabil_id)
    if r is None:
        return []
    v = [x for x in depozit.verdicte_rulare(db, r.id) if x.rezultat == "esec"]
    return sorted(v, key=lambda x: (x.severitate != "critica", x.validator))


def lista(db: Session) -> list[InCarantina]:
    """Livrabilele în carantină vizibile sesiunii (RLS), cele mai vechi primele."""
    livrabile = db.execute(
        select(productie.Livrabil)
        .where(productie.Livrabil.stare == Stare.CARANTINA.value)
        .order_by(productie.Livrabil.actualizat_la, productie.Livrabil.id)
    ).scalars()
    return [InCarantina(lv, _esecuri_ultimei_rulari(db, lv.id)) for lv in livrabile]


def detaliu(db: Session, livrabil_id: uuid.UUID) -> dict[str, Any] | None:
    lv = productie.citeste(db, livrabil_id)
    if lv is None:
        return None
    try:
        c = continut_mod.citeste(db, livrabil_id)
    except continut_mod.FaraContinut:
        c = None
    return {
        "livrabil": lv,
        "continut": c,
        "esecuri": _esecuri_ultimei_rulari(db, livrabil_id),
        "validari": depozit.pentru_ecran(db, livrabil_id),
        "contestate": contestate(db, livrabil_id),
    }


def elibereaza(
    db: Session, livrabil_id: uuid.UUID, *, spre: str, motiv: str, utilizator_id: uuid.UUID
) -> productie.Livrabil:
    """Decizia unui om: înapoi în validare sau la reparație. Niciodată direct spre publicare."""
    if spre not in SPRE:
        raise DecizieInvalida("eliberarea duce înapoi în validare sau la reparație")
    m = _motiv(motiv)
    productie.muta(
        db,
        livrabil_id,
        Stare.CARANTINA,
        SPRE[spre],
        componenta="om",
        motiv=m,
        utilizator_id=utilizator_id,
        detalii={"decizie": "eliberare", "spre": spre},
    )
    lv = productie.citeste(db, livrabil_id)
    if lv is None:
        raise productie.LivrabilInexistent(str(livrabil_id))
    audit.record(
        db,
        "carantina.eliberare",
        obiect_tip="livrabil",
        obiect_id=livrabil_id,
        utilizator_id=utilizator_id,
        tenant_id=lv.tenant_id,
        detalii={"spre": spre, "motiv": m},
    )
    return lv


def respinge_definitiv(
    db: Session, livrabil_id: uuid.UUID, *, motiv: str, utilizator_id: uuid.UUID
) -> productie.Livrabil:
    """Decizia unui om: livrabilul nu se mai folosește (stare finală `anulat`)."""
    m = _motiv(motiv)
    productie.muta(
        db,
        livrabil_id,
        Stare.CARANTINA,
        Stare.ANULAT,
        componenta="om",
        motiv=m,
        utilizator_id=utilizator_id,
        detalii={"decizie": "respingere_definitiva"},
    )
    lv = productie.citeste(db, livrabil_id)
    if lv is None:
        raise productie.LivrabilInexistent(str(livrabil_id))
    audit.record(
        db,
        "carantina.respingere",
        obiect_tip="livrabil",
        obiect_id=livrabil_id,
        utilizator_id=utilizator_id,
        tenant_id=lv.tenant_id,
        detalii={"motiv": m},
    )
    return lv


def contesta(
    db: Session, verdict_id: uuid.UUID, *, motiv: str, utilizator_id: uuid.UUID
) -> tuple[ExempluPropus, bool]:
    """„Verdict greșit” + motiv. Întoarce (exemplul propus, creat). Idempotent pe verdict."""
    m = _motiv(motiv)
    v = db.get(VerdictSalvat, verdict_id)
    if v is None:
        raise LookupError(str(verdict_id))
    lv = productie.citeste(db, v.livrabil_id)
    if lv is None:
        raise LookupError(str(v.livrabil_id))
    blocat = v.rezultat != "trece"
    e, creat = exemple.propune(
        db,
        v,
        sursa="contestatie",
        asteptat="trece" if blocat else "esec",
        severitate=None if blocat else "majora",
        motiv=m,
        utilizator_id=utilizator_id,
        tip=lv.tip,
        canal=lv.canal,
    )
    if creat:
        audit.record(
            db,
            "verdict.contestat",
            obiect_tip="verdict",
            obiect_id=verdict_id,
            utilizator_id=utilizator_id,
            tenant_id=v.tenant_id,
            detalii={"validator": v.validator, "treapta": v.treapta, "motiv": m},
        )
    return e, creat


def contestate(db: Session, livrabil_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        db.execute(
            select(ExempluPropus.verdict_id).where(
                ExempluPropus.livrabil_id == livrabil_id, ExempluPropus.sursa == "contestatie"
            )
        ).scalars()
    )


def statistica_contestatii(db: Session) -> dict[str, dict[str, Any]]:
    """Pe validator: verdicte salvate, contestate, rata de contestare și cele promovate în setul de aur."""
    total: dict[str, int] = {}
    for g, n in db.execute(select(VerdictSalvat.validator, func.count()).group_by(VerdictSalvat.validator)):
        total[g] = n
    cont: dict[str, dict[str, int]] = {}
    for validator, stare, n in db.execute(
        select(ExempluPropus.validator, ExempluPropus.stare, func.count())
        .where(ExempluPropus.sursa == "contestatie")
        .group_by(ExempluPropus.validator, ExempluPropus.stare)
    ):
        cont.setdefault(validator, {})[stare] = n
    iesire = {}
    for g in sorted(set(total) | set(cont)):
        c = cont.get(g, {})
        n = sum(c.values())
        iesire[g] = {
            "verdicte": total.get(g, 0),
            "contestate": n,
            "rata": round(n / total[g], 4) if total.get(g) else None,
            "promovate": c.get("promovat", 0),
            "respinse": c.get("respins", 0),
        }
    return iesire
