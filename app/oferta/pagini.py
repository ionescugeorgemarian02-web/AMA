"""Oferta, pâlnia și paginile de captare (F7.9, D2 + E3, docs/04, docs/05).

1. Arhitectul de ofertă (D2, profilul `strategie`) propune magnetul de lead-uri și traseul pâlniei.
2. Copywriterul de conversie (E3, profilul `creatie`) scrie pagina de captare, 3 reclame text și studiul de
caz.
3. Validarea: cascada pe G2 (fapte), G3 (politici) și G9 (juridic) pe toate textele, plus regula
deterministă a
   UNUI SINGUR apel la acțiune (butonul; niciun alt îndemn în text).
4. Un om publică pagina (`publica`); platforma o găzduiește la `/site/p/<slug>`, cu butonul spre ținta
ofertei.
Pagina stă în `pagini_captare` (pe clientul ei: agenția își face pagina pe brandul propriu)."""

import datetime as dt
import re
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app import continut, gateway
from app.ids import new_id
from app.operare import audit
from app.operare.motor import Prioritate
from app.validare.independent import evalueaza_text

CODURI = ("G2", "G3", "G9")
# Îndemnuri care ar face un al doilea apel la acțiune în textul paginii (lista e [I]; se completează din
# banc).
INDEMNURI = re.compile(
    r"\b(sun[ăa]\w*|cump[ăa]r[ăa]\w*|comand[ăa]\w*|abon(ea|a)z[ăa]\w*|[îi]nscrie-te|descarc[ăa]|programeaz[ăa]|"
    r"scrie-ne|contacteaz[ăa]-ne|cere|apas[ăa]|click|d[ăa] clic)\b",
    re.IGNORECASE,
)
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class PropunereOferta(gateway.Iesire):
    magnet: str = Field(min_length=10, max_length=300)
    promisiune: str = Field(min_length=10, max_length=300)
    public: str = Field(min_length=5, max_length=300)
    traseu: list[str] = Field(min_length=3, max_length=6)


class StudiuCaz(BaseModel):
    model_config = ConfigDict(extra="forbid")
    situatie: str = Field(min_length=10, max_length=600)
    actiune: str = Field(min_length=10, max_length=600)
    rezultat: str = Field(min_length=10, max_length=600)


class PaginaScrisa(gateway.Iesire):
    titlu: str = Field(min_length=10, max_length=120)
    subtitlu: str = Field(min_length=10, max_length=240)
    beneficii: list[str] = Field(min_length=3, max_length=5)
    dovada: str = Field(min_length=10, max_length=400)
    apel: str = Field(min_length=3, max_length=60)
    reclame: list[str] = Field(min_length=3, max_length=3)
    studiu_caz: StudiuCaz


class Baza(DeclarativeBase):
    pass


class PaginaCaptare(Baza):
    __tablename__ = "pagini_captare"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    slug: Mapped[str] = mapped_column(Text)
    tinta: Mapped[str] = mapped_column(Text)
    propunere: Mapped[dict[str, Any]] = mapped_column(JSONB)
    continut: Mapped[dict[str, Any]] = mapped_column(JSONB)
    validare: Mapped[dict[str, Any]] = mapped_column(JSONB)
    stare: Mapped[str] = mapped_column(Text, default="propus")
    publicat_de: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    publicat_la: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EroareOferta(ValueError):
    pass


def texte_pagina(c: dict[str, Any]) -> str:
    """Textul paginii (fără buton), în ordinea afișării."""
    s = c["studiu_caz"]
    return "\n".join(
        [c["titlu"], c["subtitlu"], *c["beneficii"], c["dovada"], s["situatie"], s["actiune"], s["rezultat"]]
    )


def apeluri_in_plus(c: dict[str, Any]) -> list[str]:
    """Nucleu pur: îndemnurile din textul paginii, în afara butonului (trebuie să fie zero)."""
    return [m.group(0) for m in INDEMNURI.finditer(texte_pagina(c))]


def un_singur_apel(c: dict[str, Any]) -> bool:
    return bool(c.get("apel", "").strip()) and not apeluri_in_plus(c)


def genereaza(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    firma: str,
    oferta: str,
    public: str,
    apel: str,
    tinta: str,
    slug: str,
) -> PaginaCaptare:
    if not SLUG.match(slug) or not tinta.startswith("/"):
        raise EroareOferta("slug sau țintă invalide")
    continut.prompturi.asigura()
    r1 = gateway.apeleaza(
        db,
        prompt="oferta.arhitect@1",
        schema=PropunereOferta,
        tenant_id=tenant_id,
        componenta="oferta.arhitect",
        prioritate=Prioritate.P2,
        max_tokeni=800,
        variabile={"firma": firma, "oferta": oferta, "public": public, "apel": apel},
    )
    if not isinstance(r1.iesire, PropunereOferta):
        raise TypeError("ieșirea nu respectă schema")
    p = r1.iesire
    r2 = gateway.apeleaza(
        db,
        prompt="oferta.copywriter@1",
        schema=PaginaScrisa,
        tenant_id=tenant_id,
        componenta="oferta.copywriter",
        prioritate=Prioritate.P2,
        max_tokeni=1500,
        variabile={
            "firma": firma,
            "magnet": p.magnet,
            "promisiune": p.promisiune,
            "public": p.public,
            "traseu": "\n".join(f"- {x}" for x in p.traseu),
            "apel": apel,
        },
    )
    if not isinstance(r2.iesire, PaginaScrisa):
        raise TypeError("ieșirea nu respectă schema")
    c = r2.iesire.model_dump()
    c["apel"] = apel  # butonul e al ofertei, nu al modelului
    rez = evalueaza_text(
        db,
        tenant_id,
        tip="pagina",
        canal="site",
        text=texte_pagina(c),
        campuri={"reclame": c["reclame"], "apel": apel},
        coduri=CODURI,
        model_autor=r2.model,
    )
    validare = {
        "trece": rez.trece and un_singur_apel(c),
        "cascada": rez.trece,
        "rulate": list(rez.rulate),
        "blocante": rez.blocante(),
        "apeluri_in_plus": apeluri_in_plus(c),
        "verdicte": rez.verdicte(),
    }
    pg = PaginaCaptare(
        tenant_id=tenant_id,
        slug=slug,
        tinta=tinta,
        propunere=p.model_dump(),
        continut=c,
        validare=validare,
        stare="validat" if validare["trece"] else "respins",
    )
    db.add(pg)
    db.flush()
    audit.record(
        db,
        "pagina_captare.generata",
        obiect_tip="pagina_captare",
        obiect_id=pg.id,
        tenant_id=tenant_id,
        actor_tip="sistem",
        detalii={"stare": pg.stare, "rulate": validare["rulate"]},
    )
    return pg


def publica(db: Session, pagina_id: uuid.UUID, *, utilizator_id: uuid.UUID) -> PaginaCaptare:
    pg = db.execute(select(PaginaCaptare).where(PaginaCaptare.id == pagina_id).with_for_update()).scalar_one()
    if pg.stare != "validat":
        raise EroareOferta("se publică doar o pagină validată")
    for alta in db.execute(
        select(PaginaCaptare).where(PaginaCaptare.slug == pg.slug, PaginaCaptare.stare == "publicat")
    ).scalars():
        alta.stare = "inlocuit"
    pg.stare, pg.publicat_de, pg.publicat_la = "publicat", utilizator_id, dt.datetime.now(dt.UTC)
    db.flush()
    audit.record(
        db,
        "pagina_captare.publicata",
        obiect_tip="pagina_captare",
        obiect_id=pg.id,
        tenant_id=pg.tenant_id,
        utilizator_id=utilizator_id,
        detalii={"slug": pg.slug},
    )
    return pg


def publicata(db: Session, slug: str) -> PaginaCaptare | None:
    if not SLUG.match(slug):
        return None
    return db.execute(
        select(PaginaCaptare).where(PaginaCaptare.slug == slug, PaginaCaptare.stare == "publicat")
    ).scalar_one_or_none()
