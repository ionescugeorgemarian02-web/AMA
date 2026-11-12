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
from app.operare.motor import Prioritate


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


def _ramas_zi(c: Candidat, cote_c: list[Cota]) -> tuple[int | None, int | None]:
    """Cât mai poate consuma azi un model (cereri, tokeni) pentru munca obișnuită (P1–P3): limita
    zilei fără rezerva de 10% pentru P0, minus ce s-a folosit; limita contului se aplică peste.
    `None` = fără limită."""

    def ramas(limita: int | None, folosit: int) -> int | None:
        if limita is None:
            return None
        return max(0, (cote.plafon(limita, Fereastra.ZI, Prioritate.P1) or 0) - folosit)

    def deja(resursa: str) -> Cota | None:
        return next((x for x in cote_c if x.resursa == resursa and x.fereastra == "zi"), None)

    m, cont = deja("model"), deja("cont")
    cereri = ramas(m.cereri_limita, m.cereri_folosite) if m else None
    tokeni = ramas(m.tokeni_limita, m.tokeni_folositi) if m else None
    if cont is not None:
        return _min(cereri, ramas(cont.cereri_limita, cont.cereri_folosite)), _min(
            tokeni, ramas(cont.tokeni_limita, cont.tokeni_folositi)
        )
    return cereri, tokeni


def _min(a: int | None, b: int | None) -> int | None:
    return b if a is None else a if b is None else min(a, b)


def capacitate_profil(db: Session, profil: str, acum: dt.datetime) -> tuple[int | None, int | None]:
    """Cererile și tokenii care mai încap azi în cotele modelelor din lanțul profilului (F3.11).
    Doar lanțul principal: degradarea la modelul local nu se numără (prudent). Un profil
    necunoscut sau fără niciun model utilizabil acum are capacitate 0. `None` = fără limită."""
    from app.gateway import registru
    from app.gateway.intrerupator import StareSanatate
    from app.gateway.rutare import Cerinte, alege

    p = registru.profil(db, profil)
    if p is None:
        return 0, 0
    candidati = registru.candidati(db)
    cer = Cerinte(
        prioritate=Prioritate.P1,
        acum=acum,
        chei_configurate=frozenset(
            {c.furnizor for c in candidati if c.fara_cheie or registru.citeste_cheie_env(c.cheie_env)}
        ),
        sanatate={c.furnizor: StareSanatate(c.erori_consecutive, c.intrerupt_pana_la) for c in candidati},
    )  # fmt: skip
    pe_furnizor: dict[str, list[tuple[int | None, int | None]]] = {}
    for c in alege(p, candidati, cer).principal:
        pe_furnizor.setdefault(c.furnizor, []).append(_ramas_zi(c, cote_pentru(db, c, acum)))
    total_cereri: int | None = 0
    total_tokeni: int | None = 0
    for ramase in pe_furnizor.values():
        # suma modelelor furnizorului; limita contului (deja inclusă în fiecare) nu se adună de mai multe ori
        cereri = None if any(r[0] is None for r in ramase) else sum(r[0] or 0 for r in ramase)
        tokeni = None if any(r[1] is None for r in ramase) else sum(r[1] or 0 for r in ramase)
        cont_c = [r[0] for r in ramase if r[0] is not None]
        cont_t = [r[1] for r in ramase if r[1] is not None]
        if cereri is not None and cont_c:
            cereri = min(cereri, max(cont_c))
        if tokeni is not None and cont_t:
            tokeni = min(tokeni, max(cont_t))
        total_cereri = None if total_cereri is None or cereri is None else total_cereri + cereri
        total_tokeni = None if total_tokeni is None or tokeni is None else total_tokeni + tokeni
    return total_cereri, total_tokeni
