"""Rularea bancului: cascada pe seturi, într-o tranzacție ANULATĂ (nimic nu rămâne în bază).

Pentru fiecare profil de context se creează un client de probă cu contextul lui, apoi se trece pe contextul
acelui client
(izolarea pe client se aplică ca în producție) și se rulează exemplele profilului:
- exemplele de aur ale unui validator: DOAR pașii acelui validator (ce a prezis el, nu restul cascadei);
- materialele rele și cele bune: cascada întreagă, ca la un livrabil (`cascada.evalueaza`, aceeași agregare).

Doar treptele deterministe (V0–V2) rulează: judecătorii (V3 / V4) sunt opriți, iar pașii care cer vectori prin
gateway
(`foloseste_vectori`) sunt OMIȘI și listați în rezultat (nu se pretinde că au fost măsurați).
"""

import datetime as dt
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.conturi.roluri import Rol
from app.conturi.servicii import Actor, creeaza_client, creeaza_utilizator
from app.db import ContextDb, restrans_la_client, sesiune_anulata
from app.ids import new_id
from app.validare import cascada, registru
from app.validare.agregare import Decizie
from app.validare.banc import scoruri
from app.validare.banc.context import construieste
from app.validare.banc.seturi import Exemplu, Seturi
from app.validare.intrare import Continut, Intrare, SituatieLivrabil
from app.validare.registru import Pas
from app.validare.verdict import Severitate, Verdict

PAROLA_PROBA = (
    "parola-de-proba-banc-1"  # utilizatorul de probă nu se poate autentifica: tranzacția se anulează
)


@dataclass
class RezultatExemplu:
    id: str
    set: str
    validator: str
    asteptat: str  # clasa așteptată (trece / majora / critica) sau „blocat” pentru cele rele
    prezis: str
    blocat_de: list[str] = field(default_factory=list)  # validatorii cu eșec
    avertismente: int = 0
    nu_se_aplica: bool = False
    decizie: str = ""


def _pasi(e: Exemplu) -> list[Pas]:
    return [
        p
        for p in registru.pasi_pentru(e.tip, e.canal, judecatori=False, v4=False)
        if not p.definitie.foloseste_vectori
    ]


def omise() -> list[str]:
    """Pașii pe care bancul îi omite (cer vectori prin gateway): „G4@V2”, „G7@V2”."""
    return sorted(
        f"{d.cod}@{d.treapta.value}"
        for d in registru.toate()
        if d.foloseste_vectori and not d.foloseste_model
    )


def _intrare(db: Session, tenant: uuid.UUID, e: Exemplu, la: dt.datetime) -> Intrare:
    return Intrare(
        livrabil=SituatieLivrabil(
            id=new_id(), tenant_id=tenant, tip=e.tip, canal=e.canal, versiune=1, runda=0
        ),
        continut=Continut(
            versiune=1, text=e.text, campuri=dict(e.campuri), active=tuple(e.active), autor="banc"
        ),
        la=la,
        db=db,
        judecatori=False,
        v4=False,
    )


def _severitate(verdicte: list[Verdict]) -> str | None:
    esecuri = [v for v in verdicte if v.blocheaza]
    if not esecuri:
        return None
    return "critica" if any(v.severitate is Severitate.CRITICA for v in esecuri) else "majora"


def ruleaza_aur(db: Session, tenant: uuid.UUID, e: Exemplu, la: dt.datetime) -> RezultatExemplu:
    pasi = [p for p in _pasi(e) if p.definitie.cod == e.validator]
    asteptat = scoruri.clasa(e.asteptat == "esec", e.severitate)
    if not pasi:  # validatorul nu se aplică acestui tip / canal: nu produce verdict, deci nu blochează
        return RezultatExemplu(e.id, e.set, e.validator, asteptat, "trece", nu_se_aplica=True)
    verdicte, _ = cascada.ruleaza_pasii(pasi, _intrare(db, tenant, e, la))
    sev = _severitate(verdicte)
    return RezultatExemplu(
        e.id,
        e.set,
        e.validator,
        asteptat,
        scoruri.clasa(sev is not None, sev),
        blocat_de=sorted({v.validator for v in verdicte if v.blocheaza}),
        avertismente=sum(1 for v in verdicte if v.rezultat.value == "avertisment"),
    )


def ruleaza_cascada(db: Session, tenant: uuid.UUID, e: Exemplu, la: dt.datetime) -> RezultatExemplu:
    pasi = _pasi(e)
    if not pasi:
        return RezultatExemplu(e.id, e.set, e.validator, "blocat", "trece", nu_se_aplica=True)
    ev = cascada.evalueaza(pasi, _intrare(db, tenant, e, la), prag=get_settings().validare_prag_avertismente)
    blocat = ev.agregat.decizie is not Decizie.TRECE
    return RezultatExemplu(
        e.id,
        e.set,
        e.validator,
        "blocat" if e.tip_set == "rele" else "trece",
        "blocat" if blocat else "trece",
        blocat_de=sorted({v.validator for v in ev.verdicte if v.blocheaza}),
        avertismente=sum(1 for v in ev.verdicte if v.rezultat.value == "avertisment"),
        decizie=ev.agregat.decizie.value,
    )


def _grupate(seturi: Seturi) -> dict[str, list[Exemplu]]:
    grup: dict[str, list[Exemplu]] = defaultdict(list)
    for validator in seturi.aur:
        for e in seturi.toate_aur(validator):
            grup[e.ctx].append(e)
    for e in seturi.promovate:
        if e.validator not in seturi.aur:
            grup[e.ctx].append(e)
    for e in (*seturi.rele, *seturi.bune):
        grup[e.ctx].append(e)
    return grup


def ruleaza(seturi: Seturi) -> dict[str, Any]:
    """Rulează seturile și întoarce scorurile (JSON). Nu scrie nimic în bază."""
    start = time.monotonic()
    rezultate: list[RezultatExemplu] = []
    grup = _grupate(seturi)
    with sesiune_anulata(ContextDb(agency=True)) as db:
        om = creeaza_utilizator(
            db,
            email=f"banc-{new_id()}@exemplu.test",
            parola=PAROLA_PROBA,
            nume_afisat="Banc de evaluare",
            rol=Rol.PROPRIETAR,
            tenant_id=None,
            actor=Actor.cli(),
        ).id
        clienti: dict[str, uuid.UUID] = {}
        for ctx_id in sorted(
            grup
        ):  # scop de agenție: clientul de probă și contextul lui, prin API-urile aplicației
            clienti[ctx_id] = creeaza_client(db, f"Banc {ctx_id}", actor=Actor.cli()).id
            construieste(db, clienti[ctx_id], om, seturi.la, seturi.contexte[ctx_id])
        db.flush()
        for ctx_id in sorted(
            grup
        ):  # validarea: DOAR în contextul clientului (RLS ca în producție), apoi anulată
            tenant = clienti[ctx_id]
            with restrans_la_client(db, tenant, om):
                for e in grup[ctx_id]:
                    with db.begin_nested():
                        if e.tip_set in ("aur", "promovat"):
                            rezultate.append(ruleaza_aur(db, tenant, e, seturi.la))
                        else:
                            rezultate.append(ruleaza_cascada(db, tenant, e, seturi.la))
    return calculeaza(seturi, rezultate, durata_ms=int((time.monotonic() - start) * 1000))


def calculeaza(seturi: Seturi, rezultate: list[RezultatExemplu], *, durata_ms: int = 0) -> dict[str, Any]:
    """Scorurile din rezultatele pe exemple (nucleu fără bază)."""
    pe_validator: dict[str, Any] = {}
    for g in sorted({r.validator for r in rezultate if r.set.split(":")[0] in ("aur", "promovat")}):
        rs = [r for r in rezultate if r.set.split(":")[0] in ("aur", "promovat") and r.validator == g]
        perechi = [(r.asteptat, r.prezis) for r in rs]
        c = scoruri.confuzie((a != "trece", p != "trece") for a, p in perechi)
        pe_validator[g] = {
            "exemple": len(rs),
            "promovate": sum(1 for r in rs if r.set.startswith("promovat")),
            **c.json(),
            "matrice": scoruri.matrice(perechi),
            "acord_severitate": scoruri.acord_severitate(perechi),
            "gresite": [
                {"id": r.id, "asteptat": r.asteptat, "prezis": r.prezis} for r in rs if r.asteptat != r.prezis
            ],
            "nu_se_aplica": [r.id for r in rs if r.nu_se_aplica],
        }
    rele = [r for r in rezultate if r.set == "rele"]
    bune = [r for r in rezultate if r.set == "bune"]
    tinta = {e.id: e.validator for e in seturi.rele}
    defect = {e.id: e.defect for e in seturi.rele}
    rele_pe: dict[str, dict[str, Any]] = {}
    for r in rele:
        t = tinta[r.id]
        d = rele_pe.setdefault(t, {"total": 0, "blocate": 0, "prinse_de_tinta": 0, "scapate": []})
        d["total"] += 1
        d["blocate"] += r.prezis == "blocat"
        d["prinse_de_tinta"] += t in r.blocat_de
        if r.prezis != "blocat":
            d["scapate"].append({"id": r.id, "defect": defect[r.id]})
    for d in rele_pe.values():
        d["rata_blocare"] = scoruri.rata(d["blocate"], d["total"])
        d["rata_prinse_de_tinta"] = scoruri.rata(d["prinse_de_tinta"], d["total"])
    bune_pe: dict[str, int] = defaultdict(int)
    for r in bune:
        if r.prezis == "blocat":
            for v in r.blocat_de or ["?"]:
                bune_pe[v] += 1
    p = scoruri.poarta(
        len(rele), sum(r.prezis == "blocat" for r in rele), len(bune), sum(r.prezis == "blocat" for r in bune)
    )
    return {
        "la": seturi.la.isoformat(),
        "amprenta_seturi": seturi.amprenta,
        "exemple": len(rezultate),
        "omise": omise(),
        "durata_ms": durata_ms,
        "validatori": pe_validator,
        "rele": {
            "total": len(rele),
            "blocate": p.rele_blocate,
            "rata_blocare": p.rata_blocare,
            "prinse_de_validatorul_tinta": sum(d["prinse_de_tinta"] for d in rele_pe.values()),
            "pe_validator": dict(sorted(rele_pe.items())),
        },
        "bune": {
            "total": len(bune),
            "respinse": p.bune_respinse,
            "rata_respingere": p.rata_respingere,
            "respinse_de": dict(sorted(bune_pe.items())),
            "respinse_ids": [{"id": r.id, "validatori": r.blocat_de} for r in bune if r.prezis == "blocat"],
        },
        "poarta": p.json(),
    }
