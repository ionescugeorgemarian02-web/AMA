"""Calificare și scor (F12.4, docs/17 §17.5): patru întrebări, reguli simple, trei grupe.

- **Asistentul se prezintă ca asistent AI** (`INTRODUCERE`) și spune că se poate vorbi oricând cu un om.
- **Reguli, nu model** (componentă D): nișa potrivită e condiția de intrare; bugetul, termenul și puterea de
  decizie dau câte un punct. Modelul statistic vine abia după câteva sute de lead-uri cu rezultat cunoscut.
- **Grupe:** `suna_azi` (nișă potrivită și toate cele trei semnale), `hraneste` (nișă potrivită, semnale
  incomplete: rămâne în secvență), `nepotrivit` (altă nișă sau buget sub minim: secvența se oprește, fără
  presiune). **Lead-ul mare** (peste 10.000 lei pe lună [I]) merge direct la om: sună azi, cu notificare.
- Calificarea e un istoric (doar cu adăugare); starea curentă e ultimul rând. Fiecare calificare lasă urmă.
"""

import datetime as dt
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crm import registru, secventa
from app.crm.modele import Calificare, LeadCrm
from app.crm.registru import CrmRefuzat
from app.operare import audit, notificari, urme

INTRODUCERE = (
    "Sunt asistentul AI al agenției. Îți pun patru întrebări scurte, ca să vedem dacă te putem ajuta. "
    "Dacă preferi, poți vorbi oricând cu un om: scrie-ne și te sună cineva din echipă."
)
NISE_POTRIVITE = ("horeca", "comert_local", "servicii_locale", "sanatate_frumusete", "educatie", "imobiliare")
INTREBARI: dict[str, tuple[str, dict[str, str]]] = {
    "nisa": (
        "În ce domeniu lucrează firma?",
        {
            "horeca": "restaurant, cafenea, hotel",
            "comert_local": "magazin fizic sau online",
            "servicii_locale": "servicii locale (reparații, transport, curățenie)",
            "sanatate_frumusete": "clinică, salon, sală de sport",
            "educatie": "cursuri, școală, after-school",
            "imobiliare": "imobiliare, construcții",
            "alta": "alt domeniu",
        },
    ),
    "buget": (
        "Cât puteți investi lunar în marketing?",
        {
            "sub_1000": "sub 1.000 de lei",
            "1000_3000": "1.000–3.000 de lei",
            "3000_10000": "3.000–10.000 de lei",
            "peste_10000": "peste 10.000 de lei",
            "nu_stiu": "nu știu încă",
        },
    ),
    "termen": (
        "Când ați vrea să începem?",
        {
            "imediat": "cât mai repede",
            "1_3_luni": "în 1–3 luni",
            "peste_3_luni": "peste 3 luni",
            "doar_ma_informez": "doar mă informez",
        },
    ),
    "decident": (
        "Dumneavoastră hotărâți în firmă cheltuielile de marketing?",
        {"da": "da", "impreuna": "împreună cu altcineva", "nu": "nu"},
    ),
}
BUGET_MINIM_NEPOTRIVIT = {"sub_1000"}
BUGET_OK = {"1000_3000", "3000_10000", "peste_10000"}
BUGET_MARE = {"peste_10000"}  # [I]
TERMEN_OK = {"imediat", "1_3_luni"}
DECIDENT_OK = {"da", "impreuna"}
GRUPE = ("suna_azi", "hraneste", "nepotrivit")
ETICHETE_GRUPA = {"suna_azi": "de sunat azi", "hraneste": "de hrănit cu conținut", "nepotrivit": "nepotrivit"}
SURSE = ("formular", "conversatie", "manual")


@dataclass(frozen=True)
class Scor:
    scor: int
    grupa: str
    la_om: bool
    motive: list[str] = field(default_factory=list)


def valideaza(raspunsuri: dict[str, str]) -> dict[str, str]:
    curate = {k: str(raspunsuri.get(k, "")).strip() for k in INTREBARI}
    for k, (intrebare, optiuni) in INTREBARI.items():
        if curate[k] not in optiuni:
            raise CrmRefuzat(f"răspuns lipsă sau necunoscut la: {intrebare}")
    return curate


def puncteaza(raspunsuri: dict[str, str]) -> Scor:
    """Regula pură: răspunsuri validate → scor (0–4), grupă, la om, motive (în română)."""
    r = valideaza(raspunsuri)
    motive: list[str] = []
    nisa = r["nisa"] in NISE_POTRIVITE
    semnale = {
        "buget": r["buget"] in BUGET_OK,
        "termen": r["termen"] in TERMEN_OK,
        "decident": r["decident"] in DECIDENT_OK,
    }
    scor = int(nisa) + sum(semnale.values())
    if not nisa:
        motive.append("nișa nu e una în care lucrăm")
    if r["buget"] in BUGET_MINIM_NEPOTRIVIT:
        motive.append("bugetul declarat e sub minimul unui pachet")
    if not nisa or r["buget"] in BUGET_MINIM_NEPOTRIVIT:
        return Scor(scor, "nepotrivit", False, motive)
    motive += [f"lipsește: {k}" for k, ok in semnale.items() if not ok]
    if r["buget"] in BUGET_MARE:
        return Scor(scor, "suna_azi", True, [*motive, "lead mare: merge direct la om"])
    return Scor(scor, "suna_azi" if all(semnale.values()) else "hraneste", False, motive)


def califica(
    db: Session,
    lead_id: uuid.UUID,
    raspunsuri: dict[str, str],
    *,
    sursa: str = "formular",
    utilizator_id: uuid.UUID | None = None,
    acum: dt.datetime | None = None,
) -> Calificare:
    if sursa not in SURSE:
        raise CrmRefuzat("sursă de calificare necunoscută")
    acum = acum or dt.datetime.now(dt.UTC)
    lead = db.get(LeadCrm, lead_id, with_for_update=True)
    if lead is None:
        raise CrmRefuzat("lead inexistent")
    r = valideaza(raspunsuri)
    s = puncteaza(r)
    c = Calificare(
        lead_id=lead.id, raspunsuri=r, scor=s.scor, grupa=s.grupa, la_om=s.la_om, motive=s.motive,
        sursa=sursa, la=acum,
    )  # fmt: skip
    db.add(c)
    db.flush()
    registru.adauga_activitate(
        db, lead.id, "calificare", f"Calificat: {ETICHETE_GRUPA[s.grupa]} (scor {s.scor}/4).", utilizator_id
    )
    if s.grupa == "suna_azi":
        if lead.etapa == "nou":
            registru.muta_etapa(db, lead.id, "calificat", utilizator_id=utilizator_id, acum=acum)
        titlu = "Lead mare: sună azi (direct la om)" if s.la_om else "Sună azi lead-ul calificat"
        registru.creeaza_sarcina(db, lead.id, titlu, acum.date(), cheie=f"calificare:{lead.id}:suna_azi")
    elif s.grupa == "nepotrivit":
        secventa.opreste(db, lead.contact_id, "nepotrivit")
    if s.la_om:
        url = f"/crm/lead/{lead.id}"
        registru.dupa_commit(
            db,
            lambda: notificari.notifica(
                notificari.Nivel.IMPORTANT, "Lead mare", "Un lead cu buget mare cere un om azi.", url=url
            ),
        )
    audit.record(
        db, "crm.lead_calificat", obiect_tip="lead_crm", obiect_id=lead.id, utilizator_id=utilizator_id,
        actor_tip="utilizator" if utilizator_id else "sistem", detalii={"grupa": s.grupa, "scor": s.scor},
    )  # fmt: skip
    urme.inregistreaza(
        db, "crm", "calificare", obiect_tip="lead_crm", obiect_id=str(lead.id),
        intrari={"sursa": sursa}, iesiri={"grupa": s.grupa, "scor": s.scor, "la_om": s.la_om},
    )  # fmt: skip
    return c


def curenta(db: Session, lead_id: uuid.UUID) -> Calificare | None:
    return db.execute(
        select(Calificare)
        .where(Calificare.lead_id == lead_id)
        .order_by(Calificare.la.desc(), Calificare.id.desc())
        .limit(1)
    ).scalar_one_or_none()
