"""Analiza de trafic proprie (F10.6, docs/19 §19.1, docs/16 §16.7, docs/21 §21.8): câți vizitatori ajung pe
site și pe paginile de captare și câți cer audit.

Două surse, cu reguli diferite, care NU se amestecă pe tăcute:
- **vizitele** (`site_vizite`, F7.1): contoare pe zi și pagină, scrise DOAR pentru vizitatorii care au
  acceptat analiza; fără IP, fără identificatori. Sunt deci un minim, nu totalul vizitelor;
- **cererile de audit** (`leaduri`, F7.2): exacte, fiindcă fiecare cerere e un formular trimis cu
  consimțământ propriu.
De aceea rata „cereri la 100 de vizite” este o limită de sus (numitorul e subestimat) și e afișată cu
această mențiune. Fără vizite numărate nu se afișează nicio rată.
"""

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.site.modele import Lead, Vizita

PAGINA_AUDIT = "/audit"
STARI_CONFIRMATE = ("confirmat", "audit_gata", "client")


@dataclass(frozen=True)
class Palnie:
    de_la: dt.date
    pana_la: dt.date
    vizite: int  # toate paginile, doar vizitatorii cu acord
    vizite_audit: int  # pagina formularului de audit
    cereri: int  # formulare trimise (exact)
    confirmate: int  # adresa de email confirmată
    audituri_gata: int
    clienti: int
    pe_pagina: list[tuple[str, int]] = field(default_factory=list)  # cele mai vizitate pagini
    pe_sursa: dict[str, int] = field(default_factory=dict)  # cererile pe sursă (audit, pagină de captare…)

    @property
    def cereri_la_suta(self) -> float | None:
        """Cereri la 100 de vizite numărate ale paginii de audit; `None` fără vizite numărate."""
        return round(self.cereri * 100 / self.vizite_audit, 1) if self.vizite_audit else None


def palnie(db: Session, de_la: dt.date, pana_la: dt.date, *, pagini: int = 10) -> Palnie:
    """Pâlnia pe intervalul [de_la, pana_la] (zile UTC, ambele incluse). Date de agenție."""
    pe_pagina = [
        (str(c), int(n))
        for c, n in db.execute(
            select(Vizita.cale, func.sum(Vizita.numar))
            .where(Vizita.zi >= de_la, Vizita.zi <= pana_la)
            .group_by(Vizita.cale)
            .order_by(func.sum(Vizita.numar).desc(), Vizita.cale)
        ).all()
    ]
    inceput = dt.datetime(de_la.year, de_la.month, de_la.day, tzinfo=dt.UTC)
    sfarsit = dt.datetime(pana_la.year, pana_la.month, pana_la.day, tzinfo=dt.UTC) + dt.timedelta(days=1)
    leaduri = db.execute(
        select(Lead.stare, Lead.sursa).where(Lead.creat_la >= inceput, Lead.creat_la < sfarsit)
    ).all()
    pe_sursa: dict[str, int] = {}
    for _, sursa in leaduri:
        pe_sursa[str(sursa)] = pe_sursa.get(str(sursa), 0) + 1
    stari = [str(s) for s, _ in leaduri]
    return Palnie(
        de_la=de_la,
        pana_la=pana_la,
        vizite=sum(n for _, n in pe_pagina),
        vizite_audit=sum(n for c, n in pe_pagina if c == PAGINA_AUDIT),
        cereri=len(stari),
        confirmate=sum(1 for s in stari if s in STARI_CONFIRMATE),
        audituri_gata=sum(1 for s in stari if s in ("audit_gata", "client")),
        clienti=sum(1 for s in stari if s == "client"),
        pe_pagina=pe_pagina[:pagini],
        pe_sursa=dict(sorted(pe_sursa.items())),
    )
