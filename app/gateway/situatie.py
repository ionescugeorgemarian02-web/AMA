"""Situația cotelor pentru ecranul „Modele și cote” (F3.10, 18.2): cât s-a folosit și cât a rămas din
fiecare limită, starea întrerupătoarelor, blocajele. Doar citire (contoarele le scrie limitatorul,
F3.3)."""

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.gateway import cote
from app.gateway.candidat import Candidat
from app.gateway.cote import Fereastra


@dataclass(frozen=True)
class Cota:
    resursa: str  # „model” sau „cont” (limite comune contului furnizorului)
    fereastra: str  # minut | zi
    cereri_folosite: int
    cereri_limita: int | None
    tokeni_folositi: int
    tokeni_limita: int | None
    reset_la: dt.datetime  # începutul ferestrei următoare (UTC)

    @property
    def cereri_ramase(self) -> int | None:
        return None if self.cereri_limita is None else max(0, self.cereri_limita - self.cereri_folosite)

    @property
    def tokeni_ramasi(self) -> int | None:
        return None if self.tokeni_limita is None else max(0, self.tokeni_limita - self.tokeni_folositi)

    @property
    def epuizata(self) -> bool:
        return self.cereri_ramase == 0 or self.tokeni_ramasi == 0


@dataclass(frozen=True)
class Blocaj:
    pana_la: dt.datetime
    motiv: str


def cote_pentru(db: Session, c: Candidat, acum: dt.datetime) -> list[Cota]:
    """Cotele modelului și ale contului furnizorului, pentru minutul și ziua curente (doar axele cu
    limită)."""
    rezultat: list[Cota] = []
    for resursa, cheie, limite in (
        ("model", cote.cheie_model(c.model_id), c.limite_model),
        ("cont", cote.cheie_furnizor(c.furnizor_id), c.limite_furnizor),
    ):
        for fer in Fereastra:
            lim_cereri, lim_tokeni = limite.pe(fer)
            if lim_cereri is None and lim_tokeni is None:
                continue
            inceput = cote.inceput_fereastra(acum, fer, c.reset_zi_ora)
            r = db.execute(
                text(
                    "SELECT cereri, tokeni FROM gateway_contoare "
                    "WHERE cheie = :c AND fereastra = :f AND inceput = :i"
                ),
                {"c": cheie, "f": fer.value, "i": inceput},
            ).first()
            rezultat.append(
                Cota(
                    resursa,
                    fer.value,
                    int(r[0]) if r else 0,
                    lim_cereri,
                    int(r[1]) if r else 0,
                    lim_tokeni,
                    cote.sfarsit_fereastra(acum, fer, c.reset_zi_ora),
                )
            )
    return rezultat


def blocaj_pentru(db: Session, c: Candidat, acum: dt.datetime) -> Blocaj | None:
    r = db.execute(
        text(
            "SELECT max(pana_la), (array_agg(motiv ORDER BY pana_la DESC))[1] FROM gateway_blocaje "
            "WHERE cheie IN (:m, :f) AND pana_la > :a"
        ),
        {"m": cote.cheie_model(c.model_id), "f": cote.cheie_furnizor(c.furnizor_id), "a": acum},
    ).one()
    return Blocaj(r[0], r[1] or "") if r[0] is not None else None


def acum() -> dt.datetime:
    """Momentul gateway-ului (ceasul înlocuibil din teste): contoarele se scriu cu el, deci se citesc cu
    el."""
    from app.gateway import ceas

    return ceas.acum()
