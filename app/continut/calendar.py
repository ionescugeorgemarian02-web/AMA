"""Strategul de conținut și calendarul (F6.1, D3, docs/05 „pilonii, formatele, frecvența și calendarul
lunar”).

Două părți, după regula 13.1 („variante, apoi alegere”, „schemă strictă”):
1. modelul (profilul `strategie`, care se AMÂNĂ, nu se degradează) propune DOAR conținutul: pilonii cu
ponderi, formatele pe
   canal cu frecvența săptămânală și o listă de idei pe piloni, din strategia APROBATĂ (pachetul de context cu
   secțiunile
   `strategie`, `brief` și `public`);
2. nucleul determinist (`planifica`) așază sloturile pe fereastra de zile: aceeași propunere → același
calendar. Pilonii se
   distribuie după pondere (cele mai mari resturi), sloturile unui canal se răspândesc uniform de la prima la
   ultima zi, ora vine din `ORE_CANAL` [I].

Calendarul se salvează `propus`, cu versiunea strategiei din care pleacă; îl aprobă sau îl respinge un OM. La
aprobare,
fiecare slot devine un livrabil `planificat` (componenta D3), cu termenul = slotul. Un calendar aprobat nu se
mai schimbă.
"""

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import creier, gateway, onboarding, productie
from app.continut import prompturi
from app.continut.modele import Calendar, IntrareCalendar
from app.creier import context
from app.ids import new_id
from app.operare import audit
from app.operare.motor import Prioritate

REFERINTA_PROMPT = "continut.calendar@1"
COMPONENTA = "D3"
ZILE_IMPLICIT = 30
BUGET_TOKENI = 5000
FUS = ZoneInfo("Europe/Bucharest")
# Canalele pe care produce faza F6 (text și scripturi). Ora de publicare recomandată pe canal: valori de
# pornire [I],
# de înlocuit cu memoria de performanță (N4, F11).
CANALE_CONTINUT = ("facebook", "instagram", "linkedin", "tiktok")
ORE_CANAL = {"facebook": (18, 0), "instagram": (19, 0), "linkedin": (9, 0), "tiktok": (20, 0)}
TIPURI = ("postare", "script_video_scurt")
MAXIM_PE_ZI = 3  # [I] mai multe sloturi pe zi pe un client nu se pot aproba în rutina zilnică (22.10)

Canal = Literal["facebook", "instagram", "linkedin", "tiktok"]
Tip = Literal["postare", "script_video_scurt"]


class Pilon(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nume: str = Field(min_length=2, max_length=80)
    descriere: str = Field(min_length=10, max_length=300)
    pondere: int = Field(ge=1, le=100)


class FormatCanal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canal: Canal
    tip: Tip
    pe_saptamana: int = Field(ge=1, le=7)


class Idee(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pilon: str = Field(min_length=2, max_length=80)
    subiect: str = Field(min_length=5, max_length=300)
    unghi: str = Field(default="", max_length=300)


class ContinutCalendar(BaseModel):
    """Ce propune strategul. Nimic nu are valoare implicită în afară de unghi."""

    model_config = ConfigDict(extra="forbid")
    piloni: list[Pilon] = Field(min_length=3, max_length=5)
    formate: list[FormatCanal] = Field(min_length=1, max_length=8)
    idei: list[Idee] = Field(min_length=6, max_length=40)


class PropunereCalendar(gateway.Iesire):
    calendar: ContinutCalendar


@dataclass(frozen=True)
class Slot:
    nr: int
    slot_la: dt.datetime
    canal: str
    tip: str
    pilon: str
    subiect: str
    unghi: str


class CalendarInvalid(creier.RegulaCreier):
    def __init__(self, probleme: list[str]) -> None:
        super().__init__("; ".join(probleme))
        self.probleme = probleme


class EroareCalendar(RuntimeError):
    """Decizie refuzată (stare greșită, fără om, motiv lipsă)."""


# --- nucleul determinist
# ------------------------------------------------------------------------------------------


def canale_din_strategie(strategie: dict[str, Any]) -> list[str]:
    """Canalele de conținut pe care le folosește strategia aprobată (în ordinea din `CANALE_CONTINUT`)."""
    pasi = [*strategie.get("plan_30_zile", []), *strategie.get("plan_90_zile", [])]
    folosite = {str(p.get("canal")) for p in pasi}
    return [c for c in CANALE_CONTINUT if c in folosite]


def _distributie(ponderi: Sequence[tuple[str, int]], total: int) -> list[str]:
    """Secvența de piloni pentru `total` sloturi: cote după pondere (cele mai mari resturi),
    apoi intercalate."""
    suma = sum(p for _, p in ponderi)
    cote = [(n, total * p / suma) for n, p in ponderi]
    intregi = {n: int(c) for n, c in cote}
    rest = total - sum(intregi.values())
    for n, _ in sorted(cote, key=lambda x: (-(x[1] - int(x[1])), x[0]))[:rest]:
        intregi[n] += 1
    # intercalare: la fiecare pas, pilonul cel mai „rămas în urmă” față de cota lui
    secventa: list[str] = []
    folosit = dict.fromkeys(intregi, 0)
    for _ in range(total):
        n = min(
            (x for x in intregi if folosit[x] < intregi[x]),
            key=lambda x: ((folosit[x] + 1) / intregi[x], x),
        )
        folosit[n] += 1
        secventa.append(n)
    return secventa


def planifica(c: ContinutCalendar, inceput: dt.date, zile: int = ZILE_IMPLICIT) -> list[Slot]:
    """Sloturile calendarului. Determinist: aceeași propunere și același început → același calendar."""
    brute: list[tuple[dt.datetime, str, str]] = []
    for f in c.formate:
        n = max(1, round(f.pe_saptamana * zile / 7))
        ora, minut = ORE_CANAL[f.canal]
        for i in range(n):
            zi = inceput + dt.timedelta(days=round(i * (zile - 1) / (n - 1)) if n > 1 else 0)
            local = dt.datetime.combine(zi, dt.time(ora, minut), tzinfo=FUS)
            brute.append((local.astimezone(dt.UTC), f.canal, f.tip))
    brute.sort(key=lambda x: (x[0], x[1], x[2]))
    piloni = _distributie([(p.nume, p.pondere) for p in c.piloni], len(brute))
    idei: dict[str, list[Idee]] = {}
    for idee in c.idei:
        idei.setdefault(idee.pilon, []).append(idee)
    folosite = dict.fromkeys(idei, 0)
    sloturi = []
    for nr, ((la, canal, tip), pilon) in enumerate(zip(brute, piloni, strict=True), start=1):
        lista = idei.get(pilon) or []
        if lista:
            idee = lista[folosite[pilon] % len(lista)]
            folosite[pilon] += 1
            subiect, unghi = idee.subiect, idee.unghi
        else:  # semnalat de `probleme_calendar`; aici doar nu cade
            subiect, unghi = f"Pilonul {pilon}", ""
        sloturi.append(Slot(nr, la, canal, tip, pilon, subiect, unghi))
    return sloturi


def probleme_calendar(
    c: dict[str, Any], *, canale_permise: Sequence[str], inceput: dt.date, zile: int = ZILE_IMPLICIT
) -> list[str]:
    """Nucleu pur: problemele unei propuneri (schema, canalele strategiei, pilonii, acoperirea ferestrei)."""
    try:
        p = ContinutCalendar.model_validate(c)
    except ValidationError as exc:
        return [f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()[:8]]
    probleme: list[str] = []
    nume = [x.nume for x in p.piloni]
    if len(set(nume)) != len(nume):
        probleme.append("pilonii trebuie să aibă nume diferite")
    for f in p.formate:
        if f.canal not in canale_permise:
            probleme.append(f"canalul {f.canal} nu este în strategia aprobată")
    if len({(f.canal, f.tip) for f in p.formate}) != len(p.formate):
        probleme.append("un format (canal și tip) apare de două ori")
    for idee in p.idei:
        if idee.pilon not in nume:
            probleme.append(f"ideea „{idee.subiect[:40]}” are un pilon necunoscut ({idee.pilon})")
    for n in nume:
        if not any(i.pilon == n for i in p.idei):
            probleme.append(f"pilonul {n} nu are nicio idee")
    if probleme:
        return probleme
    sloturi = planifica(p, inceput, zile)
    pe_zi: dict[dt.date, int] = {}
    for s in sloturi:
        z = s.slot_la.astimezone(FUS).date()
        pe_zi[z] = pe_zi.get(z, 0) + 1
    if max(pe_zi.values()) > MAXIM_PE_ZI:
        probleme.append(f"mai mult de {MAXIM_PE_ZI} sloturi într-o zi")
    zile_folosite = sorted(pe_zi)
    if zile_folosite[0] > inceput + dt.timedelta(days=6) or zile_folosite[-1] < inceput + dt.timedelta(
        days=zile - 7
    ):
        probleme.append(
            f"calendarul nu acoperă toate cele {zile} de zile (prima sau ultima săptămână e goală)"
        )
    if {s.pilon for s in sloturi} != set(nume):
        probleme.append("fiecare pilon trebuie să apară în calendar")
    return probleme


# --- serviciile
# -------------------------------------------------------------------------------------------------


def strategia_aprobata(db: Session, tenant_id: uuid.UUID) -> tuple[uuid.UUID, Any]:
    """Intrarea și versiunea APROBATĂ a strategiei pe 90 de zile; `RegulaCreier` dacă lipsește."""
    for intrare, aprobata in onboarding.strategie.strategii(db, tenant_id):
        if aprobata is not None:
            return intrare.id, aprobata
    raise creier.RegulaCreier("calendarul cere o strategie pe 90 de zile aprobată")


def propune(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    utilizator_id: uuid.UUID | None,
    inceput: dt.date,
    zile: int = ZILE_IMPLICIT,
) -> Calendar:
    """Calendarul propus (cu sloturile lui) din strategia aprobată. Ridică `gateway.Amanat` (nu degradează),
    `RegulaCreier` (strategie lipsă) sau `CalendarInvalid`."""
    strategie_id, strategie = strategia_aprobata(db, tenant_id)
    canale = canale_din_strategie(strategie.continut)
    if not canale:
        raise creier.RegulaCreier(
            "strategia aprobată nu are niciun canal de conținut (" + ", ".join(CANALE_CONTINUT) + ")"
        )
    # Relevanța faptelor este lexicală: întrebarea poartă ipoteza și pașii strategiei, ca faptele despre ele
    # să intre.
    s = strategie.continut
    pasi = "; ".join(
        str(p.get("actiune", "")) for p in [*s.get("plan_30_zile", []), *s.get("plan_90_zile", [])]
    )
    intrebare = f"Calendar de conținut lunar pe {', '.join(canale)}. {s.get('ipoteza', '')} {pasi}"[:1900]
    pachet = context.construieste(
        db,
        tenant_id=tenant_id,
        tip_sarcina="calendar_continut",
        intrebare=intrebare,
        buget_tokeni=BUGET_TOKENI,
        utilizator_id=utilizator_id,
        la=dt.datetime.now(dt.UTC),
        sectiuni_extra=("strategie", "brief", "public"),
    )
    lipsa = [x for x in pachet.lipsuri if x in ("ghid_brand", "strategie", "brief")]
    if lipsa:
        raise creier.RegulaCreier("calendarul cere, aprobate: " + ", ".join(lipsa))
    prompturi.asigura()
    r = gateway.apeleaza(
        db,
        prompt=REFERINTA_PROMPT,
        schema=PropunereCalendar,
        tenant_id=tenant_id,
        componenta="continut.calendar",
        variabile={"context": context.ca_text(pachet), "canale": ", ".join(canale), "zile": str(zile)},
        prioritate=Prioritate.P1,
        max_tokeni=4000,
    )
    if not isinstance(r.iesire, PropunereCalendar):
        raise TypeError("ieșirea nu respectă schema promptului")
    continut = r.iesire.calendar.model_dump(mode="json")
    probleme = probleme_calendar(continut, canale_permise=canale, inceput=inceput, zile=zile)
    if probleme:
        raise CalendarInvalid(probleme)
    cal = Calendar(
        id=new_id(),
        tenant_id=tenant_id,
        inceput=inceput,
        zile=zile,
        strategie_intrare_id=strategie_id,
        strategie_versiune=strategie.nr,
        propunere=continut,
        pachet_id=pachet.id,
        model=r.model,
        creat_de=utilizator_id,
    )
    db.add(cal)
    db.flush()
    for s in planifica(ContinutCalendar.model_validate(continut), inceput, zile):
        db.add(
            IntrareCalendar(
                id=new_id(),
                tenant_id=tenant_id,
                calendar_id=cal.id,
                nr=s.nr,
                slot_la=s.slot_la,
                canal=s.canal,
                tip=s.tip,
                pilon=s.pilon,
                subiect=s.subiect,
                unghi=s.unghi,
            )
        )
    db.flush()
    audit.record(
        db,
        "continut.calendar_propus",
        obiect_tip="calendar",
        obiect_id=cal.id,
        utilizator_id=utilizator_id,
        tenant_id=tenant_id,
        actor_tip=None if utilizator_id else "sistem",
        detalii={"inceput": inceput.isoformat(), "zile": zile, "strategie_versiune": strategie.nr},
    )
    return cal


def citeste(db: Session, calendar_id: uuid.UUID) -> Calendar | None:
    return db.get(Calendar, calendar_id)


def calendare(db: Session, tenant_id: uuid.UUID, *, limita: int = 12) -> list[Calendar]:
    return list(
        db.execute(
            select(Calendar)
            .where(Calendar.tenant_id == tenant_id)
            .order_by(Calendar.creat_la.desc())
            .limit(limita)
        ).scalars()
    )


def intrari(db: Session, calendar_id: uuid.UUID) -> list[IntrareCalendar]:
    return list(
        db.execute(
            select(IntrareCalendar)
            .where(IntrareCalendar.calendar_id == calendar_id)
            .order_by(IntrareCalendar.nr)
        ).scalars()
    )


def intrarea_livrabilului(db: Session, livrabil_id: uuid.UUID) -> IntrareCalendar | None:
    return db.execute(
        select(IntrareCalendar).where(IntrareCalendar.livrabil_id == livrabil_id)
    ).scalar_one_or_none()


def _blocheaza(db: Session, calendar_id: uuid.UUID) -> Calendar:
    cal = db.execute(
        select(Calendar).where(Calendar.id == calendar_id).with_for_update()
    ).scalar_one_or_none()
    if cal is None:
        raise EroareCalendar("calendarul nu există")
    if cal.stare != "propus":
        raise EroareCalendar(f"calendarul este „{cal.stare}”; se decide doar unul propus")
    return cal


def aproba(db: Session, calendar_id: uuid.UUID, *, utilizator_id: uuid.UUID) -> list[uuid.UUID]:
    """Aprobarea unui OM: fiecare slot devine un livrabil `planificat`. Celelalte propuneri ale clientului se
    înlocuiesc.
    Întoarce livrabilele create."""
    if utilizator_id is None:
        raise EroareCalendar("calendarul se aprobă doar de un om")
    cal = _blocheaza(db, calendar_id)
    _, strategie = strategia_aprobata(db, cal.tenant_id)
    if strategie.nr != cal.strategie_versiune or strategie.intrare_id != cal.strategie_intrare_id:
        raise EroareCalendar("strategia s-a schimbat de la propunere; cere un calendar nou")
    livrabile = []
    for i in intrari(db, cal.id):
        lv = productie.creeaza(
            db,
            tenant_id=cal.tenant_id,
            tip=i.tip,
            canal=i.canal,
            termen_la=i.slot_la,
            componenta=COMPONENTA,
            utilizator_id=utilizator_id,
        )
        i.livrabil_id = lv.id
        livrabile.append(lv.id)
    acum = dt.datetime.now(dt.UTC)
    cal.stare, cal.decis_de, cal.decis_la = "aprobat", utilizator_id, acum
    db.execute(
        update(Calendar)
        .where(Calendar.tenant_id == cal.tenant_id, Calendar.stare == "propus", Calendar.id != cal.id)
        .values(stare="inlocuit")
    )
    db.flush()
    audit.record(
        db,
        "continut.calendar_aprobat",
        obiect_tip="calendar",
        obiect_id=cal.id,
        utilizator_id=utilizator_id,
        tenant_id=cal.tenant_id,
        detalii={"livrabile": len(livrabile)},
    )
    return livrabile


def respinge(db: Session, calendar_id: uuid.UUID, *, utilizator_id: uuid.UUID, motiv: str) -> Calendar:
    motiv = motiv.strip()
    if len(motiv) < 3:
        raise EroareCalendar("respingerea cere un motiv (cel puțin 3 caractere)")
    cal = _blocheaza(db, calendar_id)
    cal.stare, cal.motiv, cal.decis_de, cal.decis_la = (
        "respins",
        motiv[:300],
        utilizator_id,
        dt.datetime.now(dt.UTC),
    )
    db.flush()
    audit.record(
        db,
        "continut.calendar_respins",
        obiect_tip="calendar",
        obiect_id=cal.id,
        utilizator_id=utilizator_id,
        tenant_id=cal.tenant_id,
        detalii={"motiv": motiv[:300]},
    )
    return cal
