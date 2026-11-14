"""Cercetătorul de tendințe (F10.7, C2, docs/12 §12.1, §12.2, §12.5, §12.7).

În fiecare dimineață citește sursele oficiale și scrie, pentru fiecare client cu profil de nișă, fișe de
tendință cu dovezi; iar linkurile lipite în inboxul de tendințe devin fișe cu propunere de calendar.

- **Surse** (doar cele permise de 12.1): fluxul RSS de tendințe zilnice Google pentru România, clipurile
  populare din YouTube Data API (dacă există cheie), fluxurile RSS de nișă ale clientului. TikTok și
  Instagram nu se citesc: intră doar prin inbox. Citirea e CITIRE, nu efect extern; fluxurile cu adresă pusă
  de om trec prin colectorul cu apărări (SSRF, robots.txt, limite); cele două surse fixe au gazde fixe.
- **Fișa (12.5)**, pe reguli: semnalele cu subiecte asemănătoare se grupează; potrivirea cu nișa = câte
  cuvinte-cheie ale clientului apar (fără potrivire nu se scrie fișă); o singură sursă = „semnal slab”,
  cel puțin două = „confirmat”; subiectele sensibile sau tragice sunt excluse automat; riscul „drepturi”
  marchează conținutul altora (clipuri, rețele); valabilitate 7 zile [I].
- **Unghiul propus** este o ciornă deterministă pentru om (leagă subiectul de cuvântul-cheie potrivit).
  Formularea cu model (partea „L · T2” a lui C2) NU este construită aici.
- **Inbox (12.2):** un link lipit devine fișă (titlul și descrierea paginii, citite prin colector) și
  propunere de calendar (subiect, unghi, ziua propusă); intrarea din inbox trece în „folosită”. O observație
  fără link devine fișă din textul ei. Tot ce vine din pagini externe e tratat ca dată (12.8): nu ajunge în
  niciun prompt de aici.
"""

import datetime as dt
import html
import json
import re
import unicodedata
import uuid
import xml.etree.ElementTree as ET  # documentele cu DOCTYPE sunt refuzate înainte de parsare
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import Date, DateTime, Float, Text, func, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.config import get_settings
from app.db import sesiune_agentie, sesiune_tenant
from app.ids import new_id
from app.logging import get_logger
from app.operare import audit, motor

log = get_logger("app.cercetare.tendinte")
NUME = "cercetare.tendinte"
RSS_GOOGLE = "https://trends.google.com/trending/rss?geo=RO"
YOUTUBE_POPULARE = "https://www.googleapis.com/youtube/v3/videos"
VALABILITATE = dt.timedelta(days=7)  # [I]
MAX_ELEMENTE = 50  # pe sursă
MAX_OCTETI = 2_000_000
PRAG_ASEMANARE = 0.5
GAZDE_DREPTURI = ("youtube.com", "youtu.be", "tiktok.com", "instagram.com", "facebook.com")
# Rădăcini (fără diacritice) care exclud automat un subiect (12.5: sensibil sau tragic). Lista e de pornire.
# Subiecte excluse automat (12.5: sensibil sau tragic), fără diacritice. Rădăcinile lungi (cel puțin 6
# litere) se potrivesc ca început de cuvânt; formele scurte doar exact, ca „mort” să nu prindă „mortar”.
# Lista e de pornire: o excludere greșită costă o tendință sărită, o scăpare costă mai mult.
SENSIBILE = (
    "accident", "decedat", "tragedi", "tragic", "razboi", "atentat", "cutremur", "inundati", "incendi",
    "sinucid", "inmormant", "explozi", "victim", "epidemi", "pandemi", "terorist", "impuscat", "injunghiat",
    "deces", "decese", "mort", "morti", "mortii", "moarte", "moartea", "ucis", "ucisa", "ucisi", "crima",
    "crime", "viol", "violul", "doliu", "ranit", "raniti", "cancer",
)  # fmt: skip
CUVINTE_GOALE = frozenset(
    [
        "pentru",
        "care",
        "este",
        "sunt",
        "acest",
        "aceasta",
        "dintre",
        "despre",
        "dupa",
        "fara",
        "intre",
        "pana",
        "prin",
        "spre",
        "sau",
        "din",
        "cum",
        "mai",
        "fost",
        "cand",
        "unde",
        "ceea",
        "doar",
        "chiar",
        "foarte",
        "the",
        "and",
        "with",
        "from",
    ]
)


class Baza(DeclarativeBase):
    pass


class ProfilTendinte(Baza):
    __tablename__ = "tendinte_profil"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    termeni: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    fluxuri: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    actualizat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FisaTendinta(Baza):
    __tablename__ = "fise_tendinta"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    zi: Mapped[dt.date] = mapped_column(Date)
    cheie: Mapped[str] = mapped_column(Text)
    subiect: Mapped[str] = mapped_column(Text)
    origine: Mapped[str] = mapped_column(Text)
    dovezi: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    prima_aparitie: Mapped[dt.date] = mapped_column(Date)
    scor_nisa: Mapped[float] = mapped_column(Float)
    termeni_potriviti: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    semnal: Mapped[str] = mapped_column(Text)
    risc: Mapped[str] = mapped_column(Text)
    unghi: Mapped[str] = mapped_column(Text, default="")
    valabil_pana: Mapped[dt.date] = mapped_column(Date)
    stare: Mapped[str] = mapped_column(Text, default="noua")
    propunere: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    inbox_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProfilInvalid(ValueError):
    pass


@dataclass(frozen=True)
class Semnal:
    """Un subiect văzut într-o sursă."""

    subiect: str
    sursa: str  # „google_tendinte”, „youtube”, „rss:<gazda>”, „inbox”
    url: str = ""
    titlu: str = ""
    la: dt.date | None = None


# --- nuclee pure ----------------------------------------------------------------------------------------
def norm(text: str) -> str:
    """Litere mici, fără diacritice, doar litere, cifre și spații."""
    fara = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", fara).strip()


def cuvinte(text: str) -> frozenset[str]:
    return frozenset(c for c in norm(text).split() if len(c) >= 4 and c not in CUVINTE_GOALE)


def sensibil(text: str) -> bool:
    return any(c == r or (len(r) >= 6 and c.startswith(r)) for c in norm(text).split() for r in SENSIBILE)


def _aceeasi_radacina(cuvant: str, termen: str) -> bool:
    """Româna flexionează („cafea”, „cafelei”, „cafenea”): două cuvinte se potrivesc dacă au același început,
    pe toată lungimea termenului minus două litere (cel puțin patru). Sub patru litere, doar exact."""
    if len(termen) < 4:
        return cuvant == termen
    n = max(4, len(termen) - 2)
    return cuvant[:n] == termen[:n]


def potrivire(text: str, termeni: list[str]) -> tuple[float, list[str]]:
    """Potrivirea cu nișa: cuvintele-cheie ale clientului care apar în text (după rădăcină; un termen din
    mai multe cuvinte cere toate cuvintele). Scorul crește cu numărul lor și se oprește la 1,0 de la trei."""
    cuv = norm(text).split()
    gasiti = [
        t
        for t in termeni
        if (parti := norm(t).split()) and all(any(_aceeasi_radacina(c, p) for c in cuv) for p in parti)
    ]
    return (min(1.0, round(len(gasiti) / 3, 2)), gasiti)


def asemanare(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def grupeaza(semnale: list[Semnal]) -> list[list[Semnal]]:
    """Semnalele cu subiecte asemănătoare (cuvinte comune) ajung în același grup (lacom)."""
    grupuri: list[tuple[frozenset[str], list[Semnal]]] = []
    for s in semnale:
        c = cuvinte(s.subiect)
        for i, (cg, lista) in enumerate(grupuri):
            if asemanare(c, cg) >= PRAG_ASEMANARE or (
                norm(s.subiect) and norm(s.subiect) == norm(lista[0].subiect)
            ):
                lista.append(s)
                grupuri[i] = (cg | c, lista)
                break
        else:
            grupuri.append((c, [s]))
    return [g for _, g in grupuri]


def risc(grup: list[Semnal]) -> str:
    text = " ".join(f"{s.subiect} {s.titlu}" for s in grup)
    if sensibil(text):
        return "sensibil"
    gazde = [(urlsplit(s.url).hostname or "").lower() for s in grup if s.url]
    return (
        "drepturi" if any(g == d or g.endswith("." + d) for g in gazde for d in GAZDE_DREPTURI) else "scazut"
    )


def unghi_ciorna(subiect: str, termeni: list[str]) -> str:
    if not termeni:
        return ""
    return f"Ciornă: leagă „{subiect[:120]}” de „{termeni[0]}”: ce înseamnă pentru clienții tăi."


@dataclass(frozen=True)
class Fisa:
    """Fișa calculată, înainte de scriere."""

    cheie: str
    subiect: str
    dovezi: list[dict[str, Any]]
    prima_aparitie: dt.date
    scor_nisa: float
    termeni_potriviti: list[str]
    semnal: str
    risc: str
    unghi: str


def fise_din_semnale(semnale: list[Semnal], termeni: list[str], zi: dt.date) -> list[Fisa]:
    """Nucleu pur (12.5). Fără potrivire cu nișa nu iese fișă; subiectele sensibile ies marcate, ca excluderea
    să lase urmă."""
    out: list[Fisa] = []
    for grup in grupeaza(semnale):
        text = " ".join(f"{s.subiect} {s.titlu}" for s in grup)
        scor, gasiti = potrivire(text, termeni)
        if scor <= 0:
            continue
        surse = {s.sursa for s in grup}
        r = risc(grup)
        subiect = grup[0].subiect.strip()[:300]
        out.append(
            Fisa(
                cheie=norm(subiect)[:200] or "fara-subiect",
                subiect=subiect,
                dovezi=[
                    {"sursa": s.sursa, "titlu": (s.titlu or s.subiect)[:300], "url": s.url[:500]}
                    for s in grup[:10]
                ],
                prima_aparitie=min((s.la for s in grup if s.la), default=zi),
                scor_nisa=scor,
                termeni_potriviti=gasiti,
                semnal="confirmat" if len(surse) >= 2 else "slab",
                risc=r,
                unghi="" if r == "sensibil" else unghi_ciorna(subiect, gasiti),
            )
        )
    return sorted(out, key=lambda f: (f.semnal != "confirmat", -f.scor_nisa, f.subiect))


# --- citirea surselor -----------------------------------------------------------------------------------
def _text(nod: ET.Element | None) -> str:
    return html.unescape((nod.text or "").strip()) if nod is not None else ""


def _data(text: str) -> dt.date | None:
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return dt.datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def din_rss(corp: bytes, sursa: str) -> list[Semnal]:
    """RSS 2.0 sau Atom → semnale (titlul e subiectul). Un document cu DOCTYPE sau entități proprii e refuzat
    (apărare de expansiune); un document stricat dă listă goală."""
    if len(corp) > MAX_OCTETI or b"<!DOCTYPE" in corp[:4096].upper() or b"<!ENTITY" in corp.upper():
        return []
    try:
        radacina = ET.fromstring(corp)  # noqa: S314
    except ET.ParseError:
        return []
    out: list[Semnal] = []
    for el in radacina.iter():
        nume = el.tag.rsplit("}", 1)[-1]
        if nume not in ("item", "entry"):
            continue
        copii = {c.tag.rsplit("}", 1)[-1]: c for c in el}
        titlu = _text(copii.get("title"))
        if not titlu:
            continue
        leg = copii.get("link")
        url = (_text(leg) or (leg.get("href", "") if leg is not None else "")) if leg is not None else ""
        la = _data(
            _text(copii.get("pubDate")) or _text(copii.get("updated")) or _text(copii.get("published"))
        )
        out.append(Semnal(titlu[:300], sursa, url if url.startswith("http") else "", titlu[:300], la))
        if len(out) >= MAX_ELEMENTE:
            break
    return out


def din_youtube(corp: bytes) -> list[Semnal]:
    """`videos.list?chart=mostPopular` → semnale (titlul clipului)."""
    try:
        elemente = json.loads(corp).get("items") or []
    except (ValueError, AttributeError):
        return []
    out = []
    for e in elemente[:MAX_ELEMENTE]:
        s = e.get("snippet") or {}
        titlu, vid = str(s.get("title") or "").strip(), str(e.get("id") or "")
        if titlu and vid:
            la = _data(str(s.get("publishedAt") or ""))
            out.append(
                Semnal(titlu[:300], "youtube", f"https://www.youtube.com/watch?v={vid}", titlu[:300], la)
            )
    return out


def citeste_generale(transport: httpx.BaseTransport | None = None) -> list[Semnal]:
    """Sursele comune tuturor clienților, citite o dată pe rulare. O sursă căzută nu oprește restul."""
    s = get_settings()
    out: list[Semnal] = []
    with httpx.Client(transport=transport, timeout=15.0, headers={"User-Agent": s.colector_user_agent}) as c:
        try:
            r = c.get(RSS_GOOGLE)
            if r.status_code == 200:
                out += din_rss(r.content, "google_tendinte")
        except httpx.HTTPError as exc:
            log.info("sursă necitită", extra={"sursa": "google_tendinte", "tip_eroare": type(exc).__name__})
        cheie = s.youtube_api_key.get_secret_value()
        if cheie:
            try:  # cheia pleacă în antet, nu în adresă (nu ajunge în jurnale)
                r = c.get(
                    YOUTUBE_POPULARE,
                    params={
                        "part": "snippet",
                        "chart": "mostPopular",
                        "regionCode": "RO",
                        "maxResults": "50",
                    },
                    headers={"X-Goog-Api-Key": cheie},
                )
                if r.status_code == 200:
                    out += din_youtube(r.content)
            except httpx.HTTPError as exc:
                log.info("sursă necitită", extra={"sursa": "youtube", "tip_eroare": type(exc).__name__})
    return out


def citeste_url(url: str) -> bytes:
    """O adresă pusă de om (flux, link din inbox), prin colectorul cu apărări (SSRF, robots, limite)."""
    from app.cercetare.descarcator import Descarcator

    d = Descarcator(get_settings().colector_user_agent, url)
    try:
        return d.ia_pagina(url).corp
    finally:
        d.inchide()


CititorUrl = Callable[[str], bytes]


def _flux(url: str, citeste: CititorUrl) -> list[Semnal]:
    try:
        return din_rss(citeste(url), "rss:" + (urlsplit(url).hostname or "necunoscut"))
    except Exception as exc:  # un flux căzut sau refuzat de apărări nu oprește restul
        log.info("flux necitit", extra={"tip_eroare": type(exc).__name__})
        return []


# --- profilul -------------------------------------------------------------------------------------------
def profil(db: Session, tenant_id: uuid.UUID) -> ProfilTendinte | None:
    return db.get(ProfilTendinte, tenant_id)


def seteaza_profil(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    termeni: list[str],
    fluxuri: list[str],
    utilizator_id: uuid.UUID | None,
) -> ProfilTendinte:
    t = list(dict.fromkeys(x.strip() for x in termeni if len(norm(x)) >= 3))
    f = list(dict.fromkeys(x.strip() for x in fluxuri if x.strip()))
    if len(t) > 40 or len(f) > 10:
        raise ProfilInvalid("cel mult 40 de cuvinte-cheie și 10 fluxuri")
    for url in f:
        p = urlsplit(url)
        if p.scheme not in ("http", "https") or not p.hostname or "." not in p.hostname or len(url) > 500:
            raise ProfilInvalid(f"flux nevalid: {url[:80]}")
    date = {"termeni": t, "fluxuri": f, "actualizat_la": dt.datetime.now(dt.UTC)}
    db.execute(
        pg_insert(ProfilTendinte)
        .values(tenant_id=tenant_id, **date)
        .on_conflict_do_update(index_elements=["tenant_id"], set_=date)
    )
    audit.record(
        db, "tendinte.profil_schimbat", obiect_tip="client", obiect_id=tenant_id, tenant_id=tenant_id,
        utilizator_id=utilizator_id, detalii={"termeni": len(t), "fluxuri": len(f)},
    )  # fmt: skip
    return db.execute(
        select(ProfilTendinte)
        .where(ProfilTendinte.tenant_id == tenant_id)
        .execution_options(populate_existing=True)
    ).scalar_one()


# --- scrierea fișelor -----------------------------------------------------------------------------------
def _scrie(db: Session, tenant_id: uuid.UUID, f: Fisa, zi: dt.date, **extra: Any) -> bool:
    r = db.execute(
        pg_insert(FisaTendinta)
        .values(
            id=new_id(),
            tenant_id=tenant_id,
            zi=zi,
            cheie=f.cheie,
            subiect=f.subiect,
            dovezi=f.dovezi,
            prima_aparitie=f.prima_aparitie,
            scor_nisa=f.scor_nisa,
            termeni_potriviti=f.termeni_potriviti,
            semnal=f.semnal,
            risc=f.risc,
            unghi=f.unghi,
            valabil_pana=zi + VALABILITATE,
            stare="exclusa" if f.risc == "sensibil" else "noua",
            **extra,
        )
        .on_conflict_do_nothing(constraint="fise_tendinta_unic")
        .returning(FisaTendinta.id)
    )
    return r.first() is not None


def ruleaza_client(
    tenant_id: uuid.UUID, zi: dt.date, generale: list[Semnal], *, citeste: CititorUrl = citeste_url
) -> int:
    """Fișele de azi ale unui client, din sursele generale și din fluxurile lui. Întoarce câte sunt noi."""
    with sesiune_tenant(tenant_id) as db:
        p = profil(db, tenant_id)
        if p is None or not p.termeni:
            return 0
        termeni, fluxuri = list(p.termeni), list(p.fluxuri)
    semnale = list(generale)
    for url in fluxuri:  # rețeaua, în afara tranzacției
        semnale += _flux(url, citeste)
    fise = fise_din_semnale(semnale, termeni, zi)
    with sesiune_tenant(tenant_id) as db:
        return sum(_scrie(db, tenant_id, f, zi, origine="surse") for f in fise)


TITLU = re.compile(rb"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
META = re.compile(
    rb"<meta[^>]+(?:property|name)=[\"'](?:og:title|og:description|description)[\"'][^>]+content=[\"']([^\"']*)[\"']",
    re.IGNORECASE,
)


def titlu_pagina(corp: bytes) -> str:
    """Titlul și descrierea unei pagini, ca text simplu (dată externă: doar se afișează, autoescape)."""
    bucati = [m.group(1) for m in (*TITLU.finditer(corp[:200_000]), *META.finditer(corp[:200_000]))]
    text = " · ".join(dict.fromkeys(html.unescape(b.decode("utf-8", "replace")).strip() for b in bucati))
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()[:300]


def urmatoarea_zi_lucratoare(zi: dt.date) -> dt.date:
    z = zi + dt.timedelta(days=1)
    while z.isoweekday() > 5:
        z += dt.timedelta(days=1)
    return z


def din_inbox(
    tenant_id: uuid.UUID, inbox_id: uuid.UUID, zi: dt.date, *, citeste: CititorUrl = citeste_url
) -> str:
    """O intrare din inboxul de tendințe devine fișă și propunere de calendar. Întoarce `fisa`, `exclusa`
    (subiect sensibil), `nimic` (intrarea nu mai e nouă)."""
    from app.media.modele import Tendinta

    with sesiune_tenant(tenant_id) as db:
        t = db.get(Tendinta, inbox_id)
        if t is None or t.stare != "noua":
            return "nimic"
        nota, url = t.text, t.url
        p = profil(db, tenant_id)
        termeni = list(p.termeni) if p else []
    titlu = ""
    if url:
        try:
            titlu = titlu_pagina(citeste(url))
        except Exception as exc:  # linkul necitit nu pierde observația omului
            log.info("link din inbox necitit", extra={"tip_eroare": type(exc).__name__})
    observatie = nota.replace(url or "", "").strip()
    subiect = (titlu or observatie or nota)[:300]
    semnal = Semnal(subiect, "inbox", url or "", titlu or observatie[:300], zi)
    scor, gasiti = potrivire(f"{subiect} {observatie}", termeni)
    r = risc([semnal, Semnal(observatie, "inbox")])
    fisa = Fisa(
        cheie=norm(subiect)[:200] or "fara-subiect",
        subiect=subiect,
        dovezi=[{"sursa": "inbox", "titlu": semnal.titlu, "url": semnal.url, "observatie": observatie[:500]}],
        prima_aparitie=zi,
        scor_nisa=scor,
        termeni_potriviti=gasiti,
        semnal="slab",  # o singură sursă (12.5), chiar dacă a ales-o un om
        risc=r,
        unghi="" if r == "sensibil" else (unghi_ciorna(subiect, gasiti) or f"Ciornă: {observatie[:200]}"),
    )
    propunere = None
    if r != "sensibil":
        propunere = {
            "subiect": subiect,
            "unghi": fisa.unghi,
            "zi": urmatoarea_zi_lucratoare(zi).isoformat(),
            "tip": "postare",
        }
    with sesiune_tenant(tenant_id) as db:
        _scrie(db, tenant_id, fisa, zi, origine="inbox", inbox_id=inbox_id, propunere=propunere)
        t = db.get(Tendinta, inbox_id)
        if t is not None:
            t.stare = "ignorata" if r == "sensibil" else "folosita"
    return "exclusa" if r == "sensibil" else "fisa"


def ruleaza(
    zi: dt.date | None = None, *, generale: list[Semnal] | None = None, citeste: CititorUrl = citeste_url
) -> dict[str, int]:
    """Rularea de dimineață peste toți clienții: fișele din surse și intrările noi din inbox."""
    from app.media.modele import Tendinta

    zi = zi or dt.datetime.now(dt.UTC).date()
    with sesiune_agentie() as db:
        clienti = list(db.execute(select(ProfilTendinte.tenant_id)).scalars())
        inbox = db.execute(select(Tendinta.tenant_id, Tendinta.id).where(Tendinta.stare == "noua")).all()
    semnale = citeste_generale() if generale is None else generale
    numar = {"fise": 0, "inbox": 0}
    for tenant_id in clienti:
        try:
            numar["fise"] += ruleaza_client(tenant_id, zi, semnale, citeste=citeste)
        except Exception as exc:
            log.warning("tendințe nerulate pentru un client", extra={"tip_eroare": type(exc).__name__})
    for tenant_id, inbox_id in inbox:
        try:
            numar["inbox"] += din_inbox(tenant_id, inbox_id, zi, citeste=citeste) == "fisa"
        except Exception as exc:
            log.warning("intrare din inbox neprelucrată", extra={"tip_eroare": type(exc).__name__})
    return numar


def ale_clientului(db: Session, tenant_id: uuid.UUID, *, limita: int = 50) -> list[FisaTendinta]:
    return list(
        db.execute(
            select(FisaTendinta)
            .where(FisaTendinta.tenant_id == tenant_id)
            .order_by(FisaTendinta.zi.desc(), FisaTendinta.semnal, FisaTendinta.scor_nisa.desc())
            .limit(limita)
        ).scalars()
    )


@motor.pas("cercetare.pas_tendinte")
def _pas() -> str:
    return str(ruleaza())


@motor.flux(NUME)
def flux(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _pas()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME, "10 6 * * *", flux)  # dimineața (12.7), în fusul afacerii


declara_programari()
