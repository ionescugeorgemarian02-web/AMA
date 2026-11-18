"""Umbra, canarul, promovarea și revenirea unui prompt optimizat (F14.2, docs/11 §11.5 pașii 6–8, §11.6).

Etapele unui candidat ieșit din optimizator (`optimizari.stare = candidat`):

1. **umbra** — candidatul produce în paralel cu campionul pe livrabile reale, dar rezultatul nu se folosește
   (`ruteaza` dă `umbra`); după `MINIM_UMBRA` (20) livrabile cu scor, trece mai departe dacă nu e mai slab
   decât campionul
   (toleranța `TOLERANTA`) și nu pierde la conformitate; altfel `respins`.
2. **canar** — 10% din trafic pe candidat, 90% pe campion; aceeași gardă după `MINIM_CANAR` livrabile ale
   candidatului; o gardă picată = revenire automată.
3. **productie** — candidatul devine versiunea activă în registru (90% din trafic); 10% rămân pe campionul
   vechi (`nume@versiune`), grupul de control, până la `MINIM_CONTROL` livrabile în fiecare grup. Câștigul
   real se măsoară față de control (testul Welch din registrul de experimente, F11.4): control mai bun
   semnificativ → revenire automată; altfel `promovat` (100%, controlul se încheie) și câștigul rămâne scris.
4. **revenirea** dintr-o atingere (`revino`), din orice etapă și după promovare: dacă candidatul ajunsese
   activ, se creează o versiune nouă cu textul campionului vechi și se activează (registrul nu reactivează
   o versiune retrasă); altfel ciorna candidatului se retrage. Totul cu audit și urme.

Constituția (§11.6): înghețarea oprește pornirea și orice avans; o promovare pe săptămână pe componentă.
Repartizarea pe grupuri e deterministă după cheia livrabilului (aceeași cheie, același grup).
# NECONECTAT: producția (autorii din F6) cheamă încă promptul activ direct; `ruteaza` și `observa` sunt API-ul
prin care se leagă, iar scorul unui livrabil vine din verdictul validării. În teste, livrabilele sunt
simulate.
"""

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import gateway
from app.db import sesiune_agentie
from app.ids import new_id
from app.invatare import constitutie, experimente
from app.invatare.modele import ObservatiePromovare, Optimizare, Promovare
from app.logging import get_logger
from app.operare import audit, motor, urme

log = get_logger("app.invatare.promovare")
NUME = "invatare.promovari"
IN_CURS = ("umbra", "canar", "productie")
PROCENT = {"umbra": 0, "canar": 10, "productie": 90, "promovat": 100}
MINIM_UMBRA = 20  # livrabile reale în umbră (§11.5 pasul 6)
MINIM_CANAR = 20  # livrabile ale candidatului la 10% [I]
MINIM_CONTROL = 20  # livrabile în fiecare grup, la măsurarea față de control [I]
TOLERANTA = 0.05  # cât poate fi candidatul sub campion la media scorului, în umbră și la canar [I]
PRAG_CASTIG = 0.02  # diferența relativă minimă pentru „câștig” la măsurare [I]


class PromovareRefuzata(ValueError):
    pass


@dataclass(frozen=True)
class Rutare:
    """Ce versiune produce livrabilul (`folosit`) și, în umbră, ce versiune mai produce în paralel."""

    folosit: str
    grup: str | None = None
    umbra: str | None = None
    promovare_id: uuid.UUID | None = None


def galeata(promovare_id: uuid.UUID, cheie: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{promovare_id}:{cheie}".encode()).digest()[:2]) % 100


def garda(campion: list[tuple[float, bool]], candidat: list[tuple[float, bool]]) -> str | None:
    """Nucleu pur: motivul pentru care candidatul nu trece etapa, sau None. Perechi (scor, conform)."""
    if not campion or not candidat:
        return "lipsesc observațiile unuia dintre grupuri"

    def medie(x: list[tuple[float, bool]]) -> float:
        return sum(s for s, _ in x) / len(x)

    def conf(x: list[tuple[float, bool]]) -> float:
        return sum(c for _, c in x) / len(x)

    if conf(candidat) < conf(campion):
        return f"conformitatea candidatului ({conf(candidat):.2f}) e sub a campionului ({conf(campion):.2f})"
    if medie(candidat) < medie(campion) - TOLERANTA:
        return f"scorul candidatului ({medie(candidat):.3f}) e sub al campionului ({medie(campion):.3f})"
    return None


def _promovare(db: Session, promovare_id: uuid.UUID) -> Promovare:
    p = db.execute(
        select(Promovare).where(Promovare.id == promovare_id).with_for_update()
    ).scalar_one_or_none()
    if p is None:
        raise PromovareRefuzata("promovarea nu există")
    return p


def in_curs(db: Session, componenta: str) -> Promovare | None:
    return db.execute(
        select(Promovare).where(Promovare.componenta == componenta, Promovare.etapa.in_(IN_CURS))
    ).scalar_one_or_none()


def _treci(db: Session, p: Promovare, etapa: str, motiv: str, acum: dt.datetime, **detalii: Any) -> None:
    din = p.etapa
    p.istoric = [
        *p.istoric,
        {"din": din, "in": etapa, "la": acum.isoformat(), "motiv": motiv[:300], **detalii},
    ]
    p.etapa, p.motiv, p.actualizat_la = etapa, motiv[:300], acum
    p.procent_candidat = PROCENT.get(etapa, 0)
    if etapa not in IN_CURS:
        p.incheiat_la = acum
    db.flush()
    audit.record(
        db, f"invatare.promovare_{etapa}", obiect_tip="promovare", obiect_id=p.id, tenant_id=None,
        actor_tip="sistem" if detalii.get("utilizator") is None else None,
        detalii={"componenta": p.componenta, "din": din, "motiv": motiv[:120]},
    )  # fmt: skip
    rezultat = {"respins": "respins", "revenit": "respins"}.get(etapa, "ok")
    urme.inregistreaza(
        db, NUME, f"etapa_{etapa}", rezultat=rezultat, motiv=motiv[:300], obiect_tip="promovare",
        obiect_id=p.id, intrari={"din": din, "componenta": p.componenta},
        iesiri={"procent_candidat": p.procent_candidat,
                **{k: v for k, v in detalii.items() if k != "utilizator"}},
    )  # fmt: skip


def poate_porni(db: Session, componenta: str, acum: dt.datetime) -> None:
    """Constituția: înghețarea și „o schimbare o dată” (o promovare pe săptămână pe componentă)."""
    if constitutie.inghetat(db):
        raise constitutie.ConstitutieIncalcata("învățarea este înghețată: nicio promovare până la dezghețare")
    ultima = db.execute(
        select(func.max(Promovare.promovat_la)).where(
            Promovare.componenta == componenta, Promovare.promovat_la.is_not(None)
        )
    ).scalar_one()
    if ultima is not None and ultima > acum - constitutie.SAPTAMANA:
        urmatoarea = (ultima + constitutie.SAPTAMANA).date().isoformat()
        raise constitutie.ConstitutieIncalcata(
            f"componenta a avut deja o promovare în ultimele 7 zile: următoarea, din {urmatoarea}"
        )


def porneste(db: Session, optimizare_id: uuid.UUID, *, acum: dt.datetime | None = None) -> Promovare:
    """Pune candidatul unei rulări în umbră."""
    acum = acum or dt.datetime.now(dt.UTC)
    o = db.get(Optimizare, optimizare_id)
    if o is None or o.stare != "candidat" or o.candidat_versiune is None:
        raise PromovareRefuzata("doar un candidat al optimizatorului se poate promova")
    if db.execute(select(Promovare.id).where(Promovare.optimizare_id == o.id)).first() is not None:
        raise PromovareRefuzata("candidatul acestei rulări a mai fost pornit")
    if in_curs(db, o.componenta) is not None:
        raise PromovareRefuzata("componenta are deja o promovare în curs")
    activ = gateway.prompturi.rezolva(db, o.componenta)
    if activ is None or activ.versiune != o.campion_versiune:
        raise PromovareRefuzata("campionul s-a schimbat de la rularea optimizatorului")
    poate_porni(db, o.componenta, acum)
    p = Promovare(
        optimizare_id=o.id, componenta=o.componenta, campion_versiune=o.campion_versiune,
        candidat_versiune=o.candidat_versiune, etapa="umbra", procent_candidat=0, creat_la=acum,
        actualizat_la=acum,
        istoric=[{"din": None, "in": "umbra", "la": acum.isoformat(), "motiv": "pornită"}], motiv="pornită",
    )  # fmt: skip
    db.add(p)
    db.flush()
    audit.record(
        db, "invatare.promovare_umbra", obiect_tip="promovare", obiect_id=p.id, tenant_id=None,
        actor_tip="sistem",
        detalii={"componenta": p.componenta, "candidat": p.candidat_versiune},
    )  # fmt: skip
    urme.inregistreaza(
        db, NUME, "etapa_umbra", obiect_tip="promovare", obiect_id=p.id,
        intrari={"optimizare": str(o.id), "componenta": o.componenta},
        iesiri={"campion": p.campion_versiune, "candidat": p.candidat_versiune},
    )  # fmt: skip
    return p


def ruteaza(db: Session, componenta: str, cheie: str) -> Rutare:
    """Versiunea promptului pentru un livrabil (cheia = id-ul lui); fără promovare în curs, cea activă."""
    p = in_curs(db, componenta)
    if p is None:
        return Rutare(folosit=componenta)
    campion, candidat = f"{componenta}@{p.campion_versiune}", f"{componenta}@{p.candidat_versiune}"
    if p.etapa == "umbra":
        return Rutare(folosit=campion, grup="campion", umbra=candidat, promovare_id=p.id)
    pe_candidat = galeata(p.id, cheie) < p.procent_candidat
    return Rutare(
        folosit=candidat if pe_candidat else campion, grup="candidat" if pe_candidat else "campion",
        promovare_id=p.id,
    )  # fmt: skip


def observa(
    db: Session,
    promovare_id: uuid.UUID,
    *,
    grup: str,
    cheie: str,
    scor: float,
    conform: bool,
    umbra: bool = False,
) -> None:
    """Scorul unui livrabil (din verdictul validării), pe etapa curentă. Aceeași cheie de două ori: o dată."""
    p = db.get(Promovare, promovare_id)
    if p is None or p.etapa not in IN_CURS:
        return
    db.execute(
        insert(ObservatiePromovare)
        .values(id=new_id(), promovare_id=p.id, etapa=p.etapa, grup=grup, umbra=umbra, cheie=cheie[:100],
                scor=max(0.0, min(1.0, scor)), conform=conform)
        .on_conflict_do_nothing()
    )  # fmt: skip


def _obs(db: Session, p: Promovare, grup: str) -> list[tuple[float, bool]]:
    return [
        (r.scor, r.conform)
        for r in db.execute(
            select(ObservatiePromovare.scor, ObservatiePromovare.conform).where(
                ObservatiePromovare.promovare_id == p.id,
                ObservatiePromovare.etapa == p.etapa,
                ObservatiePromovare.grup == grup,
            )
        )
    ]


def masoara(control: list[float], candidat: list[float]) -> tuple[str | None, dict[str, Any]]:
    """Câștigul real față de control (a = control, b = candidat), cu regula registrului de experimente."""
    return experimente.verdict(control, candidat, minim=MINIM_CONTROL, prag=PRAG_CASTIG, expirat=False)


def avanseaza(db: Session, promovare_id: uuid.UUID, *, acum: dt.datetime | None = None) -> Promovare:
    """Aplică regula etapei curente. Întoarce promovarea (eventual în aceeași etapă, dacă datele nu ajung)."""
    acum = acum or dt.datetime.now(dt.UTC)
    p = _promovare(db, promovare_id)
    if p.etapa not in IN_CURS or constitutie.inghetat(db):
        return p
    camp, cand = _obs(db, p, "campion"), _obs(db, p, "candidat")
    if p.etapa in ("umbra", "canar"):
        if len(cand) < (MINIM_UMBRA if p.etapa == "umbra" else MINIM_CANAR):
            return p
        problema = garda(camp, cand)
        cifre = {"n_campion": len(camp), "n_candidat": len(cand)}
        if problema is not None:
            if p.etapa == "umbra":
                gateway.prompturi.retrage(db, p.componenta, p.candidat_versiune)
                _treci(db, p, "respins", f"umbra: {problema}", acum, **cifre)
            else:
                _revino(db, p, f"garda canarului: {problema}", acum, cifre=cifre)
        elif p.etapa == "umbra":
            _treci(db, p, "canar", "umbra trecută: candidatul nu e mai slab decât campionul", acum, **cifre)
        else:
            gateway.prompturi.activeaza(db, p.componenta, p.candidat_versiune)
            _treci(db, p, "productie", "canarul trecut: candidatul devine activ, 10% rămân control", acum,
                   **cifre)  # fmt: skip
        return p
    concluzie, cifre = masoara([s for s, _ in camp], [s for s, _ in cand])
    if concluzie is None:
        return p
    p.castig = {"concluzie": concluzie, **cifre}
    if concluzie == "castiga_a":
        _revino(db, p, "grupul de control a fost mai bun: revenire automată", acum, cifre=cifre)
    else:
        p.promovat_la = acum
        eticheta = (
            "câștig măsurat față de control" if concluzie == "castiga_b" else "fără diferență față de control"
        )
        _treci(db, p, "promovat", f"promovat: {eticheta}", acum, concluzie=concluzie)
    return p


def _revino(
    db: Session, p: Promovare, motiv: str, acum: dt.datetime, *, cifre: dict[str, Any] | None = None,
    utilizator_id: uuid.UUID | None = None,
) -> None:  # fmt: skip
    activ = gateway.prompturi.rezolva(db, p.componenta)
    if activ is not None and activ.versiune == p.candidat_versiune:  # candidatul ajunsese activ
        vechi = gateway.prompturi.rezolva(db, f"{p.componenta}@{p.campion_versiune}")
        assert vechi is not None  # noqa: S101  (versiunile nu se șterg din registru)
        nou = gateway.prompturi.creeaza(
            db, p.componenta, profil=vechi.profil, sablon=vechi.sablon, sistem=vechi.sistem,
            schema=gateway.prompturi.schema_din(vechi.schema_nume), utilizator_id=utilizator_id,
            descriere=f"Revenire la {p.componenta}@{p.campion_versiune} (promovarea {p.id})"[:300],
        )  # fmt: skip
        gateway.prompturi.activeaza(db, p.componenta, nou.versiune, utilizator_id=utilizator_id)
        p.revenire_versiune = nou.versiune
    else:
        gateway.prompturi.retrage(db, p.componenta, p.candidat_versiune, utilizator_id=utilizator_id)
    _treci(db, p, "revenit", motiv, acum, utilizator=None if utilizator_id is None else str(utilizator_id),
           revenire=p.revenire_versiune, **(cifre or {}))  # fmt: skip


def revino(
    db: Session, promovare_id: uuid.UUID, *, utilizator_id: uuid.UUID | None, motiv: str,
    acum: dt.datetime | None = None,
) -> Promovare:  # fmt: skip
    """Revenirea dintr-o atingere (§11.5 pasul 8, §11.6 punctul 8), din orice etapă sau după promovare."""
    p = _promovare(db, promovare_id)
    if p.etapa in ("respins", "revenit"):
        raise PromovareRefuzata("promovarea s-a încheiat deja fără candidat")
    if len(motiv.strip()) < 3:
        raise PromovareRefuzata("scrie de ce revii")
    if p.etapa == "promovat":
        activ = gateway.prompturi.rezolva(db, p.componenta)
        if activ is None or activ.versiune != p.candidat_versiune:
            raise PromovareRefuzata("între timp a fost activată altă versiune: revenirea nu mai e sigură")
    _revino(
        db,
        p,
        f"revenire manuală: {motiv.strip()}",
        acum or dt.datetime.now(dt.UTC),
        utilizator_id=utilizator_id,
    )
    return p


def istoric(db: Session, componenta: str | None = None, *, limita: int = 50) -> list[Promovare]:
    q = select(Promovare).order_by(Promovare.creat_la.desc()).limit(limita)
    if componenta:
        q = q.where(Promovare.componenta == componenta)
    return list(db.execute(q).scalars())


def ruleaza(acum: dt.datetime | None = None) -> int:
    """Evaluarea zilnică a promovărilor în curs. Întoarce câte și-au schimbat etapa."""
    with sesiune_agentie() as db:
        ids = list(
            db.execute(select(Promovare.id, Promovare.etapa).where(Promovare.etapa.in_(IN_CURS))).all()
        )
    schimbate = 0
    for pid, etapa in ids:
        try:
            with sesiune_agentie() as db:
                schimbate += avanseaza(db, pid, acum=acum).etapa != etapa
        except Exception as exc:
            log.warning("promovare neevaluată", extra={"tip_eroare": type(exc).__name__})
    return schimbate


@motor.pas("invatare.pas_promovari")
def _pas() -> str:
    return str(ruleaza())


@motor.flux(NUME)
def flux(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _pas()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME, "50 6 * * *", flux)


declara_programari()
