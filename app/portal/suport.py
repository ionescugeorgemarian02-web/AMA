"""Asistentul de suport din portal (F12.10, L5): răspunde la întrebări despre cont și livrabile, din datele
clientului; escaladează restul la proprietar.

- **Din datele clientului, nu din model** (componentă D, D-024): starea livrabilelor (filtrată pe canalul sau
  tipul din întrebare), contul (cine are acces, cu ce rol) și, dacă întrebarea numește magazinul Shopify,
  câți clienți ai magazinului au acord de email (`comert.vanzari.pentru_crm`, citire prin exportul lui C).
  Totul rulează pe sesiunea clientului (RLS): asistentul nu poate vedea alt client.
- **Escaladare:** facturarea și plățile, reclamațiile și orice întrebare pe care nu o recunoaște ajung la
  proprietar (notificare + `/crm/suport`); clientul află că îi răspunde un om. Asistentul se prezintă ca AI.
- Fiecare întrebare e păstrată (`portal_suport`) și lasă urmă (`portal / suport`).
"""

import datetime as dt
import re
import unicodedata
import uuid
from collections import Counter

from sqlalchemy import Boolean, DateTime, Text, func, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app import comert
from app.ids import new_id
from app.operare import audit, notificari, urme
from app.productie import Livrabil

PREZENTARE = (
    "Sunt asistentul AI al portalului. Răspund din datele contului tău; pentru restul, te preia un om."
)
ETICHETE_STARE = {
    "planificat": "planificat",
    "briefat": "în pregătire",
    "in_scriere": "în scriere",
    "in_validare": "în verificare",
    "in_reparatie": "în corectare",
    "validat": "verificat",
    "asteapta_aprobare": "așteaptă aprobarea ta",
    "aprobat": "aprobat",
    "in_randare": "în producție",
    "control_media": "în verificare",
    "gata": "gata",
    "programat": "programat",
    "in_publicare": "se publică",
    "publicat": "publicat",
    "in_masurare": "publicat",
    "inchis": "încheiat",
    "respins": "respins",
    "carantina": "oprit pentru verificare",
    "esec_temporar": "se reîncearcă",
    "coada_de_erori": "la echipă",
    "anulat": "anulat",
    "expirat": "expirat",
}
CANALE = ("instagram", "facebook", "tiktok", "linkedin", "youtube", "blog")
TIPURI = {"postare": "postare", "postari": "postare", "video": "video", "clip": "video", "articol": "articol"}
REGULI: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("reclamatie", re.compile(r"reclamati|nemultumit|dezamagit|inacceptabil|vreau sa reziliez|plangere")),
    ("facturare", re.compile(r"factur|plat[ai]|abonament|pret|bani|card|rambursa|tva|chitant|reducere")),
    ("magazin", re.compile(r"shopify|magazin|myshopify")),
    (
        "livrabile",
        re.compile(r"livrabil|postar|video|clip|articol|calendar|publicat|programat|aprob|material"),
    ),
    ("cont", re.compile(r"\bcont\b|contul|acces|parola|utilizator|rol\b|invit|autentific")),
)
SHOP = re.compile(r"\b([a-z0-9][a-z0-9-]{0,60}\.myshopify\.com)\b")


class Baza(DeclarativeBase):
    pass


class IntrebareSuport(Baza):
    __tablename__ = "portal_suport"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    utilizator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    intrebare: Mapped[str] = mapped_column(Text)
    categorie: Mapped[str] = mapped_column(Text)
    raspuns: Mapped[str] = mapped_column(Text, default="")
    escaladat: Mapped[bool] = mapped_column(Boolean)
    preluat_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IntrebareInvalida(ValueError):
    pass


def _norma(text: str) -> str:
    fara = unicodedata.normalize("NFKD", text)
    return "".join(c for c in fara if not unicodedata.combining(c)).lower()


def categorie(intrebare: str) -> str:
    """Categoria întrebării (pur). Facturarea și reclamațiile câștigă: ajung mereu la om."""
    t = _norma(intrebare)
    for cat, regula in REGULI:
        if regula.search(t):
            return cat
    return "altceva"


def _livrabile(db: Session, tenant_id: uuid.UUID, intrebare: str) -> str:
    t = _norma(intrebare)
    q = select(Livrabil).where(Livrabil.tenant_id == tenant_id)
    canal = next((c for c in CANALE if c in t), None)
    tip = next((v for k, v in TIPURI.items() if k in t), None)
    if canal:
        q = q.where(Livrabil.canal == canal)
    if tip:
        q = q.where(Livrabil.tip == tip)
    livrabile = list(db.scalars(q.order_by(Livrabil.termen_la.nulls_last()).limit(200)))
    filtru = " ".join(x for x in (tip and f"de tip {tip}", canal and f"pe {canal}") if x)
    if not livrabile:
        return f"Nu ai încă livrabile{' ' + filtru if filtru else ''}."
    stari = Counter(ETICHETE_STARE.get(x.stare, x.stare) for x in livrabile)
    rezumat = ", ".join(f"{n} {s}" for s, n in stari.most_common())
    urmatorul = next(
        (x for x in livrabile if x.termen_la and x.stare not in ("publicat", "inchis", "anulat")), None
    )
    text = f"Livrabilele tale{' ' + filtru if filtru else ''}: {rezumat}."
    if urmatorul is not None and urmatorul.termen_la is not None:
        text += (
            f" Următorul: {urmatorul.tip} pe {urmatorul.canal}, termen {urmatorul.termen_la:%d.%m.%Y}, "
            f"stare: {ETICHETE_STARE.get(urmatorul.stare, urmatorul.stare)}."
        )
    if stari.get("așteaptă aprobarea ta"):
        text += " Le aprobi din pagina Aprobări."
    return text


def _cont(db: Session, tenant_id: uuid.UUID) -> str:
    n = db.execute(  # citire pe sesiunea clientului (RLS)
        text("SELECT count(*) FROM apartenente WHERE tenant_id = :t AND sters_la IS NULL"), {"t": tenant_id}
    ).scalar_one()
    return (
        f"Contul firmei are {n} {'persoană' if n == 1 else 'persoane'} cu acces. Parola și autentificarea în "
        "doi pași le schimbi din pagina Cont; o persoană nouă o invită titularul contului."
    )


def _magazin(tenant_id: uuid.UUID, intrebare: str) -> str | None:
    gasit = SHOP.search(_norma(intrebare))
    if gasit is None:
        return None
    eligibili = comert.vanzari.pentru_crm(
        tenant_id, gasit.group(1)
    )  # export C: doar cu acord, reverificat acum
    return (
        f"Magazinul {gasit.group(1)} are acum {len(eligibili)} clienți cu acord de email (din Shopify). "
        "Acordul se reverifică înainte de orice trimitere."
    )


def intreaba(
    db: Session, tenant_id: uuid.UUID, intrebare: str, *, utilizator_id: uuid.UUID | None
) -> IntrebareSuport:
    intrebare = " ".join(intrebare.split())
    if not 2 <= len(intrebare) <= 1000:
        raise IntrebareInvalida("Scrie întrebarea în cel mult 1000 de caractere.")
    cat = categorie(intrebare)
    raspuns: str | None = None
    if cat == "livrabile":
        raspuns = _livrabile(db, tenant_id, intrebare)
    elif cat == "cont":
        raspuns = _cont(db, tenant_id)
    elif cat == "magazin":
        raspuns = _magazin(tenant_id, intrebare)
    escaladat = raspuns is None
    if escaladat:
        raspuns = "Am trimis întrebarea ta unui om din echipă; îți răspunde în cel mult o zi lucrătoare."
    r = IntrebareSuport(
        id=new_id(),
        tenant_id=tenant_id,
        utilizator_id=utilizator_id,
        intrebare=intrebare,
        categorie=cat,
        raspuns=raspuns,
        escaladat=escaladat,
    )
    db.add(r)
    db.flush()
    audit.record(
        db,
        "portal.suport",
        obiect_tip="intrebare_suport",
        obiect_id=r.id,
        tenant_id=tenant_id,
        utilizator_id=utilizator_id,
        detalii={"categorie": cat, "escaladat": escaladat},
    )
    urme.inregistreaza(
        db,
        "portal",
        "suport",
        rezultat="info" if escaladat else "ok",
        obiect_tip="intrebare_suport",
        obiect_id=str(r.id),
        tenant_id=tenant_id,
        iesiri={"categorie": cat, "escaladat": escaladat},
    )
    if escaladat:
        titlu = "Reclamație de la un client" if cat == "reclamatie" else "Întrebare de client pentru tine"
        nivel = notificari.Nivel.IMPORTANT
        from app.crm import registru  # după commit, ca la CRM

        registru.dupa_commit(
            db, lambda: notificari.notifica(nivel, titlu, f"Categoria: {cat}.", url="/crm/suport")
        )
    return r


def istoric(db: Session, tenant_id: uuid.UUID, *, limita: int = 20) -> list[IntrebareSuport]:
    return list(
        db.scalars(
            select(IntrebareSuport)
            .where(IntrebareSuport.tenant_id == tenant_id)
            .order_by(IntrebareSuport.la.desc())
            .limit(limita)
        )
    )


def escaladate(db: Session) -> list[IntrebareSuport]:
    """Pentru proprietar (context de agenție): escaladările nepreluate, ale tuturor clienților."""
    return list(
        db.scalars(
            select(IntrebareSuport)
            .where(IntrebareSuport.escaladat.is_(True), IntrebareSuport.preluat_la.is_(None))
            .order_by(IntrebareSuport.la)
        )
    )


def preia(db: Session, intrebare_id: uuid.UUID) -> None:
    r = db.get(IntrebareSuport, intrebare_id)
    if r is None or not r.escaladat or r.preluat_la is not None:
        raise IntrebareInvalida("Întrebarea nu există sau a fost deja preluată.")
    r.preluat_la = dt.datetime.now(dt.UTC)
    audit.record(
        db, "portal.suport_preluat", obiect_tip="intrebare_suport", obiect_id=r.id, tenant_id=r.tenant_id
    )
