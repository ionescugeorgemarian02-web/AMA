"""Analistul de reclame ale concurenței (F10.8, C3, docs/12 §12.6, §12.1).

Citește săptămânal, din Meta Ad Library API (biblioteca oficială, gratuită, cu identitate confirmată),
reclamele concurenților urmăriți de fiecare client și face din ele **harta unghiurilor**: cine spune ce,
care reclame rulează de cel mai mult timp (semn că merg) și ce unghiuri nu folosește nimeni (spații libere).

Regula fermă din 12.6: **se analizează, nu se copiază.** Textul fiecărei reclame observate intră în
documentele colectate ale clientului, sub o sursă cu statutul `meta_ad_library` (text nereutilizabil), deci
validatorul G7 (F5.6) blochează fără nicio schimbare un text prea apropiat de o reclamă observată.

- Unghiul unei reclame se pune pe reguli (cuvinte-cheie pe categorie, fără diacritice); primul care se
  potrivește câștigă, altfel `altul`. Gruparea cu model (partea „L · T2” a lui C3) nu este construită.
- Citirea e CITIRE (nu efect extern), către o gazdă fixă; tokenul pleacă în antet. Fără token, jobul nu
  citește nimic și spune asta. Biblioteca TikTok are statut „de verificat” în 12.1 și nu e citită.

# NEVERIFICAT: forma răspunsului `ads_archive`, câmpurile disponibile pentru reclamele comerciale livrate în
UE și limitele de rată, pe un token real; testat pe API simulat.
"""

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy import Date, DateTime, Text, delete, func, select
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app import cercetare
from app.cercetare.tendinte import norm
from app.config import get_settings
from app.db import sesiune_agentie, sesiune_tenant
from app.ids import new_id
from app.logging import get_logger
from app.operare import audit, motor

log = get_logger("app.cercetare.reclame_concurenta")
NUME = "cercetare.reclame"
STATUT = "meta_ad_library"
NUME_SURSA = "Reclamele concurenței (Meta Ad Library)"
MAX_RECLAME = 100  # pe concurent și rulare
CAMPURI = "id,ad_creative_bodies,ad_delivery_start_time,ad_delivery_stop_time,publisher_platforms"
# Unghiurile, în ordinea în care se încearcă (rădăcini fără diacritice). Lista e de pornire.
UNGHIURI: dict[str, tuple[str, ...]] = {
    "pret": ("reducere", "redus", "pret", "oferta", "gratuit", "gratis", "discount", "ieftin", "promotie"),
    "urgenta": ("acum", "astazi", "ultimele", "ultima", "limitat", "grabeste", "expira", "doar azi"),
    "dovada_sociala": ("clienti", "recenzi", "recomand", "pareri", "stele", "multumiti", "testimonial"),
    "garantie": ("garanti", "retur", "banii inapoi", "fara risc"),
    "noutate": ("nou", "noua", "lansare", "lansam", "premiera"),
    "calitate": ("calitate", "premium", "artizanal", "proaspat", "natural", "specialitate", "autentic"),
    "comoditate": ("livrare", "rapid", "acasa", "online", "comanda", "simplu", "usor"),
    "local": ("local", "romanesc", "traditi", "din cartier", "aproape de tine"),
}
ETICHETE_UNGHI = {
    "pret": "Preț și ofertă",
    "urgenta": "Urgență",
    "dovada_sociala": "Dovadă socială",
    "garantie": "Garanție",
    "noutate": "Noutate",
    "calitate": "Calitate",
    "comoditate": "Comoditate",
    "local": "Local",
    "altul": "Alt unghi",
}


class Baza(DeclarativeBase):
    pass


class Concurent(Baza):
    __tablename__ = "concurenti_reclame"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    nume: Mapped[str] = mapped_column(Text)
    pagina_meta: Mapped[str] = mapped_column(Text)
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReclamaObservata(Baza):
    __tablename__ = "reclame_observate"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    concurent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    id_extern: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    platforme: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    format: Mapped[str] = mapped_column(Text, default="necunoscut")
    unghi: Mapped[str] = mapped_column(Text)
    prima_livrare: Mapped[dt.date] = mapped_column(Date)
    ultima_livrare: Mapped[dt.date | None] = mapped_column(Date)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    vazut_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConcurentInvalid(ValueError):
    pass


@dataclass(frozen=True)
class Reclama:
    """O reclamă citită din bibliotecă."""

    id_extern: str
    text: str
    prima_livrare: dt.date
    ultima_livrare: dt.date | None = None  # None = încă rulează
    platforme: tuple[str, ...] = ()
    format: str = "necunoscut"


# --- nuclee pure ----------------------------------------------------------------------------------------
def unghi(text: str) -> str:
    """Unghiul reclamei, pe reguli: prima categorie cu un cuvânt-cheie găsit; altfel `altul`."""
    n = " " + norm(text) + " "
    for cod, radacini in UNGHIURI.items():
        if any(f" {r}" in n for r in radacini):
            return cod
    return "altul"


def zile_rulare(prima: dt.date, ultima: dt.date | None, azi: dt.date) -> int:
    return max(0, ((ultima or azi) - prima).days) + 1


def din_raspuns(corp: dict[str, Any]) -> list[Reclama]:
    """`ads_archive` → reclame. Rândurile fără text sau fără dată de pornire se sar."""
    out: list[Reclama] = []
    for r in corp.get("data") or []:
        corpuri = r.get("ad_creative_bodies") or []
        text = str(corpuri[0]).strip() if corpuri else ""
        try:
            prima = dt.date.fromisoformat(str(r.get("ad_delivery_start_time", ""))[:10])
        except ValueError:
            continue
        if not text or not r.get("id"):
            continue
        stop = str(r.get("ad_delivery_stop_time") or "")[:10]
        try:
            ultima = dt.date.fromisoformat(stop) if stop else None
        except ValueError:
            ultima = None
        out.append(
            Reclama(
                str(r["id"])[:100],
                text[:5000],
                prima,
                ultima if ultima is None or ultima >= prima else None,
                tuple(str(p).lower() for p in r.get("publisher_platforms") or ()),
            )
        )
    return out[:MAX_RECLAME]


@dataclass
class Harta:
    """Harta unghiurilor unui client (12.6)."""

    pe_concurent: dict[str, dict[str, int]] = field(default_factory=dict)  # concurent → unghi → reclame
    de_durata: list[tuple[str, ReclamaObservata, int]] = field(
        default_factory=list
    )  # (concurent, reclamă, zile)
    spatii_libere: list[str] = field(default_factory=list)  # unghiuri pe care nu le folosește nimeni
    reclame: int = 0


def harta_din(randuri: list[tuple[str, ReclamaObservata]], azi: dt.date, *, top: int = 5) -> Harta:
    """Nucleu pur."""
    h = Harta(reclame=len(randuri))
    for concurent, r in randuri:
        pe = h.pe_concurent.setdefault(concurent, {})
        pe[r.unghi] = pe.get(r.unghi, 0) + 1
    cu_zile = [(c, r, zile_rulare(r.prima_livrare, r.ultima_livrare, azi)) for c, r in randuri]
    h.de_durata = sorted(cu_zile, key=lambda x: (-x[2], x[0]))[:top]
    folosite = {u for pe in h.pe_concurent.values() for u in pe}
    h.spatii_libere = [u for u in UNGHIURI if u not in folosite] if randuri else []
    return h


# --- citirea bibliotecii --------------------------------------------------------------------------------
def citeste_biblioteca(pagina_meta: str, transport: httpx.BaseTransport | None = None) -> list[Reclama]:
    """Reclamele unei pagini livrate în România. `PermissionError` fără token configurat."""
    s = get_settings()
    token = s.meta_ad_library_token.get_secret_value()
    if not token:
        raise PermissionError("tokenul Meta Ad Library nu este configurat")
    with httpx.Client(transport=transport, timeout=20.0) as c:
        r = c.get(
            f"https://graph.facebook.com/{s.meta_graph_versiune}/ads_archive",
            params={
                "search_page_ids": pagina_meta,
                "ad_reached_countries": '["RO"]',
                "ad_active_status": "ALL",
                "fields": CAMPURI,
                "limit": str(MAX_RECLAME),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    r.raise_for_status()
    return din_raspuns(dict(r.json()))


# --- concurenții ----------------------------------------------------------------------------------------
def concurenti(db: Session, tenant_id: uuid.UUID) -> list[Concurent]:
    return list(
        db.execute(
            select(Concurent).where(Concurent.tenant_id == tenant_id).order_by(Concurent.nume)
        ).scalars()
    )


def adauga_concurent(
    db: Session, tenant_id: uuid.UUID, *, nume: str, pagina_meta: str, utilizator_id: uuid.UUID | None
) -> Concurent:
    nume, pagina_meta = nume.strip(), pagina_meta.strip()
    if not 2 <= len(nume) <= 120:
        raise ConcurentInvalid("numele concurentului: între 2 și 120 de caractere")
    if not (pagina_meta.isdecimal() and 5 <= len(pagina_meta) <= 25):
        raise ConcurentInvalid(
            "identificatorul paginii Meta este un număr (îl găsești în biblioteca de reclame)"
        )
    if any(c.pagina_meta == pagina_meta for c in concurenti(db, tenant_id)):
        raise ConcurentInvalid("pagina este deja urmărită")
    c = Concurent(tenant_id=tenant_id, nume=nume, pagina_meta=pagina_meta)
    db.add(c)
    db.flush()
    audit.record(
        db, "concurent.adaugat", obiect_tip="concurent", obiect_id=c.id, tenant_id=tenant_id,
        utilizator_id=utilizator_id, detalii={"nume": nume},
    )  # fmt: skip
    return c


def sterge_concurent(db: Session, tenant_id: uuid.UUID, concurent_id: uuid.UUID) -> None:
    db.execute(delete(Concurent).where(Concurent.tenant_id == tenant_id, Concurent.id == concurent_id))


# --- înregistrarea reclamelor ---------------------------------------------------------------------------
def _sursa(db: Session, tenant_id: uuid.UUID) -> uuid.UUID:
    for s in cercetare.surse(db, tenant_id):
        if s.statut == STATUT:
            return s.id
    return cercetare.creeaza_sursa(
        db, tenant_id=tenant_id, tip="manual", statut_cod=STATUT, nume=NUME_SURSA
    ).id


def inregistreaza(db: Session, concurent: Concurent, reclame: list[Reclama]) -> int:
    """Scrie reclamele noi și actualizează perioada celor știute. Textul fiecărei reclame noi intră în
    documentele colectate (statut nereutilizabil), de unde îl citește G7. Întoarce câte sunt noi."""
    stiute = {
        r.id_extern: r
        for r in db.execute(
            select(ReclamaObservata).where(ReclamaObservata.concurent_id == concurent.id)
        ).scalars()
    }
    noi, sursa_id = 0, None
    for r in reclame:
        vechi = stiute.get(r.id_extern)
        if vechi is not None:
            vechi.ultima_livrare, vechi.vazut_la = r.ultima_livrare, dt.datetime.now(dt.UTC)
            continue
        sursa_id = sursa_id or _sursa(db, concurent.tenant_id)
        doc, _ = cercetare.adauga_text(
            db,
            tenant_id=concurent.tenant_id,
            sursa_id=sursa_id,
            titlu=f"{concurent.nume}: reclama {r.id_extern}"[:200],
            text=r.text,
        )
        db.add(
            ReclamaObservata(
                tenant_id=concurent.tenant_id,
                concurent_id=concurent.id,
                id_extern=r.id_extern,
                text=r.text,
                platforme=list(r.platforme),
                format=r.format,
                unghi=unghi(r.text),
                prima_livrare=r.prima_livrare,
                ultima_livrare=r.ultima_livrare,
                document_id=doc.id,
            )
        )
        noi += 1
    db.flush()
    return noi


def harta(db: Session, tenant_id: uuid.UUID, azi: dt.date | None = None) -> Harta:
    randuri = [
        (str(nume), r)
        for nume, r in db.execute(
            select(Concurent.nume, ReclamaObservata)
            .join(Concurent, Concurent.id == ReclamaObservata.concurent_id)
            .where(ReclamaObservata.tenant_id == tenant_id)
        ).all()
    ]
    return harta_din(randuri, azi or dt.datetime.now(dt.UTC).date())


def ruleaza(transport: httpx.BaseTransport | None = None) -> dict[str, int]:
    """Rularea săptămânală peste toți concurenții urmăriți. Un concurent necitit nu îi oprește pe ceilalți."""
    numar = {"concurenti": 0, "reclame_noi": 0, "necititi": 0}
    with sesiune_agentie() as db:
        toti = [(c.tenant_id, c.id, c.pagina_meta) for c in db.execute(select(Concurent)).scalars()]
    for tenant_id, concurent_id, pagina in toti:
        try:
            reclame = citeste_biblioteca(pagina, transport)  # rețeaua, în afara tranzacției
        except PermissionError:
            log.warning("analistul de reclame nu rulează: lipsește tokenul Meta Ad Library")
            numar["necititi"] += len(toti) - numar["concurenti"]
            break
        except (httpx.HTTPError, ValueError) as exc:
            log.info("bibliotecă necitită", extra={"tip_eroare": type(exc).__name__})
            numar["necititi"] += 1
            continue
        with sesiune_tenant(tenant_id) as db:
            c = db.get(Concurent, concurent_id)
            if c is not None:
                numar["reclame_noi"] += inregistreaza(db, c, reclame)
        numar["concurenti"] += 1
    return numar


@motor.pas("cercetare.pas_reclame")
def _pas() -> str:
    return str(ruleaza())


@motor.flux(NUME)
def flux(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _pas()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME, "30 6 * * 1", flux)  # săptămânal (12.7), luni dimineața


declara_programari()
