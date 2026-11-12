"""Compunerea brieful din răspunsurile interviului și materialele colectate (F4.4), cu sursă pe fiecare câmp.

Un model (profilul `creatie`, prin gateway, schemă strictă) propune valoarea fiecărui câmp, cu sursa
(un răspuns
sau un pasaj) și citatul exact. Un verificator determinist (același ca la fapte:
`creier.citat_in_text`) respinge
orice câmp al cărui citat nu apare literal în sursa indicată sau a cărui sursă nu este una dintre cele oferite
modelului. Un câmp respins, lipsă, sau o compunere imposibilă (gateway-ul refuză / ieșire invalidă) cade pe
răspunsul clientului însuși, ca sursă (`raspuns`): brieful nu rămâne cu goluri din vina modelului.
`Amanat` NU se
înghite: fluxul durabil reprogramează.
"""

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app import cercetare, creier, gateway
from app.creier.compartimente import Compartiment, SursaTip
from app.onboarding import brief, interviu, prompturi, sesiuni
from app.onboarding.modele import IntrebareSesiune
from app.operare import audit
from app.operare.motor import Prioritate

REFERINTA_PROMPT = "onboarding.completeaza_brief@1"
CHEIE_BRIEF = "brief"
PASAJE_MAXIME = 8
CARACTERE_PASAJ = 700


class CampPropus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    camp: str = Field(max_length=40)
    valoare: str = Field(max_length=2500)
    sursa_tip: Literal["raspuns", "pasaj"]
    sursa_ref: str = Field(max_length=100)
    citat: str = Field(max_length=800)


class BriefPropus(gateway.Iesire):
    campuri: list[CampPropus] = Field(default_factory=list, max_length=20)


@dataclass
class Compunere:
    din_model: list[str] = field(default_factory=list)
    din_raspuns: list[str] = field(default_factory=list)
    respinse: list[dict[str, str]] = field(default_factory=list)
    probleme: list[str] = field(default_factory=list)


def verifica_camp(p: CampPropus, raspunsuri: dict[str, str], pasaje: dict[str, str]) -> str | None:
    """Motivul respingerii unui câmp propus, sau `None` (nucleu determinist, fără model). `raspunsuri` și
    `pasaje` sunt DOAR sursele oferite modelului (identificator → text)."""
    if p.camp not in brief.CAMPURI:
        return "camp_necunoscut"
    if not p.valoare.strip():
        return "valoare_goala"
    oferite = raspunsuri if p.sursa_tip == "raspuns" else pasaje
    if p.sursa_ref not in oferite:
        return "sursa_neoferita"
    if not creier.citat_in_text(p.citat, oferite[p.sursa_ref]):
        return "citat_negasit"
    return None


def _pasaje_pentru(
    db: Session, tenant_id: uuid.UUID, grupuri: dict[str, list[IntrebareSesiune]]
) -> dict[str, str]:
    """Pasaje din materialele REUTILIZABILE ale clientului, găsite prin căutarea hibridă după fiecare
    întrebare."""
    surse_ok = [s.id for s in cercetare.surse(db, tenant_id) if cercetare.STATUTE[s.statut].reutilizare_text]
    if not surse_ok:
        return {}
    gasite: dict[str, str] = {}
    for q in interviu.intrebari():
        if q.camp not in grupuri or len(gasite) >= PASAJE_MAXIME:
            continue
        try:
            r = creier.cauta(
                db, tenant_id=tenant_id, intrebare=f"{q.text} {grupuri[q.camp][0].raspuns or ''}"[:300],
                limita=2, surse=surse_ok,
            )  # fmt: skip
        except creier.CautareRefuzata:
            continue
        for x in r.rezultate:
            if len(gasite) < PASAJE_MAXIME:
                gasite.setdefault(str(x.pasaj_id), x.text)
    return gasite


def _din_raspuns(camp: str, rows: list[IntrebareSesiune]) -> dict[str, Any]:
    principal = rows[0]
    valoare = "\n".join((r.raspuns or "").strip() for r in rows)[:2500]
    return {
        "valoare": valoare,
        "surse": [{"tip": "raspuns", "ref": str(principal.id), "citat": (principal.raspuns or "")[:300]}],
    }


def compune(db: Session, sesiune_id: uuid.UUID, *, utilizator_id: uuid.UUID | None) -> Compunere:
    """Compune brieful și îl scrie pe sesiune (`brief_gata`). Interviul trebuie terminat. Ridică `Amanat`."""
    s = sesiuni.sesiune(db, sesiune_id)
    if s.stare == "trimis":
        raise sesiuni.SesiuneInchisa("brieful a fost deja trimis")
    p = sesiuni.progres(db, sesiune_id)
    if not p.terminat:
        raise sesiuni.EroareOnboarding("interviul nu e terminat: mai sunt întrebări fără răspuns")
    grupuri = sesiuni.raspunsuri_pe_camp(db, sesiune_id)
    raspunsuri = {str(r.id): r.raspuns or "" for rows in grupuri.values() for r in rows}
    pasaje = _pasaje_pentru(db, s.tenant_id, grupuri)
    rezultat = Compunere()
    propuse: dict[str, CampPropus] = {}
    prompturi.asigura()
    try:
        linii_r = "\n".join(f"[R:{r.id}] ({r.camp}) {r.raspuns}" for rows in grupuri.values() for r in rows)
        linii_p = (
            "\n".join(f"[P:{pid}] {t[:CARACTERE_PASAJ]}" for pid, t in pasaje.items())
            or "(niciun material colectat)"
        )
        r = gateway.apeleaza(
            db,
            prompt=REFERINTA_PROMPT,
            variabile={
                "raspunsuri": gateway.marcheaza_extern(linii_r, sursa="raspuns_client", max_caractere=50_000),
                "pasaje": gateway.marcheaza_extern(linii_p, sursa="pagina", max_caractere=20_000),
            },
            schema=BriefPropus,
            tenant_id=s.tenant_id,
            componenta="onboarding.completeaza_brief",
            prioritate=Prioritate.P2,
            max_tokeni=2500,
            demasca=True,
        )
        iesire = r.iesire
        if not isinstance(iesire, BriefPropus):
            raise TypeError("ieșirea nu respectă schema promptului")
        for c in iesire.campuri:
            motiv = verifica_camp(c, raspunsuri, pasaje)
            if motiv is None and c.camp not in propuse:
                propuse[c.camp] = c
            else:
                rezultat.respinse.append({"camp": c.camp, "motiv": motiv or "dublat"})
    except gateway.Amanat:
        raise
    except gateway.EroareGateway as exc:
        rezultat.respinse.append({"camp": "*", "motiv": f"gateway:{type(exc).__name__}"})
    continut: dict[str, Any] = {}
    for camp in brief.CAMPURI:
        rows = grupuri.get(camp)
        if camp in propuse:
            c = propuse[camp]
            continut[camp] = {
                "valoare": c.valoare.strip(),
                "surse": [{"tip": c.sursa_tip, "ref": c.sursa_ref, "citat": c.citat.strip()}],
            }
            rezultat.din_model.append(camp)
        elif rows:
            continut[camp] = _din_raspuns(camp, rows)
            rezultat.din_raspuns.append(camp)
    s.brief = brief.BriefClient.model_validate(continut).model_dump(mode="json")
    s.brief_probleme = brief.lipsuri(s.brief)
    s.stare = "brief_gata"
    s.amanat_pana = None
    s.actualizat_la = dt.datetime.now(dt.UTC)
    db.flush()
    rezultat.probleme = list(s.brief_probleme)
    audit.record(
        db, "onboarding.brief_compus", obiect_tip="onboarding_sesiune", obiect_id=s.id,
        utilizator_id=utilizator_id, tenant_id=s.tenant_id,
        detalii={"din_model": len(rezultat.din_model), "din_raspuns": len(rezultat.din_raspuns),
                 "respinse": len(rezultat.respinse), "probleme": len(rezultat.probleme)},
    )  # fmt: skip
    return rezultat


def seteaza_camp(
    db: Session, sesiune_id: uuid.UUID, camp: str, valoare: str, *, utilizator_id: uuid.UUID
) -> list[str]:
    """Un operator corectează valoarea unui câmp din ciorna brieful; sursele rămân și se adaugă el. Întoarce
    problemele de completitudine rămase."""
    s = sesiuni.sesiune(db, sesiune_id)
    if s.stare != "brief_gata" or s.brief is None:
        raise sesiuni.EroareOnboarding("brieful nu e în lucru")
    if camp not in brief.CAMPURI:
        raise sesiuni.EroareOnboarding(f"câmp necunoscut: {camp}")
    curent = dict(s.brief)
    vechi = curent.get(camp) or {"valoare": "", "surse": []}
    surse = [x for x in vechi.get("surse", []) if x.get("tip") != "operator"]
    surse.append({"tip": "operator", "ref": str(utilizator_id), "citat": None})
    curent[camp] = {"valoare": valoare.strip(), "surse": surse}
    s.brief = brief.BriefClient.model_validate(curent).model_dump(mode="json")
    s.brief_probleme = brief.lipsuri(s.brief)
    s.actualizat_la = dt.datetime.now(dt.UTC)
    db.flush()
    audit.record(
        db, "onboarding.camp_editat", obiect_tip="onboarding_sesiune", obiect_id=s.id,
        utilizator_id=utilizator_id, tenant_id=s.tenant_id, detalii={"camp": camp},
    )  # fmt: skip
    return list(s.brief_probleme)


def trimite_spre_aprobare(
    db: Session, sesiune_id: uuid.UUID, *, utilizator_id: uuid.UUID
) -> tuple[uuid.UUID, int]:
    """Brieful devine intrare în Creier (compartimentul `brief`), versiune `propus`. Un brief cu câmpuri goale
    nu trece: `creier.PoartaInchisa` cu problemele. Întoarce (intrare, versiune)."""
    s = sesiuni.sesiune(db, sesiune_id)
    if s.stare != "brief_gata" or s.brief is None:
        raise sesiuni.EroareOnboarding("brieful nu e compus")
    probleme = brief.lipsuri(s.brief)
    if probleme:  # înainte de orice scriere: un brief cu goluri nu creează nici măcar intrarea
        raise creier.PoartaInchisa(probleme)
    sursa = creier.Sursa(SursaTip.DECLARATIE_CLIENT, detalii={"sesiune": str(s.id)})
    existenta = creier.gaseste_intrare(
        db, tenant_id=s.tenant_id, compartiment=Compartiment.BRIEF, cheie=CHEIE_BRIEF
    )
    if existenta is None:
        intrare, v = creier.creeaza_intrare(
            db, tenant_id=s.tenant_id, compartiment=Compartiment.BRIEF, cheie=CHEIE_BRIEF,
            continut=s.brief, sursa=sursa, utilizator_id=utilizator_id,
        )  # fmt: skip
    else:
        intrare = existenta
        v = creier.propune_schimbare(
            db, existenta.id, continut=s.brief, sursa=sursa, utilizator_id=utilizator_id
        )
    s.stare, s.brief_intrare_id = "trimis", intrare.id
    s.actualizat_la = dt.datetime.now(dt.UTC)
    db.flush()
    return intrare.id, v.nr


creier.inregistreaza_schema(Compartiment.BRIEF, brief.BriefClient)
creier.inregistreaza_randare(Compartiment.BRIEF, brief.text_pentru_prompt)
creier.inregistreaza_poarta(Compartiment.BRIEF, lambda _db, _t, c: brief.lipsuri(c))
_ = SursaTip


def brief_aprobat(db: Session, tenant_id: uuid.UUID) -> tuple[dict[str, Any], int]:
    """Brieful aprobat acum (conținut, versiune). Fără el nu se construiesc ghidul, publicul, harta
    pieței sau strategia."""
    i = creier.gaseste_intrare(db, tenant_id=tenant_id, compartiment=Compartiment.BRIEF, cheie=CHEIE_BRIEF)
    v = creier.versiune_aprobata(db, i.id) if i else None
    if v is None:
        raise creier.RegulaCreier("brieful nu este aprobat: aprobă brieful înainte de pasul următor")
    return v.continut, v.nr
