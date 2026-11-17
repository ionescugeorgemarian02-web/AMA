"""Consiliul (F13.7, docs/07 §7.6): dosarul, importul deciziei, bugetul de apeluri, modul de conectare.

Modul ales (D-012): **manual asistat**. Platforma pregătește dosarul (cifre, context, opțiuni cu acțiunile
lor, întrebări precise și formatul exact al răspunsului); omul îl deschide în Claude, iar răspunsul se lipește
înapoi în panou. Importul validează decizia (o opțiune din dosar, motive, condiții, ce se măsoară), scrie
înregistrarea de decizie și transformă acțiunile opțiunii în propuneri `consiliu`, aprobate de omul care a
importat (trec prin gardian și executor). Modul **API** (Claude prin gateway, cu credit lunar) e construit în
spatele aceleiași uși (`intreaba_api`); acolo propunerile așteaptă omul. # NEVERIFICAT: profilul real al
Consiliului (T4, Claude) și creditul lunar se configurează la migrare.

Bugetul: cel mult `AMA_RECLAME_CONSILIU_PLAFON_LUNAR` dosare pe lună (implicit 8); peste el dosarul se amână,
iar sarcina rămâne la Strateg (T3).
"""

import datetime as dt
import json
import re
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import gateway
from app.config import get_settings
from app.operare import audit
from app.operare.motor import Prioritate
from app.reclame import prompturi, propuneri, rezultate, strateg
from app.reclame.modele import Campanie, ContReclame, DecizieReclame, DosarConsiliu

REFERINTA_PROMPT = "reclame.consiliu@1"
ZILE_DOSAR = 30


class DecizieConsiliu(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alegere: str = Field(min_length=2, max_length=80)
    motive: list[str] = Field(min_length=1, max_length=5)
    conditii: list[str] = Field(default_factory=list, max_length=5)
    masuram: list[str] = Field(min_length=1, max_length=5)


class DecizieConsiliuApi(gateway.Iesire):
    decizie: DecizieConsiliu


class DosarRefuzat(ValueError):
    pass


def _lei(bani: int | None) -> str:
    return "–" if bani is None else f"{bani / 100:.2f} lei"


def optiuni(campanii: list[Campanie]) -> list[dict[str, Any]]:
    """Opțiunile dosarului, fiecare cu ieșirea și acțiunile ei (Consiliul alege, nu inventează acțiuni)."""
    out: list[dict[str, Any]] = [
        {"id": "continua", "iesire": "continua", "text": "Continuăm fără schimbări.", "actiuni": []}
    ]
    for k, c in enumerate(campanii, 1):
        if c.stare == "activa":
            out.append(
                {
                    "id": f"opreste-{k}",
                    "iesire": "opreste",
                    "text": f"Oprim campania „{c.nume}”.",
                    "actiuni": [{"campanie_id": str(c.id), "tip": "stare", "dupa": {"stare": "pauza"}}],
                }
            )
        elif c.stare == "in_pauza":
            out.append(
                {
                    "id": f"porneste-{k}",
                    "iesire": "continua",
                    "text": f"Repornim campania „{c.nume}”.",
                    "actiuni": [{"campanie_id": str(c.id), "tip": "stare", "dupa": {"stare": "activa"}}],
                }
            )
    out.append(
        {
            "id": "pivoteaza",
            "iesire": "pivoteaza",
            "actiuni": [],
            "text": "Pivotăm unghiul: testăm una dintre ipotezele Strategului pe 20% din buget.",
        }
    )
    return out


def scrie_dosar(
    db: Session, cont: ContReclame, subiect: str, motiv_apel: str, acum: dt.datetime
) -> tuple[str, list[dict[str, Any]]]:
    azi = acum.date()
    de_la = azi - dt.timedelta(days=ZILE_DOSAR)
    campanii = list(
        db.execute(select(Campanie).where(Campanie.cont_id == cont.id).order_by(Campanie.nume)).scalars()
    )
    opt = optiuni(campanii)
    r = [
        f"# Dosar de Consiliu: {subiect}",
        "",
        f"Contul: {cont.nume} ({cont.platforma}). De ce te întrebăm: {motiv_apel}",
        "",
        f"## Cifre, {de_la} – {azi} (din managerul de reclame)",
        "",
    ]
    for c in campanii:
        t = rezultate.totaluri(db, cont.id, de_la, azi, obiect_extern=c.id_extern or "-")
        r.append(
            f"- {c.nume} ({c.stare}, {_lei(c.buget_zilnic_bani)}/zi): cheltuit {_lei(t.cheltuiala_bani)}, "
            f"{t.clicuri} clicuri, {t.rezultate} rezultate, cost pe rezultat {_lei(t.cost_pe_rezultat_bani)}"
        )
    r += [
        "",
        f"Plafoane: {_lei(cont.plafon_zilnic_bani)}/zi, {_lei(cont.plafon_lunar_bani)}/lună.",
        "",
        "## Ultimele decizii ale Strategului",
        "",
    ]
    for d in strateg.ale_contului(db, cont.id, limita=5):
        r.append(f"- {d.pana_la}: {d.iesire} — {d.motiv}")
        r += [f"  - ipoteză: {a.get('ipoteza')}" for a in d.alternative]
    r += ["", "## Opțiuni", ""] + [f"- `{o['id']}`: {o['text']}" for o in opt]
    r += [
        "",
        "## Întrebări",
        "",
        "1. Care opțiune o alegi și de ce?",
        "2. În ce condiții ne răzgândim?",
        "3. Ce măsurăm ca să știm că a fost bine?",
        "",
        "## Formatul răspunsului",
        "",
        "Răspunde cu un singur bloc JSON, exact așa:",
        "",
        '```json\n{"alegere": "<id-ul opțiunii>", "motive": ["…"], "conditii": ["…"], "masuram": ["…"]}\n```',
    ]
    return "\n".join(r), opt


def deschide(
    db: Session, cont_id: uuid.UUID, *, subiect: str, motiv_apel: str, acum: dt.datetime | None = None
) -> DosarConsiliu:
    """Pregătește dosarul. Peste plafonul lunar, dosarul se scrie „amânat” (sarcina rămâne la Strateg)."""
    acum = acum or dt.datetime.now(dt.UTC)
    cont = db.get(ContReclame, cont_id)
    if cont is None:
        raise DosarRefuzat("cont inexistent")
    luna = acum.date().replace(day=1)
    folosite = db.execute(
        select(func.count()).where(DosarConsiliu.luna == luna, DosarConsiliu.stare.in_(("deschis", "decis")))
    ).scalar_one()
    s = get_settings()
    continut, opt = scrie_dosar(db, cont, subiect, motiv_apel, acum)
    d = DosarConsiliu(
        tenant_id=cont.tenant_id,
        cont_id=cont.id,
        subiect=subiect[:200],
        motiv_apel=motiv_apel[:500],
        continut=continut,
        optiuni=opt,
        luna=luna,
        mod="api" if s.reclame_consiliu_mod == "api" else "manual",
        stare="amanat" if folosite >= s.reclame_consiliu_plafon_lunar else "deschis",
    )
    db.add(d)
    db.flush()
    audit.record(
        db,
        "reclame.dosar_consiliu",
        obiect_tip="reclame_dosar",
        obiect_id=d.id,
        tenant_id=cont.tenant_id,
        actor_tip="sistem",
        detalii={"stare": d.stare, "folosite_luna": int(folosite)},
    )
    return d


def extrage(text: str) -> DecizieConsiliu:
    """Decizia din răspunsul lipit (blocul ```json``` sau primul obiect JSON din text)."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S) or re.search(r"(\{.*\})", text, re.S)
    if not m:
        raise DosarRefuzat("răspunsul nu conține blocul JSON cerut")
    try:
        return DecizieConsiliu.model_validate(json.loads(m.group(1)))
    except (ValueError, ValidationError) as exc:
        raise DosarRefuzat(f"decizia nu are forma cerută: {str(exc)[:200]}") from None


def aplica(
    db: Session,
    dosar_id: uuid.UUID,
    decizie: DecizieConsiliu,
    *,
    utilizator_id: uuid.UUID | None,
    acum: dt.datetime | None = None,
) -> DecizieReclame:
    """Scrie înregistrarea de decizie și propunerile opțiunii alese. Importul de către om le aprobă."""
    acum = acum or dt.datetime.now(dt.UTC)
    d = db.get(DosarConsiliu, dosar_id)
    if d is None or d.stare != "deschis":
        raise DosarRefuzat("dosarul nu așteaptă o decizie")
    opt = next((o for o in d.optiuni if o["id"] == decizie.alegere), None)
    if opt is None:
        raise DosarRefuzat(f"opțiunea „{decizie.alegere}” nu e în dosar")
    azi = acum.date()
    ids: list[str] = []
    for a in opt["actiuni"]:
        p = propuneri.propune(
            db,
            uuid.UUID(a["campanie_id"]),
            a["tip"],
            dict(a["dupa"]),
            sursa="consiliu",
            motiv=f"Consiliul: {decizie.motive[0]}"[:500],
            utilizator_id=utilizator_id,
            acum=acum,
        )
        if p.stare == "propusa" and utilizator_id is not None:
            propuneri.aproba(db, p.id, utilizator_id=utilizator_id)
        ids.append(str(p.id))
    rec = DecizieReclame(
        tenant_id=d.tenant_id,
        cont_id=d.cont_id,
        sursa="consiliu",
        de_la=azi - dt.timedelta(days=ZILE_DOSAR),
        pana_la=azi,
        observat={"dosar": str(d.id), "conditii": decizie.conditii},
        iesire=opt["iesire"],
        motiv=f"{opt['text']} {' '.join(decizie.motive)}"[:1000],
        asteptat="; ".join(decizie.masuram)[:500],
        verificare_la=azi + dt.timedelta(days=ZILE_DOSAR),
        propuneri=ids,
        model="consiliu:" + d.mod,
    )
    db.add(rec)
    db.flush()
    d.stare, d.decizie, d.decizie_id, d.decis_de, d.decis_la = (
        "decis",
        decizie.model_dump(),
        rec.id,
        utilizator_id,
        acum,
    )
    audit.record(
        db,
        "reclame.decizie",
        obiect_tip="reclame_decizie",
        obiect_id=rec.id,
        tenant_id=d.tenant_id,
        utilizator_id=utilizator_id,
        actor_tip=None if utilizator_id else "sistem",
        detalii={"iesire": rec.iesire, "sursa": "consiliu", "alegere": decizie.alegere},
    )
    return rec


def importa(db: Session, dosar_id: uuid.UUID, text: str, *, utilizator_id: uuid.UUID) -> DecizieReclame:
    """Modul manual asistat: răspunsul copiat din Claude, lipit de om în panou."""
    return aplica(db, dosar_id, extrage(text), utilizator_id=utilizator_id)


def intreaba_api(db: Session, dosar_id: uuid.UUID) -> DecizieReclame:
    """Modul API: Claude prin gateway (profilul Consiliului). Propunerile rezultate așteaptă omul."""
    d = db.get(DosarConsiliu, dosar_id)
    if d is None or d.stare != "deschis":
        raise DosarRefuzat("dosarul nu așteaptă o decizie")
    prompturi.asigura()
    r = gateway.apeleaza(
        db,
        prompt=REFERINTA_PROMPT,
        schema=DecizieConsiliuApi,
        tenant_id=d.tenant_id,
        componenta="reclame.consiliu",
        variabile={"dosar": d.continut},
        prioritate=Prioritate.P2,
        max_tokeni=1500,
    )
    if not isinstance(r.iesire, DecizieConsiliuApi):
        raise DosarRefuzat("ieșirea nu respectă schema")
    return aplica(db, d.id, r.iesire.decizie, utilizator_id=None)


def dosare(db: Session, *, limita: int = 50) -> list[DosarConsiliu]:
    return list(
        db.execute(select(DosarConsiliu).order_by(DosarConsiliu.creat_la.desc()).limit(limita)).scalars()
    )
