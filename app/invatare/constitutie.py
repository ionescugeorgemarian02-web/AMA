"""Constituția învățării (F11.5, docs/11 §11.6): gardurile tehnice care nu depind de bunăvoința codului.

1. **Validatorii sunt în afara învățării.** Tot ce face învățarea rulează în `flux_invatare(db)`, care
   marchează tranzacția (`app.flux = 'invatare'`). Cât marcajul e pus, baza refuză orice scriere în regulile
   validatorilor pe client și în registrul de fapte (declanșatorul `ama_fara_invatare`, migrarea 0093).
   Pachetele de reguli sunt fișiere în repo, pe care aplicația nu le scrie; garda statică
   `scripts/check_invatare.py` interzice modulului de învățare să importe regulile, registrul de validatori
   sau să deschidă fișiere pentru scriere.
2. **O schimbare o dată** (punctul 4): cel mult o promovare pe săptămână pe domeniu (`poate_promova`).
3. **Înghețarea** (punctul 9): un buton global care oprește toate promovările până e dezactivat.
4. **Indicatorii de gardă** (punctul 3), nucleu pur (`garda_incalcata`): dacă ascunderile, dezabonările,
   comentariile negative sau reclamațiile cresc peste prag după o schimbare, schimbarea se anulează.
   # NECONECTAT: platformele nu dau încă aceste cifre prin cititorii din F10.1, deci regula există și e
   testată, dar nu e chemată automat de nimic.
"""

import datetime as dt
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.invatare.modele import Lectie
from app.operare import audit

SAPTAMANA = dt.timedelta(days=7)
INDICATORI_GARDA = ("ascunderi", "dezabonari", "comentarii_negative", "reclamatii")
PRAG_GARDA = 0.20  # creștere relativă a ratei care anulează o „îmbunătățire” [I]


class ConstitutieIncalcata(RuntimeError):
    """Schimbarea cerută încalcă o regulă a Constituției."""


@contextmanager
def flux_invatare(db: Session) -> Iterator[None]:
    """Marchează tranzacția ca flux de învățare; la ieșire reface marcajul dinainte. Cât e activ, baza
    refuză scrierile în regulile validatorilor și în registrul de fapte."""
    anterior = db.execute(text("SELECT coalesce(current_setting('app.flux', true), '')")).scalar_one()
    db.execute(text("SELECT set_config('app.flux', 'invatare', true)"))
    yield
    # La o excepție nu se reface nimic aici: tranzacția (sau punctul de salvare) se anulează, iar marcajul,
    # fiind local tranzacției, dispare odată cu ea. O comandă în plus ar ascunde eroarea adevărată.
    db.execute(text("SELECT set_config('app.flux', :v, true)"), {"v": anterior})


def inghetat(db: Session) -> bool:
    return bool(db.execute(text("SELECT inghetat FROM invatare_stare WHERE id = 1")).scalar_one())


def ingheata(db: Session, *, activ: bool, utilizator_id: uuid.UUID, motiv: str = "") -> None:
    """Butonul de înghețare (doar cu scop de agenție: politica bazei refuză altfel)."""
    r = db.execute(
        text(
            "UPDATE invatare_stare SET inghetat = :a, motiv = :m, schimbat_de = :u, schimbat_la = now() "
            "WHERE id = 1 RETURNING id"
        ),
        {"a": activ, "m": motiv.strip()[:300], "u": utilizator_id},
    ).first()
    if r is None:
        raise ConstitutieIncalcata("înghețarea se schimbă doar cu drept de agenție")
    audit.record(
        db,
        "invatare.inghetata" if activ else "invatare.dezghetata",
        obiect_tip="invatare",
        obiect_id="stare",
        utilizator_id=utilizator_id,
        detalii={"motiv": motiv.strip()[:120]},
    )


def poate_promova(
    db: Session, tenant_id: uuid.UUID, domeniu_tip: str, domeniu: str, *, acum: dt.datetime | None = None
) -> None:
    """Aruncă `ConstitutieIncalcata` dacă promovarea nu e permisă acum: învățarea e înghețată sau domeniul
    a mai avut o promovare în ultimele 7 zile."""
    acum = acum or dt.datetime.now(dt.UTC)
    if inghetat(db):
        raise ConstitutieIncalcata("învățarea este înghețată: nicio promovare până la dezghețare")
    ultima = db.execute(
        select(Lectie.decis_la)
        .where(
            Lectie.tenant_id == tenant_id,
            Lectie.domeniu_tip == domeniu_tip,
            Lectie.domeniu == domeniu,
            Lectie.stare == "activa",
            Lectie.decis_la > acum - SAPTAMANA,
            Lectie.decis_la <= acum,
        )
        .order_by(Lectie.decis_la.desc())
        .limit(1)
    ).scalar_one_or_none()
    if ultima is not None:
        urmatoarea = (ultima + SAPTAMANA).date().isoformat()
        raise ConstitutieIncalcata(
            f"domeniul a avut deja o promovare în ultimele 7 zile: următoarea, din {urmatoarea}"
        )


def garda_incalcata(
    inainte: dict[str, float], dupa: dict[str, float], *, prag: float = PRAG_GARDA
) -> list[str]:
    """Nucleu pur: indicatorii de gardă (rate, între 0 și 1) care au crescut cu mai mult de `prag` relativ.
    Un indicator care apare de la zero se socotește încălcat."""
    incalcati = []
    for k in INDICATORI_GARDA:
        a, d = inainte.get(k), dupa.get(k)
        if a is None or d is None:
            continue
        if (a == 0 and d > 0) or (a > 0 and (d - a) / a > prag):
            incalcati.append(k)
    return incalcati
