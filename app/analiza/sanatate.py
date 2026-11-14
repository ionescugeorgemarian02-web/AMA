"""Indicatorii de business și scorul de sănătate al clientului (F10.4, L4, docs/04 §4.10 și §4.13).

Totul este pe reguli, calculat din datele existente la fiecare afișare (fără model, fără tabel nou):

- **Semnalele de risc** (4.10), nucleu pur (`semnale`): aprobări întârziate la client, respingeri multe,
  portal nedeschis, facturi restante. Fiecare semnal scade puncte din 100; scorul dă nivelul: `bun`,
  `atentie`, `risc`. Pragurile sunt de pornire [I] și stau în constante, într-un singur loc.
- **Indicatorii** (4.13) pe client, pe ultimele 30 de zile: venitul lunar recurent, minutele de om
  (ESTIMARE din acțiuni numărate, nu cronometrare), rata de aprobare din prima, livrarea la timp, cota de
  modele folosită în luna curentă. La nivel de agenție: venitul total și churn-ul lunar. Conversiile
  audit → apel → client cer CRM-ul (F12) și sunt arătate ca indisponibile, nu ca zero.
- Un indicator fără date destule este `None` („–” pe ecran): nu se afișează un procent din zero cazuri.

„Portal nedeschis” se măsoară prin ultima autentificare reușită a unui utilizator al clientului (jurnalul
de audit); o sesiune rămasă deschisă mai multe zile nu se vede ca vizită nouă (aproximare acceptată).
"""

import datetime as dt
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import finante, gateway, productie
from app.analiza.modele import MetriciPostare
from app.finante.modele import Abonament
from app.gateway.reguli_buget import Fereastra
from app.operare.modele import JurnalAudit
from app.productie import Aprobare, Livrabil, Tranzitie
from app.publicare.modele import PublicareAsistata

FEREASTRA = dt.timedelta(days=30)
# --- pragurile semnalelor [I] ---------------------------------------------------------------------------
INTARZIERE_APROBARE = dt.timedelta(hours=48)  # o cerere la client, nedecisă de atâta timp, e „întârziată”
DECIZII_MINIME = 5  # sub atâtea decizii nu se judecă rata de respingere
PRAG_RESPINGERI = 0.30
PORTAL_ATENTIE = dt.timedelta(days=14)
PORTAL_RISC = dt.timedelta(days=30)
TOLERANTA_LIVRARE = dt.timedelta(hours=1)
# --- estimarea minutelor de om, pe acțiune [I] ----------------------------------------------------------
MINUTE_APROBARE, MINUTE_PUBLICARE_ASISTATA, MINUTE_CIFRE_MANUALE = 2, 3, 2
NIVELURI = {"bun": "În regulă", "atentie": "De urmărit", "risc": "Risc de plecare"}
TINTE = {  # 4.13, pentru comparația de pe ecran
    "minute_om": 120,
    "aprobare_din_prima": 0.85,
    "livrare_la_timp": 0.97,
    "cota_modele": 0.60,
    "churn": 0.05,
}


@dataclass(frozen=True)
class Semnal:
    cod: str
    text: str
    puncte: int  # cât scade din scor


@dataclass(frozen=True)
class DateRisc:
    """Ce citesc regulile de risc despre un client."""

    aprobari_intarziate: int = 0  # cereri la client, în așteptare de peste `INTARZIERE_APROBARE`
    aprobari_expirate: int = 0  # cereri la client expirate în fereastră
    decizii: int = 0
    respingeri: int = 0
    ultima_autentificare: dt.datetime | None = None
    client_de_la: dt.datetime | None = None
    abonament_stare: str | None = None


def semnale(d: DateRisc, acum: dt.datetime) -> list[Semnal]:
    """Nucleu pur: semnalele de risc din 4.10."""
    out: list[Semnal] = []
    if d.aprobari_intarziate:
        n = d.aprobari_intarziate
        out.append(
            Semnal(
                "aprobari_intarziate",
                f"{n} {'aprobare așteaptă' if n == 1 else 'aprobări așteaptă'} la client de peste "
                f"{int(INTARZIERE_APROBARE.total_seconds() // 3600)} de ore",
                30 if n >= 3 else 20,
            )
        )
    if d.aprobari_expirate:
        n = d.aprobari_expirate
        out.append(
            Semnal(
                "aprobari_expirate",
                f"{n} {'aprobare a expirat' if n == 1 else 'aprobări au expirat'} fără decizie "
                "în ultimele 30 de zile",
                20 if n >= 3 else 10,
            )
        )
    if d.decizii >= DECIZII_MINIME and d.respingeri / d.decizii > PRAG_RESPINGERI:
        out.append(
            Semnal(
                "respingeri_multe",
                f"{d.respingeri} respingeri din {d.decizii} decizii în ultimele 30 de zile",
                20,
            )
        )
    vechime = acum - d.client_de_la if d.client_de_la else None
    if vechime is None or vechime >= PORTAL_ATENTIE:  # un client abia venit nu e „absent”
        absent = acum - d.ultima_autentificare if d.ultima_autentificare else None
        if absent is None:
            out.append(Semnal("portal_nedeschis", "Nimeni de la client nu a intrat încă în portal", 15))
        elif absent >= PORTAL_RISC:
            out.append(Semnal("portal_nedeschis", f"Portal nedeschis de {absent.days} de zile", 25))
        elif absent >= PORTAL_ATENTIE:
            out.append(Semnal("portal_nedeschis", f"Portal nedeschis de {absent.days} de zile", 15))
    if d.abonament_stare == "suspendat":
        out.append(Semnal("facturi_restante", "Abonament suspendat pentru neplată", 40))
    elif d.abonament_stare == "restant":
        out.append(Semnal("facturi_restante", "Factură restantă", 25))
    return out


def scor(s: list[Semnal]) -> int:
    return max(0, 100 - sum(x.puncte for x in s))


def nivel(valoare: int) -> str:
    return "bun" if valoare >= 80 else "atentie" if valoare >= 50 else "risc"


def rata(parte: int, total: int) -> float | None:
    """Un procent doar dacă există din ce: fără cazuri nu se afișează 0% sau 100%."""
    return round(parte / total, 4) if total > 0 else None


@dataclass(frozen=True)
class Indicatori:
    venit_lunar: int  # lei; 0 fără abonament activ
    minute_om: int  # estimare
    aprobare_din_prima: float | None
    livrare_la_timp: float | None
    cota_modele: float | None
    livrabile_cu_termen: int = 0
    decizii: int = 0


@dataclass(frozen=True)
class FisaClient:
    tenant_id: uuid.UUID
    nume: str
    scor: int
    nivel: str
    semnale: list[Semnal]
    indicatori: Indicatori


@dataclass(frozen=True)
class Agentie:
    venit_lunar: int
    clienti_platitori: int
    churn_lunar: float | None
    fise: list[FisaClient] = field(default_factory=list)


def _prima_decizie(aprobari: list[Aprobare]) -> dict[uuid.UUID, Aprobare]:
    prima: dict[uuid.UUID, Aprobare] = {}
    for a in sorted(aprobari, key=lambda x: x.decis_la or dt.datetime.max.replace(tzinfo=dt.UTC)):
        prima.setdefault(a.livrabil_id, a)
    return prima


def _cota(db: Session, tenant_id: uuid.UUID, acum: dt.datetime) -> float | None:
    buget = gateway.bugete.efectiv(db, tenant_id).luna
    consum = gateway.bugete.consum_curent(db, tenant_id, acum)[Fereastra.LUNA]
    parti = [
        float(Decimal(folosit) / Decimal(limita))
        for folosit, limita in (
            (consum.apeluri, buget.apeluri),
            (consum.tokeni, buget.tokeni),
            (consum.pret_umbra, buget.pret_umbra),
        )
        if limita
    ]
    return round(max(parti), 4) if parti else None


def fisa(
    db: Session, tenant_id: uuid.UUID, nume: str, client_de_la: dt.datetime | None, acum: dt.datetime
) -> FisaClient:
    """Indicatorii și scorul unui client, din date (sesiunea trebuie să vadă clientul: RLS)."""
    de_la = acum - FEREASTRA
    aprobari = list(
        db.execute(
            select(Aprobare).where(
                Aprobare.tenant_id == tenant_id,
                (Aprobare.creat_la >= de_la) | (Aprobare.stare == "in_asteptare"),
            )
        ).scalars()
    )
    la_client = [a for a in aprobari if a.decident == "client"]
    decise = [a for a in aprobari if a.decis_la is not None and a.stare in ("aprobat", "respins")]
    prima = _prima_decizie(decise)
    abonament = finante.abonamente.al_clientului(db, tenant_id)
    ultima = db.execute(
        select(func.max(JurnalAudit.creat_la)).where(
            JurnalAudit.tenant_id == tenant_id, JurnalAudit.actiune == "autentificare.reusita"
        )
    ).scalar_one_or_none()
    risc = DateRisc(
        aprobari_intarziate=sum(
            1 for a in la_client if a.stare == "in_asteptare" and acum - a.creat_la >= INTARZIERE_APROBARE
        ),
        aprobari_expirate=sum(1 for a in la_client if a.stare == "expirat" and a.termen_la >= de_la),
        decizii=len(decise),
        respingeri=sum(1 for a in decise if a.stare == "respins"),
        ultima_autentificare=ultima,
        client_de_la=client_de_la,
        abonament_stare=abonament.stare if abonament else None,
    )
    s = semnale(risc, acum)

    cu_termen = list(
        db.execute(
            select(Livrabil.id, Livrabil.termen_la).where(
                Livrabil.tenant_id == tenant_id, Livrabil.termen_la > de_la, Livrabil.termen_la <= acum
            )
        ).all()
    )
    publicate: dict[uuid.UUID, dt.datetime] = {}
    if cu_termen:
        for lid, la in db.execute(
            select(Tranzitie.livrabil_id, func.min(Tranzitie.creat_la))
            .where(
                Tranzitie.livrabil_id.in_([i for i, _ in cu_termen]),
                Tranzitie.in_stare == productie.Stare.PUBLICAT.value,
                Tranzitie.rezultat == "aplicata",
            )
            .group_by(Tranzitie.livrabil_id)
        ).all():
            publicate[lid] = la
    la_timp = 0
    for lid, termen in cu_termen:
        publicat = publicate.get(lid)
        if publicat is not None and termen is not None and publicat <= termen + TOLERANTA_LIVRARE:
            la_timp += 1

    asistate = db.execute(
        select(func.count())
        .select_from(PublicareAsistata)
        .where(
            PublicareAsistata.tenant_id == tenant_id,
            PublicareAsistata.stare == "publicat",
            PublicareAsistata.publicat_la >= de_la,
        )
    ).scalar_one()
    manuale = db.execute(
        select(func.count())
        .select_from(MetriciPostare)
        .where(
            MetriciPostare.tenant_id == tenant_id,
            MetriciPostare.sursa == "manual",
            MetriciPostare.citit_la >= de_la,
        )
    ).scalar_one()
    decise_de_operator = sum(1 for a in decise if a.decident == "operator")
    ind = Indicatori(
        venit_lunar=abonament.suma if abonament and abonament.stare in ("activ", "restant") else 0,
        minute_om=decise_de_operator * MINUTE_APROBARE
        + int(asistate) * MINUTE_PUBLICARE_ASISTATA
        + int(manuale) * MINUTE_CIFRE_MANUALE,
        aprobare_din_prima=rata(sum(1 for a in prima.values() if a.stare == "aprobat"), len(prima)),
        livrare_la_timp=rata(la_timp, len(cu_termen)),
        cota_modele=_cota(db, tenant_id, acum),
        livrabile_cu_termen=len(cu_termen),
        decizii=len(prima),
    )
    valoare = scor(s)
    return FisaClient(tenant_id, nume, valoare, nivel(valoare), s, ind)


def churn(suspendate_in_fereastra: int, platitoare_acum: int) -> float | None:
    """Nucleu pur: plecările din fereastră raportate la cei care plăteau la începutul ei."""
    return rata(suspendate_in_fereastra, platitoare_acum + suspendate_in_fereastra)


def situatie(db: Session, acum: dt.datetime | None = None) -> Agentie:
    """Tabloul agenției: fișa fiecărui client vizibil sesiunii, cei cu scorul cel mai mic primii."""
    from app.conturi import lista_clienti

    acum = acum or dt.datetime.now(dt.UTC)
    fise = [fisa(db, c.id, c.nume, c.creat_la, acum) for c in lista_clienti(db)]
    fise.sort(key=lambda f: (f.scor, f.nume))
    A = Abonament
    platitoare = db.execute(
        select(func.count()).select_from(A).where(A.stare.in_(("activ", "restant")))
    ).scalar_one()
    suspendate = db.execute(
        select(func.count()).select_from(A).where(A.stare == "suspendat", A.suspendat_la >= acum - FEREASTRA)
    ).scalar_one()
    return Agentie(
        venit_lunar=sum(f.indicatori.venit_lunar for f in fise),
        clienti_platitori=int(platitoare),
        churn_lunar=churn(int(suspendate), int(platitoare)),
        fise=fise,
    )
