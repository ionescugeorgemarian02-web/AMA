"""Raportul dublu și verificarea plafoanelor (F13.10, docs/16 §16.7, §16.10).

Raportul are două coloane pe fiecare zi: ce spune platforma de reclame (cheltuială, clicuri, rezultate) și
ce a
măsurat site-ul (vizitele numărate pe pagina de audit, cererile de audit). Diferența se explică, nu se
ascunde:
vizitele se numără doar cu acordul vizitatorului, iar cererile vin din toate sursele, nu doar din reclame.

`depasiri` caută orice depășire de plafon: zi peste plafonul zilnic, lună peste plafonul lunar, campanie peste
plafonul ei, și orice schimbare aplicată fără verdictul favorabil al gardianului.
"""

import datetime as dt
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analiza import trafic
from app.reclame import rezultate
from app.reclame.modele import Campanie, ContReclame, Propunere
from app.reclame.rezultate import Totaluri


@dataclass(frozen=True)
class ZiRaport:
    zi: dt.date
    platforma: Totaluri
    vizite_audit: int
    cereri_audit: int


@dataclass
class RaportDublu:
    de_la: dt.date
    pana_la: dt.date
    zile: list[ZiRaport] = field(default_factory=list)

    @property
    def platforma(self) -> Totaluri:
        t = [z.platforma for z in self.zile]
        return Totaluri(
            sum(x.cheltuiala_bani for x in t),
            sum(x.afisari for x in t),
            sum(x.clicuri for x in t),
            sum(x.rezultate for x in t),
        )

    @property
    def vizite_audit(self) -> int:
        return sum(z.vizite_audit for z in self.zile)

    @property
    def cereri_audit(self) -> int:
        return sum(z.cereri_audit for z in self.zile)

    @property
    def explicatii(self) -> list[str]:
        p, out = self.platforma, []
        if p.clicuri != self.vizite_audit:
            out.append(
                f"Platforma numără {p.clicuri} clicuri, site-ul {self.vizite_audit} vizite pe pagina de "
                "audit: "
                "site-ul numără doar vizitatorii care au acceptat analiza, iar o parte din clicuri nu ajung "
                "până la încărcarea paginii."
            )
        if p.rezultate != self.cereri_audit:
            out.append(
                f"Platforma raportează {p.rezultate} rezultate, site-ul {self.cereri_audit} cereri de audit: "
                "cererile vin din toate sursele (nu doar din reclame), iar platforma atribuie conversii după "
                "modelul ei (inclusiv după vizualizare)."
            )
        return out


def raport_dublu(db: Session, cont_id: uuid.UUID, de_la: dt.date, pana_la: dt.date) -> RaportDublu:
    r = RaportDublu(de_la, pana_la)
    zi = de_la
    while zi <= pana_la:
        p = trafic.palnie(db, zi, zi, pagini=0)
        r.zile.append(ZiRaport(zi, rezultate.totaluri(db, cont_id, zi, zi), p.vizite_audit, p.cereri))
        zi += dt.timedelta(days=1)
    return r


def depasiri(db: Session, cont_id: uuid.UUID, de_la: dt.date, pana_la: dt.date) -> list[str]:
    """Orice depășire de plafon sau schimbare aplicată fără verdict favorabil. Goală = totul în plafoane."""
    cont = db.get(ContReclame, cont_id)
    if cont is None:
        return ["cont inexistent"]
    out: list[str] = []
    luni: dict[dt.date, int] = {}
    for zi, t in rezultate.pe_zile(db, cont_id, de_la, pana_la):
        if t.cheltuiala_bani > cont.plafon_zilnic_bani:
            out.append(f"{zi}: cheltuiala zilei peste plafonul zilnic")
        luni[zi.replace(day=1)] = luni.get(zi.replace(day=1), 0) + t.cheltuiala_bani
    out += [
        f"{luna:%Y-%m}: cheltuiala lunii peste plafonul lunar"
        for luna, s in luni.items()
        if s > cont.plafon_lunar_bani
    ]
    campanii = {
        c.id_extern: c.nume for c in db.execute(select(Campanie).where(Campanie.cont_id == cont_id)).scalars()
    }
    for ext, nume in campanii.items():
        if ext is None:
            continue
        for zi, _ in rezultate.pe_zile(db, cont_id, de_la, pana_la):
            if (
                rezultate.totaluri(db, cont_id, zi, zi, obiect_extern=ext).cheltuiala_bani
                > cont.plafon_campanie_bani
            ):
                out.append(f"{zi}: „{nume}” peste plafonul pe campanie")
    for p in db.execute(
        select(Propunere).where(Propunere.cont_id == cont_id, Propunere.stare == "aplicata")
    ).scalars():
        if not p.verdict.get("permis"):
            out.append(f"schimbarea {p.id} a fost aplicată fără verdictul gardianului")
        buget = p.dupa.get("buget_zilnic_bani")
        if buget is not None and int(buget) > cont.plafon_campanie_bani:
            out.append(f"schimbarea {p.id} a pus un buget peste plafonul pe campanie")
    return out
