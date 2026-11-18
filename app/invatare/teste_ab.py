"""Testele A/B formale (F14.4, N7, docs/11 §11.2): ipoteza declarată dinainte, verdictul calculat automat.

- **Declararea** (`declara`): ipoteza, obiectul, varianta A (controlul) și B, indicatorul, efectul minim de
  interes (absolut), alfa, puterea și abaterea estimată. Mărimea eșantionului pe variantă se calculează atunci
  (`marime_esantion`, test bilateral pe medii): n = 2 · ((z₁₋α/₂ + z_putere) · σ / δ)², cel puțin `MINIM_N`.
  Nimic din ce s-a declarat nu se mai schimbă (declanșator în bază).
- **Regula de oprire** (`verdict`, nucleu pur), cu eșantion fix: înainte ca ambele variante să atingă n nu se
  calculează nimic (fără „trasul cu ochiul”, care umflă falsele pozitive). La n: testul Welch (aproximație
  normală), valoarea p bilaterală, intervalul de încredere al diferenței B − A. Câștigă B dacă p < α și
  diferența e pozitivă; A dacă p < α și diferența e negativă; altfel „fără diferență”. La termen, fără n:
  „neconcludent”.
- **Observațiile:** o valoare pe unitate (cheie unică pe test); după n, cele în plus nu mai contează
  (primele n
  în ordinea sosirii).
- Testele cu client sunt sub RLS; cele de agenție (fără client) le vede doar agenția. Urme la declarare și la
  verdict.
"""

import datetime as dt
import math
import uuid
from statistics import NormalDist
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db import sesiune_agentie
from app.ids import new_id
from app.invatare.modele import ExperimentFormal, ObservatieFormala
from app.logging import get_logger
from app.operare import audit, motor, urme

log = get_logger("app.invatare.teste_ab")
NUME = "invatare.teste_ab"
MINIM_N = 20
NORMALA = NormalDist()
ETICHETE = {
    "castiga_a": "câștigă A (controlul)",
    "castiga_b": "câștigă B",
    "fara_diferenta": "fără diferență semnificativă",
    "neconcludent": "neconcludent (eșantionul nu s-a atins la termen)",
}


class TestRefuzat(ValueError):
    __test__ = False  # nu e o clasă de teste pytest


def marime_esantion(efect_minim: float, abatere: float, *, alfa: float = 0.05, putere: float = 0.8) -> int:
    z = NORMALA.inv_cdf(1 - alfa / 2) + NORMALA.inv_cdf(putere)
    return max(MINIM_N, math.ceil(2 * (z * abatere / efect_minim) ** 2))


def _medie(x: list[float]) -> float:
    return sum(x) / len(x)


def _varianta(x: list[float]) -> float:
    m = _medie(x)
    return sum((v - m) ** 2 for v in x) / (len(x) - 1) if len(x) > 1 else 0.0


def verdict(
    a: list[float], b: list[float], *, n: int, alfa: float, efect_minim: float, expirat: bool
) -> tuple[str | None, dict[str, Any]]:
    """Nucleu pur: (verdictul sau None dacă testul continuă, cifrele)."""
    cifre: dict[str, Any] = {"n_a": len(a), "n_b": len(b), "n_cerut": n}
    if len(a) < n or len(b) < n:
        return ("neconcludent" if expirat else None), cifre
    a, b = a[:n], b[:n]
    ma, mb = _medie(a), _medie(b)
    eroare = math.sqrt(_varianta(a) / n + _varianta(b) / n)
    dif = mb - ma
    if eroare > 0:
        z = dif / eroare
        p = 2 * (1 - NORMALA.cdf(abs(z)))
    else:
        z, p = (0.0, 1.0) if dif == 0 else (math.copysign(math.inf, dif), 0.0)
    jum = NORMALA.inv_cdf(1 - alfa / 2) * eroare
    cifre |= {
        "medie_a": round(ma, 4), "medie_b": round(mb, 4), "diferenta": round(dif, 4),
        "interval": [round(dif - jum, 4), round(dif + jum, 4)], "z": None if math.isinf(z) else round(z, 3),
        "p": round(p, 5), "alfa": alfa, "efect_minim": efect_minim, "atinge_efectul_minim": abs(dif) >=
    efect_minim,
    }  # fmt: skip
    if p < alfa:
        return ("castiga_b" if dif > 0 else "castiga_a"), cifre
    return "fara_diferenta", cifre


def declara(
    db: Session, *, ipoteza: str, obiect: str, varianta_a: str, varianta_b: str, indicator: str,
    efect_minim: float, abatere_estimata: float, alfa: float = 0.05, putere: float = 0.8,
    durata_maxima_zile: int = 60, tenant_id: uuid.UUID | None = None, utilizator_id: uuid.UUID | None = None,
    acum: dt.datetime | None = None,
) -> ExperimentFormal:  # fmt: skip
    if len(ipoteza.strip()) < 10:
        raise TestRefuzat("ipoteza se scrie dinainte, în cuvinte (cel puțin 10 caractere)")
    if efect_minim <= 0 or abatere_estimata <= 0:
        raise TestRefuzat("efectul minim și abaterea estimată trebuie să fie pozitive")
    n = marime_esantion(efect_minim, abatere_estimata, alfa=alfa, putere=putere)
    t = ExperimentFormal(
        tenant_id=tenant_id, ipoteza=ipoteza.strip()[:400], obiect=obiect[:120], varianta_a=varianta_a[:120],
        varianta_b=varianta_b[:120], indicator=indicator[:60], efect_minim=efect_minim, alfa=alfa,
        putere=putere,
        abatere_estimata=abatere_estimata, n_pe_varianta=n, durata_maxima_zile=durata_maxima_zile,
        declarat_la=acum or dt.datetime.now(dt.UTC),
    )  # fmt: skip
    db.add(t)
    db.flush()
    audit.record(
        db, "invatare.test_ab_declarat", obiect_tip="test_ab", obiect_id=t.id, tenant_id=tenant_id,
        utilizator_id=utilizator_id, detalii={"obiect": t.obiect, "n_pe_varianta": n},
    )  # fmt: skip
    urme.inregistreaza(
        db, NUME, "declara", obiect_tip="test_ab", obiect_id=t.id, tenant_id=tenant_id,
        intrari={"ipoteza": t.ipoteza, "indicator": indicator, "efect_minim": efect_minim, "alfa": alfa,
                 "putere": putere}, iesiri={"n_pe_varianta": n},
    )  # fmt: skip
    return t


def observa(db: Session, test_id: uuid.UUID, *, varianta: str, cheie: str, valoare: float) -> None:
    t = db.get(ExperimentFormal, test_id)
    if t is None or t.stare != "in_curs":
        return
    db.execute(
        insert(ObservatieFormala)
        .values(id=new_id(), tenant_id=t.tenant_id, test_id=t.id, varianta=varianta, cheie=cheie[:100],
                valoare=float(valoare))
        .on_conflict_do_nothing()
    )  # fmt: skip


def _valori(db: Session, t: ExperimentFormal, varianta: str) -> list[float]:
    return list(
        db.execute(
            select(ObservatieFormala.valoare)
            .where(ObservatieFormala.test_id == t.id, ObservatieFormala.varianta == varianta)
            .order_by(ObservatieFormala.la, ObservatieFormala.id)
        ).scalars()
    )


def evalueaza(db: Session, test_id: uuid.UUID, *, acum: dt.datetime | None = None) -> ExperimentFormal:
    """Aplică regula de oprire declarată; un test încheiat rămâne cum e."""
    acum = acum or dt.datetime.now(dt.UTC)
    t = db.execute(
        select(ExperimentFormal).where(ExperimentFormal.id == test_id).with_for_update()
    ).scalar_one_or_none()
    if t is None:
        raise TestRefuzat("testul nu există")
    if t.stare != "in_curs":
        return t
    expirat = acum >= t.declarat_la + dt.timedelta(days=t.durata_maxima_zile)
    v, cifre = verdict(
        _valori(db, t, "a"), _valori(db, t, "b"), n=t.n_pe_varianta, alfa=t.alfa, efect_minim=t.efect_minim,
        expirat=expirat,
    )  # fmt: skip
    t.rezultat = cifre
    if v is not None:
        t.stare, t.verdict, t.incheiat_la = "incheiat", v, acum
        audit.record(
            db, "invatare.test_ab_incheiat", obiect_tip="test_ab", obiect_id=t.id, tenant_id=t.tenant_id,
            actor_tip="sistem", detalii={"verdict": v},
        )  # fmt: skip
        urme.inregistreaza(
            db, NUME, "verdict", obiect_tip="test_ab", obiect_id=t.id, tenant_id=t.tenant_id,
            rezultat="ok" if v != "neconcludent" else "info", motiv=ETICHETE[v], iesiri=cifre,
        )  # fmt: skip
    db.flush()
    return t


def lista(db: Session, *, limita: int = 100) -> list[ExperimentFormal]:
    return list(
        db.execute(
            select(ExperimentFormal).order_by(ExperimentFormal.declarat_la.desc()).limit(limita)
        ).scalars()
    )


def ruleaza(acum: dt.datetime | None = None) -> int:
    """Evaluarea zilnică a testelor în curs. Întoarce câte s-au încheiat."""
    with sesiune_agentie() as db:
        ids = list(
            db.execute(select(ExperimentFormal.id).where(ExperimentFormal.stare == "in_curs")).scalars()
        )
    incheiate = 0
    for tid in ids:
        try:
            with sesiune_agentie() as db:
                incheiate += evalueaza(db, tid, acum=acum).stare == "incheiat"
        except Exception as exc:
            log.warning("test A/B neevaluat", extra={"tip_eroare": type(exc).__name__})
    return incheiate


@motor.pas("invatare.pas_teste_ab")
def _pas() -> str:
    return str(ruleaza())


@motor.flux(NUME)
def flux(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _pas()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME, "45 6 * * *", flux)


declara_programari()
