"""Calibrarea judecătorilor (G14, F5.8, docs/09 §9.6): eșantion săptămânal la om, acordul pe judecător,
deriva.

- `esantioneaza(db, de_la, pana_la, n)`: din verdictele V3 / V4 salvate în fereastră (judecătorul a răspuns,
nu a fost
  indisponibil) alege, determinist, cel mult `n` pe judecător și le pune în coada de etichetare
  (`calibrare_etichete`).
  Rulează săptămânal ca job programat (`validare.calibrare_saptamanala`, luni 05:41, ora României).
- `eticheteaza(db, id, eticheta, motiv, utilizator_id)`: un om spune „corect” / „greșit” (+ motiv). Un
„greșit” devine
  exemplu PROPUS pentru setul de aur (`exemple.propune`, sursa `eticheta`), pe care îl promovează tot un om.
- `statistici(db)`: pe judecător acordul (procent, kappa, interval Wilson, număr de etichete) și alerta sub
85% cu minimum
  de etichete; `deriva(db, de_la, pana_la)`: rata de trecere pe săptămâni și alertele de derivă.
- `verifica_si_anunta(db, ...)`: trimite notificările (nivel „important”) pentru acord sub prag și derivă.

Etichetele sunt date de client (RLS): un operator vede coada clientului lui; statisticile pe toți clienții le
vede
proprietarul (scop de agenție).
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import productie
from app.ids import new_id
from app.operare import audit, notificari
from app.validare import calibrare_nucleu as nucleu
from app.validare import continut as continut_mod
from app.validare import exemple
from app.validare.modele import EtichetaCalibrare, ExempluPropus, VerdictSalvat

ETICHETE = ("corect", "gresit")
N_IMPLICIT = 10  # [I] verdicte pe judecător pe săptămână


class EtichetaInvalida(ValueError):
    """Eticheta nu respectă regulile (valoare, motiv, deja pusă)."""


def judecator_din(v: VerdictSalvat) -> str:
    return f"{v.validator}@{v.treapta}"


def versiune_din(v: VerdictSalvat) -> str:
    d = v.detalii or {}
    return f"{v.validator_versiune}|{d.get('prompt', '')}|{d.get('model', '')}"[:300]


def saptamana_din(t: dt.datetime) -> str:
    an, sapt, _ = t.isocalendar()
    return f"{an}-W{sapt:02d}"


def _verdicte_judecatori(db: Session, de_la: dt.datetime, pana_la: dt.datetime) -> list[VerdictSalvat]:
    q = select(VerdictSalvat).where(
        VerdictSalvat.treapta.in_(("V3", "V4")),
        VerdictSalvat.creat_la >= de_la,
        VerdictSalvat.creat_la < pana_la,
    )
    # un judecător indisponibil (fără model în detalii) nu a judecat nimic: nu intră în statistică
    return [
        v for v in db.execute(q).scalars() if (v.detalii or {}).get("model") and "eroare" not in v.detalii
    ]


def esantioneaza(
    db: Session, de_la: dt.datetime, pana_la: dt.datetime, *, n: int = N_IMPLICIT, saminta: str | None = None
) -> list[EtichetaCalibrare]:
    """Pune în coadă eșantionul ferestrei (idempotent: un verdict intră o singură dată)."""
    deja = set(db.execute(select(EtichetaCalibrare.verdict_id)).scalars())
    candidati = {str(v.id): v for v in _verdicte_judecatori(db, de_la, pana_la) if v.id not in deja}
    ales = nucleu.esantioneaza(
        ((i, judecator_din(v)) for i, v in candidati.items()), n, saminta or pana_la.isoformat()
    )
    noi: list[EtichetaCalibrare] = []
    for i in ales:
        v = candidati[i]
        e = EtichetaCalibrare(
            id=new_id(),
            tenant_id=v.tenant_id,
            verdict_id=v.id,
            judecator=judecator_din(v),
            versiune=versiune_din(v),
            judecator_esec=v.rezultat != "trece",
            saptamana=saptamana_din(v.creat_la),
        )
        db.add(e)
        noi.append(e)
    db.flush()
    return noi


@dataclass(frozen=True)
class ElementCoada:
    eticheta: EtichetaCalibrare
    verdict: VerdictSalvat
    text: str
    tip: str
    canal: str


def coada(db: Session, *, limita: int = 50) -> list[ElementCoada]:
    """Verdictele de etichetat, cele mai vechi primele, cu dovezile și textul judecat (clientul curent,
    RLS)."""
    rows = db.execute(
        select(EtichetaCalibrare, VerdictSalvat)
        .join(VerdictSalvat, VerdictSalvat.id == EtichetaCalibrare.verdict_id)
        .where(EtichetaCalibrare.stare == "de_etichetat")
        .order_by(EtichetaCalibrare.creat_la, EtichetaCalibrare.id)
        .limit(limita)
    ).all()
    iesire = []
    for e, v in rows:
        liv = productie.citeste(db, v.livrabil_id)
        text = continut_mod.citeste(db, v.livrabil_id, v.versiune).text
        iesire.append(ElementCoada(e, v, text, liv.tip if liv else "", liv.canal if liv else ""))
    return iesire


def eticheteaza(
    db: Session,
    eticheta_id: uuid.UUID,
    *,
    eticheta: str,
    motiv: str,
    utilizator_id: uuid.UUID,
    acum: dt.datetime | None = None,
) -> tuple[EtichetaCalibrare, ExempluPropus | None]:
    """Eticheta unui om. „Greșit” cere motiv și propune exemplul pentru setul de aur."""
    if eticheta not in ETICHETE:
        raise EtichetaInvalida("eticheta este „corect” sau „gresit”")
    motiv = motiv.strip()[:500]
    if eticheta == "gresit" and len(motiv) < 3:
        raise EtichetaInvalida("un verdict greșit cere motivul")
    e = db.execute(
        select(EtichetaCalibrare).where(EtichetaCalibrare.id == eticheta_id).with_for_update()
    ).scalar_one_or_none()
    if e is None:
        raise LookupError(str(eticheta_id))
    if e.stare != "de_etichetat":
        raise EtichetaInvalida("verdictul are deja etichetă")
    e.stare, e.eticheta, e.motiv = "etichetat", eticheta, motiv
    e.etichetat_de, e.etichetat_la = utilizator_id, acum or dt.datetime.now(dt.UTC)
    db.flush()
    propus: ExempluPropus | None = None
    if eticheta == "gresit":
        v = db.get(VerdictSalvat, e.verdict_id)
        liv = productie.citeste(db, v.livrabil_id) if v else None
        if v is not None and liv is not None:
            propus, _ = exemple.propune(
                db,
                v,
                sursa="eticheta",
                asteptat="trece" if e.judecator_esec else "esec",
                severitate=None if e.judecator_esec else "majora",
                motiv=motiv,
                utilizator_id=utilizator_id,
                tip=liv.tip,
                canal=liv.canal,
            )
    audit.record(
        db,
        "calibrare.eticheta",
        obiect_tip="verdict",
        obiect_id=e.verdict_id,
        utilizator_id=utilizator_id,
        tenant_id=e.tenant_id,
        detalii={"judecator": e.judecator, "eticheta": eticheta},
    )
    return e, propus


def statistici(db: Session) -> dict[str, dict[str, Any]]:
    """Acordul pe judecător (toate etichetele vizibile sesiunii)."""
    rows = db.execute(
        select(
            EtichetaCalibrare.judecator, EtichetaCalibrare.judecator_esec, EtichetaCalibrare.eticheta
        ).where(EtichetaCalibrare.stare == "etichetat")
    ).all()
    pe: dict[str, list[tuple[bool, bool]]] = {}
    for jud, esec, et in rows:
        pe.setdefault(jud, []).append((bool(esec), et == "corect"))
    in_asteptare = set(
        db.execute(
            select(EtichetaCalibrare.judecator).where(EtichetaCalibrare.stare == "de_etichetat")
        ).scalars()
    )
    judecatori = sorted(set(pe) | set(in_asteptare))
    return {j: {**nucleu.acord(pe.get(j, [])).json(), "de_etichetat": _numar(db, j)} for j in judecatori}


def _numar(db: Session, judecator: str) -> int:
    return len(
        db.execute(
            select(EtichetaCalibrare.id).where(
                EtichetaCalibrare.judecator == judecator, EtichetaCalibrare.stare == "de_etichetat"
            )
        ).all()
    )


def saptamani(db: Session, de_la: dt.datetime, pana_la: dt.datetime) -> list[nucleu.Saptamana]:
    agregat: dict[tuple[str, str, str], list[int]] = {}
    for v in _verdicte_judecatori(db, de_la, pana_la):
        k = (judecator_din(v), versiune_din(v), saptamana_din(v.creat_la))
        a = agregat.setdefault(k, [0, 0])
        a[0] += 1
        a[1] += v.rezultat == "trece"
    return [nucleu.Saptamana(j, ver, s, t, tr) for (j, ver, s), (t, tr) in sorted(agregat.items())]


def deriva(db: Session, de_la: dt.datetime, pana_la: dt.datetime) -> list[nucleu.Deriva]:
    return nucleu.deriva(saptamani(db, de_la, pana_la))


def verifica_si_anunta(db: Session, de_la: dt.datetime, pana_la: dt.datetime) -> list[str]:
    """Alertele de calibrare (acord sub prag, derivă), trimise ca notificări „importante”. Întoarce
    textele."""
    texte = [
        f"Judecătorul {j}: acord cu omul {s['procent'] * 100:.0f}% pe {s['etichete']} etichete (prag 85%)."
        for j, s in statistici(db).items()
        if s["sub_prag"]
    ]
    texte += [
        f"Derivă la {d.judecator}: rata de trecere {d.rata * 100:.0f}% în {d.saptamana}, față de "
        f"{d.referinta * 100:.0f}% înainte, fără schimbare de prompt sau versiune."
        for d in deriva(db, de_la, pana_la)
    ]
    for t in texte:
        notificari.notifica(
            notificari.Nivel.IMPORTANT, "Calibrarea judecătorilor", t, url="/validatoare/calibrare"
        )
    return texte
