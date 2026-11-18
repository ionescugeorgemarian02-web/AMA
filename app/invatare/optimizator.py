"""Optimizatorul de prompturi (F14.1, N5, docs/11 §11.5): rulare nocturnă, candidat, raport, comparație cu
campionul pe setul de test.

- **Componenta** = numele unui prompt din registrul gateway-ului; **campionul** = versiunea lui activă.
- **Setul de aur** = date în repo (`evaluare/optimizare/<componenta>.jsonl`): exemple cu variabilele
  promptului și criteriile automate ale testului comparativ (`gateway.criterii`), fără date de client.
  Împărțirea în antrenare și test e deterministă (după amprenta id-ului), ca o rulare să nu-și aleagă
  singură testul.
- **Scorul** unei versiuni = calitatea (media criteriilor) × conformitatea (fracția ieșirilor fără probleme
  blocante de limbă, verificate de `app.validare`), obiectivul compus din §11.6 punctul 2.
- **Căutarea** (reflexivă, în spiritul GEPA, fără dependențe noi; D-020): propunătorul citește exemplele
  ratate de campion pe antrenare și propune până la 3 instrucțiuni de adăugat la mesajul de sistem. Doar se
  ADAUGĂ instrucțiuni: nimic din ce cerea campionul (inclusiv regulile de conformitate) nu se șterge.
  Fiecare variantă devine o ciornă nouă în registru; cea mai bună pe antrenare se măsoară pe test, față de
  campion.
- **Decizia:** candidatul rămâne (`stare = candidat`) doar dacă scorul compus pe test bate campionul cu
  `MARJA` și conformitatea nu scade; altfel ciornele se retrag (`fara_candidat`). Promovarea e pasul F14.2.
- Apelurile trec prin gateway (P3, clientul intern al evaluărilor); urme pentru rulare și pentru fiecare
  scorare.
"""

import datetime as dt
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import gateway, validare
from app.db import sesiune_agentie
from app.invatare.modele import Optimizare
from app.logging import get_logger
from app.operare import audit, motor, urme
from app.operare.motor import Prioritate

log = get_logger("app.invatare.optimizator")
NUME = "invatare.optimizator"
DIRECTOR_AUR = Path(__file__).resolve().parents[2] / "evaluare" / "optimizare"
PROMPT_REFLECTIE = "invatare.reflectie"
MARJA = 0.03  # cât trebuie să bată candidatul campionul pe test, la scorul compus [I]
FRACTIE_TEST = 0.30
MAX_CANDIDATI = 3
MAX_ESECURI_IN_PROPUNERE = 8


class OptimizareRefuzata(ValueError):
    pass


@dataclass(frozen=True)
class Exemplu:
    id: str
    variabile: dict[str, Any]
    criterii: dict[str, Any]


@dataclass(frozen=True)
class Varianta:
    """O versiune propusă: mesajul de sistem și șablonul complete, plus ce s-a schimbat și de ce."""

    sistem: str
    sablon: str
    schimbare: str
    motiv: str


@dataclass
class Scor:
    calitate: float
    conformitate: float
    n: int
    picate: list[dict[str, Any]] = field(default_factory=list)

    @property
    def compus(self) -> float:
        return round(self.calitate * self.conformitate, 4)

    def ca_dict(self) -> dict[str, Any]:
        return {
            "calitate": self.calitate,
            "conformitate": self.conformitate,
            "compus": self.compus,
            "n": self.n,
        }


Executor = Callable[[Session, str, Exemplu], dict[str, Any] | None]
Propunator = Callable[[Session, gateway.prompturi.Reperat, list[dict[str, Any]]], list[Varianta]]


class InstructiuneNoua(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instructiune: str = Field(min_length=10, max_length=400)
    motiv: str = Field(min_length=5, max_length=300)


class PropunereReflectie(gateway.Iesire):
    instructiuni: list[InstructiuneNoua] = Field(min_length=1, max_length=MAX_CANDIDATI)


# --- nucleu pur


def incarca_set(componenta: str, director: Path | None = None) -> list[Exemplu]:
    cale = (director or DIRECTOR_AUR) / f"{componenta}.jsonl"
    if not cale.exists():
        raise OptimizareRefuzata(f"componenta {componenta!r} nu are set de aur ({cale.name})")
    out = []
    for linie in cale.read_text(encoding="utf-8").splitlines():
        if linie.strip():
            d = json.loads(linie)
            out.append(Exemplu(str(d["id"]), dict(d["variabile"]), dict(d["criterii"])))
    return out


def _in_test(id_: str) -> bool:
    return hashlib.sha256(id_.encode()).digest()[0] / 256 < FRACTIE_TEST


def imparte(exemple: list[Exemplu]) -> tuple[list[Exemplu], list[Exemplu]]:
    """Antrenare / test, determinist după id. Ambele trebuie să aibă cel puțin două exemple."""
    test = [e for e in exemple if _in_test(e.id)]
    antrenare = [e for e in exemple if not _in_test(e.id)]
    if len(test) < 2 or len(antrenare) < 2:
        raise OptimizareRefuzata("setul de aur e prea mic pentru antrenare și test")
    return antrenare, test


def text_iesire(iesire: Any) -> str:
    """Tot textul unei ieșiri structurate (câmpuri, liste, obiecte imbricate), pe rânduri."""
    if isinstance(iesire, str):
        return iesire
    if isinstance(iesire, dict):
        return "\n".join(t for t in (text_iesire(v) for v in iesire.values()) if t)
    if isinstance(iesire, list):
        return "\n".join(t for t in (text_iesire(v) for v in iesire) if t)
    return ""


def conform(text: str) -> bool:
    """Conformitatea de limbă, cu validatorul real (G10, reguli): nicio problemă blocantă."""
    return not any(p.blocant for p in validare.probleme_limba(text))


def evalueaza_iesire(ex: Exemplu, iesire: dict[str, Any] | None) -> tuple[float, bool, dict[str, float]]:
    if iesire is None:
        return 0.0, False, {"schema_valida": 0.0}
    text = text_iesire(iesire)
    ev = gateway.criterii.evalueaza({**ex.criterii, "text_din": "text"}, {"text": text})
    return ev.scor, conform(text), ev.detalii


def bate(campion: Scor, candidat: Scor, marja: float = MARJA) -> tuple[bool, str]:
    if candidat.conformitate < campion.conformitate:
        return False, "candidatul pierde la conformitate"
    if candidat.compus < campion.compus + marja:
        return (
            False,
            f"candidatul nu bate campionul cu marja {marja:.2f} ({candidat.compus} față de {campion.compus})",
        )
    return True, f"candidatul bate campionul: {candidat.compus} față de {campion.compus} (marja {marja:.2f})"


def din_reflectie(campion: gateway.prompturi.Reperat, p: PropunereReflectie) -> list[Varianta]:
    return [
        Varianta(f"{campion.sistem.rstrip()}\n{i.instructiune.strip()}".strip(), campion.sablon,
                 f"adaugă la sistem: {i.instructiune.strip()}", i.motiv.strip())
        for i in p.instructiuni
    ]  # fmt: skip


# --- apelurile, prin gateway


def executor_gateway(db: Session, referinta: str, ex: Exemplu) -> dict[str, Any] | None:
    p = gateway.prompturi.rezolva(db, referinta)
    if p is None:
        raise OptimizareRefuzata(f"promptul {referinta} nu există")
    try:
        r = gateway.apeleaza(
            db, prompt=referinta, variabile=ex.variabile, schema=gateway.prompturi.schema_din(p.schema_nume),
            tenant_id=gateway.evaluare.client_intern(db), componenta=NUME, prioritate=Prioritate.P3,
        )  # fmt: skip
    except gateway.IesireInvalida:
        return None
    return r.iesire.model_dump(mode="json")


def propunator_gateway(
    db: Session, campion: gateway.prompturi.Reperat, picate: list[dict[str, Any]]
) -> list[Varianta]:
    r = gateway.apeleaza(
        db, prompt=PROMPT_REFLECTIE, schema=PropunereReflectie,
        variabile={"componenta": campion.nume, "sistem": campion.sistem, "sablon": campion.sablon,
                   "esecuri": json.dumps(picate[:MAX_ESECURI_IN_PROPUNERE], ensure_ascii=False)},
        tenant_id=gateway.evaluare.client_intern(db), componenta=NUME, prioritate=Prioritate.P3,
    )  # fmt: skip
    if not isinstance(r.iesire, PropunereReflectie):
        raise OptimizareRefuzata("propunătorul a întors altă schemă")
    return din_reflectie(campion, r.iesire)


# --- rularea


def scoreaza(db: Session, executor: Executor, referinta: str, exemple: list[Exemplu], *, set_: str) -> Scor:
    with urme.span(NUME, "scoreaza", db=db, obiect_tip="prompt", obiect_id=referinta,
                   intrari={"set": set_, "n": len(exemple)}) as s:  # fmt: skip
        scoruri, conforme, picate = [], 0, []
        for ex in exemple:
            sc, ok, detalii = evalueaza_iesire(ex, executor(db, referinta, ex))
            scoruri.append(sc)
            conforme += ok
            if sc < 1.0 or not ok:
                ratate = sorted(k for k, v in detalii.items() if v < 1.0) + ([] if ok else ["conformitate"])
                picate.append({"exemplu": ex.id, "variabile": ex.variabile, "ratate": ratate})
        rez = Scor(
            round(sum(scoruri) / len(scoruri), 4), round(conforme / len(exemple), 4), len(exemple), picate
        )
        s.iesiri = rez.ca_dict()
        return rez


def optimizeaza(
    db: Session,
    componenta: str,
    *,
    executor: Executor | None = None,
    propunator: Propunator | None = None,
    exemple: list[Exemplu] | None = None,
    marja: float = MARJA,
    acum: dt.datetime | None = None,
) -> Optimizare:
    """O rulare a optimizatorului pe o componentă (sesiune de agenție); întoarce rularea încheiată."""
    executor, propunator = executor or executor_gateway, propunator or propunator_gateway
    with urme.span(NUME, "optimizeaza", db=db, obiect_tip="prompt", obiect_id=componenta) as s:
        campion = gateway.prompturi.rezolva(db, componenta)
        if campion is None:
            raise OptimizareRefuzata(f"componenta {componenta!r} nu are o versiune activă")
        antrenare, test = imparte(exemple if exemple is not None else incarca_set(componenta))
        o = Optimizare(componenta=componenta, campion_versiune=campion.versiune, marja=marja)
        db.add(o)
        db.flush()
        schema = gateway.prompturi.schema_din(campion.schema_nume)
        camp_antr = scoreaza(db, executor, campion.referinta, antrenare, set_="antrenare")
        variante = propunator(db, campion, camp_antr.picate)[:MAX_CANDIDATI]
        incercari: list[tuple[int, Varianta, Scor]] = []
        for v in variante:
            p = gateway.prompturi.creeaza(
                db, componenta, profil=campion.profil, sablon=v.sablon, sistem=v.sistem, schema=schema,
                descriere=f"Candidat al optimizatorului (rularea {o.id}): {v.schimbare}"[:300],
            )  # fmt: skip
            incercari.append((p.versiune, v, scoreaza(db, executor, f"{componenta}@{p.versiune}", antrenare,
                                                      set_="antrenare")))  # fmt: skip
        raport: dict[str, Any] = {
            "exemple": {"antrenare": len(antrenare), "test": len(test)},
            "campion": {"versiune": campion.versiune, "antrenare": camp_antr.ca_dict()},
            "variante": [
                {"versiune": ver, "schimbare": v.schimbare, "motiv": v.motiv, "antrenare": sc.ca_dict()}
                for ver, v, sc in incercari
            ],
        }  # fmt: skip
        castig: tuple[int, Varianta, Scor] | None = max(incercari, key=lambda x: x[2].compus, default=None)
        if castig is None:
            o.stare, o.motiv = "fara_candidat", "propunătorul nu a dat nicio variantă"
            o.incheiat_la = acum or dt.datetime.now(dt.UTC)
        else:
            ver, v, _ = castig
            camp_test = scoreaza(db, executor, campion.referinta, test, set_="test")
            cand_test = scoreaza(db, executor, f"{componenta}@{ver}", test, set_="test")
            ok, motiv = bate(camp_test, cand_test, marja)
            raport["test"] = {
                "campion": camp_test.ca_dict(),
                "candidat": cand_test.ca_dict(),
                "versiune": ver,
            }
            raport["ce_s_a_schimbat"] = {"schimbare": v.schimbare, "motiv": v.motiv}
            o.scor_campion, o.scor_candidat, o.motiv = camp_test.compus, cand_test.compus, motiv
            o.stare, o.candidat_versiune = ("candidat", ver) if ok else ("fara_candidat", None)
            o.incheiat_la = acum or dt.datetime.now(dt.UTC)
        for ver, _, _ in incercari:
            if ver != o.candidat_versiune:
                gateway.prompturi.retrage(db, componenta, ver)
        o.raport = raport
        db.flush()
        audit.record(
            db, "invatare.optimizare", obiect_tip="optimizare", obiect_id=o.id, tenant_id=None,
            actor_tip="sistem",
            detalii={"componenta": componenta, "stare": o.stare, "candidat": o.candidat_versiune},
        )  # fmt: skip
        s.rezultat = "ok" if o.stare == "candidat" else "info"
        s.iesiri = {"optimizare": str(o.id), "stare": o.stare, "candidat": o.candidat_versiune,
                    "scor_campion": o.scor_campion, "scor_candidat": o.scor_candidat}  # fmt: skip
        return o


def componente_cu_set(director: Path | None = None) -> list[str]:
    return sorted(p.name.removesuffix(".jsonl") for p in (director or DIRECTOR_AUR).glob("*.jsonl"))


def istoric(db: Session, componenta: str | None = None, *, limita: int = 50) -> list[Optimizare]:
    q = select(Optimizare).order_by(Optimizare.inceput_la.desc()).limit(limita)
    if componenta:
        q = q.where(Optimizare.componenta == componenta)
    return list(db.execute(q).scalars())


def ruleaza_noaptea(acum: dt.datetime | None = None) -> int:
    """Rularea nocturnă: o optimizare pe fiecare componentă cu set de aur și versiune activă. O componentă cu
    un candidat încă neprocesat (sau o promovare în curs, F14.2) nu se mai optimizează. Întoarce câți
    candidați au ieșit."""
    candidati = 0
    for comp in componente_cu_set():
        try:
            with sesiune_agentie() as db:
                if gateway.prompturi.rezolva(db, comp) is None or _ocupata(db, comp):
                    continue
                candidati += optimizeaza(db, comp, acum=acum).stare == "candidat"
        except Exception as exc:
            log.warning("optimizare eșuată", extra={"componenta": comp, "tip_eroare": type(exc).__name__})
    return candidati


def _ocupata(db: Session, componenta: str) -> bool:
    return (
        db.execute(
            select(Optimizare.id)
            .where(Optimizare.componenta == componenta, Optimizare.stare == "candidat")
            .limit(1)
        ).first()
        is not None
    )


@motor.pas("invatare.pas_optimizator")
def _pas() -> str:
    return str(ruleaza_noaptea())


@motor.flux(NUME)
def flux(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _pas()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME, "15 2 * * *", flux, coada=motor.Coada.IO)


declara_programari()
