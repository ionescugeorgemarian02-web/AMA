"""Butoanele de oprire (docs 7.8): steaguri de sistem, citite de modulele care fac efecte.

Cine le citește: producția nouă de livrabile (`Oprire.PRODUCTIE` și oprirea pe client, F2.4: `productie.muta`
refuză pornirea unui livrabil nou) și publicarea (F2.5: executorul de efecte verifică oprirea chiar
înainte de trimitere; maparea clasă de efect → oprire e în `operare.efecte.stari.OPRIRE_PE_TIP`).
Reclamele (F13) și învățarea (F12) vor apela `este_oprit` înaintea oricărui efect.
Implicit nimic nu este oprit.

    from app.operare import opriri
    if opriri.este_oprit(db, opriri.Oprire.PUBLICARE, tenant_id=client_id):
        ...  # nu publica
"""

import uuid
from enum import StrEnum
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.operare import audit
from app.operare.tabele import StareOprire


class Oprire(StrEnum):
    PUBLICARE = "publicare"  # oprirea globală a publicării
    PRODUCTIE = (
        "productie"  # oprirea producției NOI (întrerupătorul din 7.3 o pune singur; repornirea: doar om)
    )
    RECLAME = "reclame"  # oprirea tuturor reclamelor
    INVATARE = "invatare"  # înghețarea învățării: nicio promovare nouă
    APELURI_PLATITE = "apeluri_platite"
    CLIENT = "client"  # oprirea pe un client (oprește orice efect pentru el)


GLOBALE = (Oprire.PUBLICARE, Oprire.PRODUCTIE, Oprire.RECLAME, Oprire.INVATARE, Oprire.APELURI_PLATITE)
ETICHETE: dict[Oprire, str] = {
    Oprire.PUBLICARE: "Publicarea (global)",
    Oprire.PRODUCTIE: "Producția nouă (global)",
    Oprire.RECLAME: "Toate reclamele",
    Oprire.INVATARE: "Învățarea (înghețată)",
    Oprire.APELURI_PLATITE: "Apelurile plătite",
    Oprire.CLIENT: "Un client",
}
Canal = Literal["panou", "telegram", "sistem"]  # „sistem”: doar întrerupătorul global (7.3)
MOTIV_MAXIM = 300


def _rand(db: Session, tip: Oprire, tenant_id: uuid.UUID | None) -> StareOprire | None:
    q = select(StareOprire).where(StareOprire.tip == tip.value)
    q = q.where(StareOprire.tenant_id.is_(None) if tenant_id is None else StareOprire.tenant_id == tenant_id)
    return db.execute(q).scalar_one_or_none()


def citeste(db: Session, tip: Oprire, *, tenant_id: uuid.UUID | None = None) -> StareOprire | None:
    """Rândul de stare al unei opriri (cu motivul, canalul și momentul ultimei schimbări), sau `None`."""
    return _rand(db, tip, tenant_id)


def este_oprit(db: Session, tip: Oprire, *, tenant_id: uuid.UUID | None = None) -> bool:
    """Adevărat dacă efectul de tipul `tip` nu are voie să ruleze. Oprirea unui client le oprește pe toate
    pentru el. Fără rând = nu este oprit."""
    if tip is Oprire.CLIENT:
        if tenant_id is None:
            raise ValueError("Oprire.CLIENT cere tenant_id")
        rand = _rand(db, tip, tenant_id)
        return bool(rand and rand.activ)
    glob = _rand(db, tip, None)
    if glob and glob.activ:
        return True
    if tenant_id is not None:
        client = _rand(db, Oprire.CLIENT, tenant_id)
        return bool(client and client.activ)
    return False


def seteaza(
    db: Session,
    tip: Oprire,
    activ: bool,
    *,
    canal: Canal,
    motiv: str = "",
    tenant_id: uuid.UUID | None = None,
    utilizator_id: uuid.UUID | None = None,
) -> bool:
    """Oprește sau repornește, cu audit (cine, când, de ce, canal). Întoarce dacă starea s-a schimbat."""
    if (tip is Oprire.CLIENT) != (tenant_id is not None):
        raise ValueError("tenant_id se dă exact pentru Oprire.CLIENT")
    motiv = motiv.strip()[:MOTIV_MAXIM]
    rand = _rand(db, tip, tenant_id)
    schimbat = (rand.activ if rand else False) != activ
    if rand is None:
        db.add(
            StareOprire(
                tip=tip.value,
                tenant_id=tenant_id,
                activ=activ,
                motiv=motiv,
                canal=canal,
                schimbat_de=utilizator_id,
            )
        )
    elif schimbat:
        rand.activ, rand.motiv, rand.canal, rand.schimbat_de = activ, motiv, canal, utilizator_id
        rand.schimbat_la = func.now()
    db.flush()
    audit.record(
        db,
        "oprire.oprit" if activ else "oprire.repornit",
        obiect_tip="oprire",
        obiect_id=tip.value,
        utilizator_id=utilizator_id,
        tenant_id=tenant_id,
        actor_tip=None if utilizator_id else "sistem",
        detalii={"tip": tip.value, "canal": canal, "motiv": motiv, "schimbat": schimbat},
    )
    return schimbat


def active(db: Session) -> list[StareOprire]:
    """Toate opririle active (globale și pe client), cele mai noi primele."""
    return list(
        db.execute(
            select(StareOprire).where(StareOprire.activ.is_(True)).order_by(StareOprire.schimbat_la.desc())
        ).scalars()
    )
