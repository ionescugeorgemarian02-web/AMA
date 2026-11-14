"""Licențele activelor (F8.4, docs/14 §14.3, G7): niciun activ nu se folosește fără licență înregistrată.

Fiecare sursă are câmpurile ei obligatorii (`CAMPURI`). Licența se scrie în `active.licenta` doar dacă e
completă;
orice folosire trece prin `foloseste`, care o verifică și o consemnează în `folosiri_active`. Baza refuză
și ea
(declanșator) o folosire a unui activ fără licență, oricine ar scrie rândul.
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.media.modele import Activ, FolosireActiv
from app.operare import audit

STATUT_OK = "verificata"
CAMPURI: dict[str, tuple[str, ...]] = {
    "material_client": ("declarat_de", "conditii"),
    "stock": ("furnizor", "identificator", "autor", "url", "copie", "descarcat_la"),
    "generat": ("furnizor", "model", "prompt", "samanta", "conditii"),
    "voce_sintetizata": ("profil", "motor", "model"),
    "muzica": ("furnizor", "identificator", "autor", "copie"),
    "productie_proprie": ("componente",),
}


class FaraLicenta(PermissionError):
    """Activul nu are licență înregistrată (sau licența lui nu permite folosirea)."""


def probleme(licenta: dict[str, Any] | None) -> list[str]:
    """Nucleu pur: ce lipsește dintr-o licență ca să fie folosibilă."""
    if not licenta:
        return ["fără licență înregistrată"]
    tip = licenta.get("tip")
    if tip not in CAMPURI:
        return [f"tip de licență necunoscut: {tip!r}"]
    out = [f"lipsește `{c}`" for c in CAMPURI[tip] if licenta.get(c) in (None, "", [], {})]
    statut = licenta.get("statut")
    if statut != STATUT_OK:
        out.append(f"statutul licenței este {statut!r}, nu {STATUT_OK!r}")
    return out


def cere(activ: Activ) -> dict[str, Any]:
    p = probleme(activ.licenta)
    if p:
        raise FaraLicenta(f"activul {activ.id} nu poate fi folosit: " + "; ".join(p))
    return activ.licenta or {}


def inregistreaza(
    db: Session, activ: Activ, licenta: dict[str, Any], *, utilizator_id: uuid.UUID | None = None
) -> Activ:
    """Scrie licența pe activ, doar completă (altfel `FaraLicenta`)."""
    lic = {"statut": STATUT_OK, **licenta}
    p = probleme(lic)
    if p:
        raise FaraLicenta("licență incompletă: " + "; ".join(p))
    activ.licenta = lic
    db.flush()
    audit.record(
        db,
        "activ.licenta",
        obiect_tip="activ",
        obiect_id=activ.id,
        tenant_id=activ.tenant_id,
        utilizator_id=utilizator_id,
        detalii={"tip": lic["tip"], "statut": lic["statut"]},
    )
    return activ


def foloseste(db: Session, activ_id: uuid.UUID, *, scop: str, obiect_id: uuid.UUID | None = None) -> Activ:
    """Singura cale de folosire a unui activ într-o producție: verifică licența și consemnează folosirea."""
    a = db.get(Activ, activ_id)
    if a is None:
        raise FaraLicenta(f"activ inexistent: {activ_id}")
    cere(a)
    db.add(FolosireActiv(tenant_id=a.tenant_id, activ_id=a.id, scop=scop, obiect_id=obiect_id))
    db.flush()
    return a


def folosiri(db: Session, activ_id: uuid.UUID) -> list[FolosireActiv]:
    return list(db.execute(select(FolosireActiv).where(FolosireActiv.activ_id == activ_id)).scalars())


def licenta_material_client(utilizator_id: uuid.UUID | None) -> dict[str, Any]:
    return {
        "tip": "material_client",
        "statut": STATUT_OK,
        "declarat_de": str(utilizator_id) if utilizator_id else "client",
        "conditii": "termenii portalului: clientul garantează drepturile asupra materialelor încărcate",
        "inregistrat_la": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
    }
