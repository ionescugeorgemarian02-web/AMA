"""Amânarea unui livrabil planificat (F3.11): câmpul `nu_inainte_de`, cu efect real prin `productie.muta`.

Planificatorul de capacitate (A4) amână livrabilele care nu încap în cotele zilei. „Amânat” nu e o
etichetă: un livrabil cu `nu_inainte_de` în viitor este REFUZAT de `muta` la trecerea din `planificat` în
`briefat` (refuzul se scrie în istoric, cod `amanat`); după acel moment trece normal. Amânarea nu ocolește
mașina de stări: nu schimbă starea și nu atinge `muta`, doar adaugă o condiție. Se amână doar un livrabil
`planificat`, doar mai târziu (nu mai devreme decât e deja) și doar până la termen.
"""

import datetime as dt
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.operare import audit, evenimente
from app.productie.modele import Livrabil
from app.productie.stari import Stare
from app.productie.tranzitii import EroareProductie, blocheaza


class AmanareNepermisa(EroareProductie):
    """Livrabilul nu poate fi amânat (nu e `planificat`, sau amânarea ar trece de termen)."""


def amana(
    db: Session,
    livrabil_id: uuid.UUID,
    pana_la: dt.datetime,
    *,
    motiv: str,
    componenta: str = "A4",
    utilizator_id: uuid.UUID | None = None,
) -> Livrabil:
    """Pune `nu_inainte_de = pana_la` (UTC). O amânare mai devreme decât cea existentă nu face nimic. Cu
    audit și eveniment."""
    if pana_la.tzinfo is None:
        raise ValueError("`pana_la` trebuie să aibă fus orar")
    livrabil = blocheaza(db, livrabil_id)
    if livrabil.stare != Stare.PLANIFICAT.value:
        raise AmanareNepermisa(f"doar un livrabil planificat se amână (acesta este „{livrabil.stare}”)")
    if livrabil.termen_la is not None and pana_la > livrabil.termen_la:
        raise AmanareNepermisa("amânarea ar trece de termenul livrabilului")
    if livrabil.nu_inainte_de is not None and pana_la <= livrabil.nu_inainte_de:
        return livrabil
    anterior = livrabil.nu_inainte_de
    livrabil.nu_inainte_de = pana_la
    livrabil.actualizat_la = func.now()
    db.flush()
    audit.record(
        db, "livrabil.amanat", obiect_tip="livrabil", obiect_id=str(livrabil.id),
        tenant_id=livrabil.tenant_id,
        utilizator_id=utilizator_id, actor_tip="utilizator" if utilizator_id else "sistem",
        detalii={
            "componenta": componenta, "pana_la": pana_la.isoformat(), "motiv": motiv[:200],
            "anterior": anterior.isoformat() if anterior else None,
        },
    )  # fmt: skip
    evenimente.emite(
        db, "livrabil.amanat", sursa="productie", obiect_tip="livrabil", obiect_id=livrabil.id,
        tenant_id=livrabil.tenant_id, date={"pana_la": pana_la.isoformat(), "componenta": componenta},
    )  # fmt: skip
    return livrabil


def elibereaza(
    db: Session, livrabil_id: uuid.UUID, *, motiv: str, utilizator_id: uuid.UUID | None = None
) -> Livrabil:
    """Scoate amânarea (un om reprogramează mai devreme). Cu audit."""
    livrabil = blocheaza(db, livrabil_id)
    if livrabil.nu_inainte_de is None:
        return livrabil
    livrabil.nu_inainte_de = None
    livrabil.actualizat_la = func.now()
    db.flush()
    audit.record(
        db, "livrabil.amanare_scoasa", obiect_tip="livrabil", obiect_id=str(livrabil.id),
        tenant_id=livrabil.tenant_id,
        utilizator_id=utilizator_id, detalii={"motiv": motiv[:200]},
    )  # fmt: skip
    return livrabil
