"""Proba de două săptămâni, accelerată (F6.8, docs/23 §23.9, docs/25 §25.4 poarta de lansare 1: „14 zile de
producție pentru
brandurile proprii fără incident critic”; rata de aprobare din prima, măsurată).

# SIMULAT: proba pe conținut real (14 zile calendaristice, CariereAI și BigBrain, modele reale, un om care
# aprobă și publică
de pe telefon) cere resurse externe și se face la migrare (D-007). Aici rulează ACELAȘI lanț de producție, zi
cu zi, pe
ceasul calendarului (nu se așteaptă zilele): pentru fiecare zi și brand, sloturile zilei trec prin brief →
scriere →
validare → aprobare la L1; decizia omului și publicarea din telefon sunt funcții date de apelant (simulate în
test).

Incident critic [I] (oricare oprește proba):
- o postare publicată pe o versiune care nu a trecut validarea sau pe care nu a aprobat-o un om;
- două publicări ale aceleiași versiuni (cheia de idempotență);
- un livrabil publicat fără pachet asistat (publicare pe lângă H1);
- o eroare neprinsă în lanț.
Livrabilele ajunse în carantină sau în coada de erori NU sunt incidente critice (sunt oprite înainte de
public, cum cere
designul), dar se numără.

Rata de aprobare din prima = livrabile aprobate la PRIMA cerere de aprobare, fără editare / respingere ÷
livrabile decise.
"""

import datetime as dt
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app import productie, publicare, validare
from app.continut import calendar, pipeline
from app.db import sesiune_tenant
from app.operare import audit
from app.productie import Stare

ZILE = 14


@dataclass(frozen=True)
class Decizie:
    """Ce hotărăște omul (simulat): `aproba`, `respinge` (cu motiv standard și frază) sau `editeaza` (text
    nou, apoi aprobă)."""

    fel: str
    motiv_standard: str | None = None
    motiv: str = ""
    text: str = ""


Decident = Callable[[Session, productie.Aprobare, productie.Livrabil, int], Decizie]
Publicator = Callable[[publicare.PublicareAsistata, int], str]  # întoarce linkul postării


@dataclass
class Raport:
    zile: int = 0
    produse: int = 0
    decise: int = 0
    aprobate_din_prima: int = 0
    respinse: int = 0
    editate: int = 0
    publicate: int = 0
    oprite: dict[str, int] = field(default_factory=dict)  # stare finală nepublicabilă → număr
    incidente_critice: list[str] = field(default_factory=list)
    pe_zi: list[dict[str, Any]] = field(default_factory=list)

    @property
    def rata_aprobare_din_prima(self) -> float | None:
        return round(self.aprobate_din_prima / self.decise, 4) if self.decise else None

    def json(self) -> dict[str, Any]:
        return {
            "zile": self.zile,
            "produse": self.produse,
            "decise": self.decise,
            "aprobate_din_prima": self.aprobate_din_prima,
            "respinse": self.respinse,
            "editate": self.editate,
            "publicate": self.publicate,
            "oprite": self.oprite,
            "incidente_critice": self.incidente_critice,
            "rata_aprobare_din_prima": self.rata_aprobare_din_prima,
        }


def sloturi_zilei(db: Session, calendar_id: uuid.UUID, zi: dt.date) -> list[uuid.UUID]:
    return [
        i.livrabil_id
        for i in calendar.intrari(db, calendar_id)
        if i.livrabil_id is not None and i.slot_la.astimezone(calendar.FUS).date() == zi
    ]


def verifica_publicarea(db: Session, lid: uuid.UUID) -> list[str]:
    """Incidentele critice ale unui livrabil publicat (listă goală = curat). Nucleul verificării probei."""
    lv = productie.citeste(db, lid)
    if lv is None or lv.stare != Stare.PUBLICAT.value:
        return []
    probleme = []
    pachete = publicare.asistata.ale_livrabilului(db, lid)
    publicate = [p for p in pachete if p.stare == "publicat"]
    if not publicate:
        probleme.append(f"{lid}: publicat fără pachet asistat")
    if len({p.versiune for p in publicate}) != len(publicate):
        probleme.append(f"{lid}: aceeași versiune publicată de două ori")
    for p in publicate:
        rulari = [r for r in validare.rulari(db, lid) if r.versiune == p.versiune]
        if not rulari or rulari[-1].decizie != "trece":
            probleme.append(f"{lid}: versiunea {p.versiune} publicată fără validare trecută")
        aprobari = [
            a
            for a in productie.aprobari.ale_livrabilului(db, lid)
            if a.versiune == p.versiune and a.stare == "aprobat"
        ]
        if not aprobari or aprobari[-1].decis_de is None:
            probleme.append(f"{lid}: versiunea {p.versiune} publicată fără aprobarea unui om")
    return probleme


def _decide(tenant: uuid.UUID, om: uuid.UUID, lid: uuid.UUID, decident: Decident, n: int, r: Raport) -> None:
    """Decizia omului pe cererea activă; editarea trimite din nou în validare, apoi omul aprobă."""
    from app.validare import birou

    with sesiune_tenant(tenant, om) as db:
        ap = productie.aprobari.cerere_activa(db, lid)
        lv = productie.citeste(db, lid)
        if ap is None or lv is None:
            return
        d = decident(db, ap, lv, n)
        r.decise += 1
        if d.fel == "respinge":
            r.respinse += 1
            productie.aprobari.decide(
                db,
                ap.id,
                productie.Hotarare.RESPINS,
                utilizator_id=om,
                rol="proprietar",
                motiv_standard=d.motiv_standard,
                motiv=d.motiv,
            )
            return
        if d.fel == "aproba":
            r.aprobate_din_prima += 1
            productie.aprobari.decide(
                db, ap.id, productie.Hotarare.APROBAT, utilizator_id=om, rol="proprietar"
            )
            return
        r.editate += 1
        birou.editeaza(db, ap.id, versiune=ap.versiune, text=d.text, utilizator_id=om)
    if pipeline.produ(tenant, lid) == Stare.ASTEAPTA_APROBARE.value:
        with sesiune_tenant(tenant, om) as db:
            ap = productie.aprobari.cerere_activa(db, lid)
            if ap is not None:
                productie.aprobari.decide(
                    db, ap.id, productie.Hotarare.APROBAT, utilizator_id=om, rol="proprietar"
                )


def ruleaza(
    branduri: list[tuple[uuid.UUID, uuid.UUID]],
    *,
    om: uuid.UUID,
    inceput: dt.date,
    decident: Decident,
    publicator: Publicator,
    zile: int = ZILE,
) -> Raport:
    """Proba: `branduri` = (client, calendar aprobat). Zi cu zi, brand cu brand: producție, decizie,
    publicare, verificare."""
    r = Raport()
    n = 0
    for k in range(zile):
        zi = inceput + dt.timedelta(days=k)
        linie: dict[str, Any] = {"zi": zi.isoformat(), "produse": 0, "publicate": 0}
        for tenant, cal in branduri:
            with sesiune_tenant(tenant) as db:
                lids = sloturi_zilei(db, cal, zi)
            for lid in lids:
                n += 1
                try:
                    stare = pipeline.produ(tenant, lid)
                    r.produse += 1
                    linie["produse"] += 1
                    if stare == Stare.ASTEAPTA_APROBARE.value:
                        _decide(tenant, om, lid, decident, n, r)
                    with sesiune_tenant(tenant, om) as db:
                        lv = productie.citeste(db, lid)
                        p = next(
                            (
                                x
                                for x in publicare.asistata.ale_livrabilului(db, lid)
                                if x.stare == "pregatit"
                            ),
                            None,
                        )
                        if p is not None:
                            publicare.asistata.confirma(db, p.id, link=publicator(p, n), utilizator_id=om)
                            r.publicate += 1
                            linie["publicate"] += 1
                        elif lv is not None and lv.stare != Stare.PUBLICAT.value:
                            r.oprite[lv.stare] = r.oprite.get(lv.stare, 0) + 1
                        r.incidente_critice += verifica_publicarea(db, lid)
                except Exception as exc:  # orice eroare neprinsă e incident critic, nu oprește raportul
                    r.incidente_critice.append(
                        f"{lid}: eroare neprinsă {type(exc).__name__}: {str(exc)[:200]}"
                    )
        r.pe_zi.append(linie)
        r.zile += 1
    for tenant, _ in branduri:
        with sesiune_tenant(tenant, om) as db:
            audit.record(
                db,
                "continut.proba",
                obiect_tip="client",
                obiect_id=tenant,
                utilizator_id=om,
                tenant_id=tenant,
                detalii={k: v for k, v in r.json().items() if k != "incidente_critice"}
                | {"incidente_critice": len(r.incidente_critice)},
            )
    return r
