"""Construiește, într-o tranzacție care se anulează, contextul unui profil: faptele aprobate, ofertele (cu
istoricul de
prețuri), ghidul de brand și sursele colectate ale unui client de probă. Folosește aceleași API-uri ca
aplicația
(registrul de fapte, catalogul de oferte, Creierul, cercetarea): nu scrie direct în tabele.

Toate momentele sunt relative la `la` (data validării din `contexte.toml`), nu la ceasul real.
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app import cercetare, creier
from app.creier import Compartiment, Sursa, SursaTip, fapte, oferte
from app.validare.banc.seturi import ProfilContext


def _acum(la: dt.datetime, zile: float) -> dt.datetime:
    return la - dt.timedelta(days=zile)


def _pret(numar: object, moneda: str = "RON") -> dict[str, Any]:
    return {"numar": str(numar), "moneda": moneda}


def _fapt(db: Session, tenant: uuid.UUID, om: uuid.UUID, la: dt.datetime, f: dict[str, Any]) -> None:
    continut: dict[str, Any] = {"tip": f["tip"], "subiect": f["subiect"], "afirmatie": f["afirmatie"]}
    if f.get("valoare"):
        continut["valoare"] = dict(f["valoare"])
    aprobat = _acum(la, float(f.get("aprobat_zile", 1)))
    de_la = _acum(la, float(f["de_la_zile"])) if "de_la_zile" in f else None
    pana_la = _acum(la, float(f["pana_la_zile"])) if "pana_la_zile" in f else None
    i, v, _ = fapte.propune_fapt(
        db,
        tenant_id=tenant,
        continut=continut,
        sursa=Sursa(SursaTip.DECLARATIE_CLIENT),
        utilizator_id=om,
        valabil_de_la=de_la,
        valabil_pana_la=pana_la,
        acum=aprobat,
    )
    if f.get("aprobat", True):
        fapte.aproba_fapt(db, i.id, v.nr, utilizator_id=om, acum=aprobat)


def _oferta(db: Session, tenant: uuid.UUID, om: uuid.UUID, la: dt.datetime, o: dict[str, Any]) -> None:
    """Treptele de preț ale `istoric` ([preț, acum câte zile a intrat în vigoare], cele mai vechi primele)
    sunt versiuni
    aprobate; ultima versiune este `pret` (+ `pret_referinta`), în vigoare de `aprobat_zile` zile (implicit
    1)."""
    baza: dict[str, Any] = {"tip": o.get("tip", "produs"), "nume": o["nume"]}
    for c in ("descriere", "conditii", "garantie"):
        if o.get(c):
            baza[c] = o[c]
    treptele = [(str(p), float(z)) for p, z in o.get("istoric", [])]
    treptele.append((str(o["pret"]), float(o.get("aprobat_zile", 1))))
    iid: uuid.UUID | None = None
    for k, (pret, zile) in enumerate(treptele):
        ultima = k == len(treptele) - 1
        # o promoție cere preț de referință: treptele vechi (fără referință) sunt „produs”, ultima
        # are tipul declarat
        continut = {**baza, "pret": _pret(pret), "tip": baza["tip"] if ultima else "produs"}
        if ultima and o.get("pret_referinta"):
            continut["pret_referinta"] = _pret(o["pret_referinta"])
        acum = _acum(la, zile)
        if iid is None:
            intrare, v, _ = oferte.propune_oferta(
                db,
                tenant_id=tenant,
                continut=continut,
                sursa=Sursa(SursaTip.DECLARATIE_CLIENT),
                utilizator_id=om,
                acum=acum,
            )
            iid = intrare.id
        else:
            v = oferte.modifica_oferta(
                db,
                iid,
                continut=continut,
                sursa=Sursa(SursaTip.DECLARATIE_CLIENT),
                utilizator_id=om,
                acum=acum,
            )
        oferte.aproba_oferta(db, iid, v.nr, utilizator_id=om, acum=acum)


def _ghid(db: Session, tenant: uuid.UUID, om: uuid.UUID, la: dt.datetime, ghid: dict[str, Any]) -> None:
    i, v = creier.creeaza_intrare(
        db,
        tenant_id=tenant,
        compartiment=Compartiment.PROFIL_BRAND,
        cheie="ghid",
        continut=dict(ghid),
        sursa=Sursa(SursaTip.OM),
        utilizator_id=om,
        acum=_acum(la, 1),
    )
    creier.aproba(db, i.id, v.nr, utilizator_id=om, acum=_acum(la, 1))


def _surse(db: Session, tenant: uuid.UUID, surse: tuple[dict[str, Any], ...]) -> None:
    for s in surse:
        sid = cercetare.creeaza_sursa(
            db,
            tenant_id=tenant,
            tip="manual",
            statut_cod=s.get("statut", "material_client"),
            nume=s.get("nume", "Sursă de probă"),
        ).id
        for k, t in enumerate(s["texte"]):
            cercetare.adauga_text(db, tenant_id=tenant, sursa_id=sid, titlu=f"Document {k}", text=t)
        creier.pregateste_sursa(db, sid)
    db.flush()


def construieste(
    db: Session, tenant: uuid.UUID, om: uuid.UUID, la: dt.datetime, profil: ProfilContext
) -> None:
    """Contextul profilului pentru clientul de probă `tenant`; `om` este utilizatorul de probă (autorul
    aprobărilor)."""
    if profil.ghid:
        _ghid(db, tenant, om, la, profil.ghid)
    for f in profil.fapte:
        _fapt(db, tenant, om, la, f)
    for o in profil.oferte:
        _oferta(db, tenant, om, la, o)
    _surse(db, tenant, profil.surse)
