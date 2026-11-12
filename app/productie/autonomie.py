"""Nivelurile de autonomie pe client și pe clasă de acțiune (F2.10, 7.4, ADR-12): stocare, schimbare, decizie.

- Matricea: pentru fiecare client, cinci clase de acțiuni, fiecare cu un nivel L0–L4. Fără rând: L1.
- `decide(db, livrabil)` răspunde „cere aprobare?” (vezi `reguli_autonomie`): nivelul clientului pentru
  clasa livrabilului, canalele cu consimțământ per postare (TikTok) rămase la L1, eșantionul determinist
  de la L2 / L3. Rata eșantionului și lista canalelor vin din configurare (`AMA_AUTONOMIE_ESANTION_L2` /
  `_L3`, `AMA_CANALE_CONSIMTAMANT`).
- Schimbarea nivelului: DOAR proprietarul (permisiunea `autonomie.seteaza`), cu motiv, auditată și în istoric.
- Retrogradarea automată: la un incident critic, cu un nivel mai jos (podeaua L0), pe o clasă sau pe
  toate; scrisă în istoric ca „retrogradare”, cu audit de sistem și anunț.
- NU se construiește aici promovarea automată L1 → L2 (30 de livrabile, acordul clientului în portal):
  istoricul păstrează ce e nevoie pentru ea.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.conturi import PermisiuneRefuzata
from app.conturi.roluri import Permisiune, Rol, poate
from app.ids import new_id
from app.operare import audit, evenimente
from app.operare.notificari import Nivel as NivelAnunt
from app.productie import reguli_autonomie as reguli
from app.productie.anunturi import anunta
from app.productie.modele import Livrabil, NivelAutonomie, SchimbareAutonomie
from app.productie.reguli_autonomie import NIVEL_IMPLICIT, Clasa, Decizie, Nivel

MOTIV_MINIM = 3
MOTIV_MAXIM = 300


class MotivLipsa(ValueError):
    """Schimbarea de nivel cere un motiv (cel puțin 3 caractere)."""


@dataclass(frozen=True)
class Schimbare:
    clasa: Clasa
    de_la: Nivel
    la: Nivel


def canale_consimtamant() -> frozenset[str]:
    """Canalele marcate cu consimțământ per postare: rămân la L1 (7.4). Configurare, nu cod."""
    brut = get_settings().canale_consimtamant
    return frozenset(c.strip().lower() for c in brut.split(",") if c.strip())


# --- citire --------------------------------------------------------------------------------------------


def nivel(db: Session, tenant_id: uuid.UUID, clasa: Clasa) -> Nivel:
    rand = db.get(NivelAutonomie, (tenant_id, clasa.value))
    return Nivel(rand.nivel) if rand is not None else NIVEL_IMPLICIT


def matrice(db: Session, tenant_id: uuid.UUID) -> dict[Clasa, Nivel]:
    """Nivelul pentru fiecare dintre cele cinci clase (cele nesetate sunt L1)."""
    setate = {
        r.clasa: Nivel(r.nivel)
        for r in db.execute(select(NivelAutonomie).where(NivelAutonomie.tenant_id == tenant_id)).scalars()
    }
    return {c: setate.get(c.value, NIVEL_IMPLICIT) for c in Clasa}


def istoric(db: Session, tenant_id: uuid.UUID, *, limita: int = 100) -> list[SchimbareAutonomie]:
    return list(
        db.execute(
            select(SchimbareAutonomie)
            .where(SchimbareAutonomie.tenant_id == tenant_id)
            .order_by(SchimbareAutonomie.creat_la.desc(), SchimbareAutonomie.id.desc())
            .limit(limita)
        ).scalars()
    )


def decide(db: Session, livrabil: Livrabil, *, verificari_ok: bool = True, in_limite: bool = True) -> Decizie:
    """Cere platforma aprobarea unui om pentru acest livrabil? (umbră / aprobare / automat)

    `verificari_ok`: un livrabil `validat` a trecut verificările, deci implicit adevărat. `in_limite`:
    plafonul din contract / perimetrul (cheltuiala, strategia); îl calculează cel care știe plafonul (F13)."""
    s = get_settings()
    clasa = Clasa(livrabil.clasa_actiune)
    return reguli.cere_aprobare(
        nivel(db, livrabil.tenant_id, clasa),
        clasa,
        livrabil.id,
        canal=livrabil.canal,
        canale_consimtamant=canale_consimtamant(),
        rata_l2=s.autonomie_esantion_l2,
        rata_l3=s.autonomie_esantion_l3,
        verificari_ok=verificari_ok,
        in_limite=in_limite,
    )


# --- schimbare (doar proprietarul) --------------------------------------------------------------------------


def seteaza_nivel(
    db: Session,
    tenant_id: uuid.UUID,
    clasa: Clasa,
    nou: Nivel,
    *,
    utilizator_id: uuid.UUID,
    rol: Rol | str,
    motiv: str,
) -> bool:
    """Setează nivelul clientului pentru o clasă. Doar proprietarul; cu motiv; auditat. Întoarce dacă s-a
    schimbat.

    Nu cere (încă) acordul clientului pentru urcarea peste L1 (19.4: portalul clientului, F7)."""
    if not poate(rol, Permisiune.AUTONOMIE_SETEAZA):
        raise PermisiuneRefuzata("nivelul de autonomie îl schimbă doar proprietarul")
    motiv = motiv.strip()
    if not MOTIV_MINIM <= len(motiv) <= MOTIV_MAXIM:
        raise MotivLipsa("schimbarea nivelului cere un motiv (3–300 de caractere)")
    schimbare = _scrie(db, tenant_id, clasa, nou, tip="setare", utilizator_id=utilizator_id, motiv=motiv)
    if schimbare is None:
        return False
    audit.record(
        db,
        "autonomie.seteaza",
        obiect_tip="autonomie",
        obiect_id=f"{tenant_id}:{clasa.value}",
        utilizator_id=utilizator_id,
        tenant_id=tenant_id,
        detalii={
            "clasa": clasa.value,
            "de_la": int(schimbare.de_la),
            "la": int(schimbare.la),
            "motiv": motiv,
        },
    )
    return True


def retrogradeaza(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    motiv: str,
    clasa: Clasa | None = None,
    referinta: str = "",
) -> list[Schimbare]:
    """Incident critic: cu un nivel mai jos (7.4), pe `clasa` sau pe toate clasele clientului. Podeaua e L0.
    Automat (fără om): istoricul spune „retrogradare”, auditul „sistem”; proprietarul e anunțat."""
    motiv = motiv.strip()[:MOTIV_MAXIM] or "incident critic"
    schimbate: list[Schimbare] = []
    for c in [clasa] if clasa is not None else list(Clasa):
        curent = nivel(db, tenant_id, c)
        jos = reguli.retrogradat(curent)
        if jos == curent:
            continue
        s = _scrie(
            db, tenant_id, c, jos, tip="retrogradare", utilizator_id=None, motiv=motiv, referinta=referinta
        )
        if s is not None:
            schimbate.append(s)
            audit.record(
                db,
                "autonomie.retrogradata",
                obiect_tip="autonomie",
                obiect_id=f"{tenant_id}:{c.value}",
                tenant_id=tenant_id,
                actor_tip="sistem",
                detalii={"clasa": c.value, "de_la": int(s.de_la), "la": int(s.la), "motiv": motiv},
            )
    if schimbate:
        anunta(
            db,
            NivelAnunt.IMPORTANT,
            "Autonomia a fost redusă",
            f"Un incident critic a coborât cu un nivel autonomia la {len(schimbate)} clasă(e) de acțiuni.",
            url="/",
        )
    return schimbate


def _scrie(
    db: Session,
    tenant_id: uuid.UUID,
    clasa: Clasa,
    nou: Nivel,
    *,
    tip: str,
    utilizator_id: uuid.UUID | None,
    motiv: str,
    referinta: str = "",
) -> Schimbare | None:
    existent = db.execute(
        select(NivelAutonomie)
        .where(NivelAutonomie.tenant_id == tenant_id, NivelAutonomie.clasa == clasa.value)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    vechi = Nivel(existent.nivel) if existent is not None else NIVEL_IMPLICIT
    if vechi == nou:
        return None
    db.execute(
        pg_insert(NivelAutonomie)
        .values(
            tenant_id=tenant_id,
            clasa=clasa.value,
            nivel=int(nou),
            motiv=motiv,
            schimbat_de=utilizator_id,
        )
        .on_conflict_do_update(
            index_elements=["tenant_id", "clasa"],
            set_={"nivel": int(nou), "motiv": motiv, "schimbat_de": utilizator_id, "schimbat_la": func.now()},
        )
    )
    db.add(
        SchimbareAutonomie(
            id=new_id(),
            tenant_id=tenant_id,
            clasa=clasa.value,
            de_la=int(vechi),
            la=int(nou),
            tip=tip,
            utilizator_id=utilizator_id,
            motiv=motiv,
            referinta=referinta[:120],
        )
    )
    db.flush()
    evenimente.emite(
        db,
        f"autonomie.{'seteaza' if tip == 'setare' else 'retrogradata'}",
        sursa="productie",
        obiect_tip="autonomie",
        obiect_id=f"{tenant_id}:{clasa.value}",
        tenant_id=tenant_id,
        utilizator_id=utilizator_id,
        date={"clasa": clasa.value, "de_la": int(vechi), "la": int(nou)},
    )
    return Schimbare(clasa, vechi, nou)
