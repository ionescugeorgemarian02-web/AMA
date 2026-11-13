"""Citirea pentru context a compartimentelor fără modul propriu (F4.7): profilul de brand și constrângerile.

La fel ca `fapte.pentru_context`: doar versiunile APROBATE de un om, aprobate până la `la`, neretrase la
`la` și cu `la` în valabilitate. Constructorul de context (`context.py`) nu citește depozitul versionat
altfel decât prin aceste funcții.

Faptele și ofertele NU se citesc pe aici (au propriile `pentru_context`, cu regulile lor, de ex. oferta cere
faptele legate valabile): cererea lor este refuzată, ca să nu existe o a doua cale, mai slabă, spre
registrul de fapte. Constrângerile pot veni și de pe nivelul platformei (reguli ale produsului, fără
client), citite la fel; nivelul de nișă nu se citește aici (clientul nu are încă o nișă asociată: propunere
în JURNAL).
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.creier.compartimente import Compartiment, randare
from app.creier.modele import IntrareCreier, VersiuneCreier
from app.creier.versiuni import RegulaCreier

REFUZATE = frozenset({Compartiment.REGISTRU_FAPTE, Compartiment.CATALOG_OFERTE})


@dataclass(frozen=True)
class IntrareContext:
    intrare_id: uuid.UUID
    versiune: int
    nivel: str
    cheie: str
    continut: dict[str, Any]
    text: str
    sursa_tip: str
    aprobat_la: dt.datetime | None


def _valoare(v: Any) -> str:
    if isinstance(v, list | tuple):
        return ", ".join(x for x in (_valoare(i) for i in v) if x)
    if isinstance(v, dict):
        return "; ".join(f"{k.replace('_', ' ')}: {_valoare(v[k])}" for k in sorted(v) if _valoare(v[k]))
    if v is None or isinstance(v, bool):
        return ""
    return str(v).strip()


def text_intrare(continut: dict[str, Any]) -> str:
    """Conținutul ca text pentru prompt, determinist (chei sortate). O singură valoare text se dă fără
    etichetă; altfel fiecare câmp apare ca „nume: valoare”."""
    campuri = [(k, _valoare(continut[k])) for k in sorted(continut)]
    campuri = [(k, v) for k, v in campuri if v]
    if len(campuri) == 1:
        return campuri[0][1]
    return "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in campuri)


def _text(compartiment: Compartiment, continut: dict[str, Any]) -> str:
    randeaza = randare(compartiment)
    randat = randeaza(continut) if randeaza else None
    return randat if randat is not None else text_intrare(continut)


def pentru_context(
    db: Session,
    tenant_id: uuid.UUID,
    compartiment: Compartiment,
    la: dt.datetime,
    *,
    cu_platforma: bool = False,
) -> list[IntrareContext]:
    """Versiunile aprobate și valabile la `la` ale compartimentului, ale clientului (și, cu
    `cu_platforma`, ale nivelului platformei, doar pentru constrângeri)."""
    if la.tzinfo is None:
        raise RegulaCreier("data cerută trebuie să aibă fus orar (UTC)")
    if compartiment in REFUZATE:
        raise RegulaCreier(
            f"{compartiment.value} se citește doar prin fapte.pentru_context / oferte.pentru_context"
        )
    if cu_platforma and compartiment is not Compartiment.CONSTRANGERI:
        raise RegulaCreier("nivelul platformei se citește doar pentru constrângeri")
    proprietar = IntrareCreier.tenant_id == tenant_id
    if cu_platforma:
        proprietar = proprietar | ((IntrareCreier.tenant_id.is_(None)) & (IntrareCreier.nivel == "platforma"))
    q = (
        select(IntrareCreier, VersiuneCreier)
        .join(VersiuneCreier, VersiuneCreier.intrare_id == IntrareCreier.id)
        .where(
            proprietar,
            IntrareCreier.compartiment == compartiment.value,
            VersiuneCreier.aprobat_la.is_not(None),
            VersiuneCreier.aprobat_la <= la,
            VersiuneCreier.retras_la.is_(None) | (VersiuneCreier.retras_la > la),
            VersiuneCreier.valabil_de_la.is_(None) | (VersiuneCreier.valabil_de_la <= la),
            VersiuneCreier.valabil_pana_la.is_(None) | (VersiuneCreier.valabil_pana_la > la),
        )
        .order_by(IntrareCreier.nivel, IntrareCreier.cheie, IntrareCreier.id, VersiuneCreier.nr)
    )
    return [
        IntrareContext(
            i.id,
            v.nr,
            i.nivel,
            i.cheie,
            v.continut,
            _text(compartiment, v.continut),
            v.sursa_tip,
            v.aprobat_la,
        )
        for i, v in db.execute(q).all()
    ]
