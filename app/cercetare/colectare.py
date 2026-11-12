"""Colectorul de surse, serviciul (F4.2, docs/12 §12.3). Pașii fluxului durabil stau în `fluxuri.py`.

Ciclul: o sursă (`creeaza_sursa`) → o colectare (`porneste_colectare`) → frontiera de adrese în
`colectari_pagini` →
pagini citite una câte una (`proceseaza_lot`) → documente (text în bază, original pe disc) → `incheie`.
Frontiera stă în bază, deci o colectare întreruptă continuă de unde a rămas; contoarele se recalculează din
pagini (nu se incrementează), deci reluarea unui pas nu le strică. Re-colectarea (`If-None-Match` /
`If-Modified-Since`, apoi hash) nu rescrie ce nu s-a schimbat.

Textul colectat este CONȚINUT EXTERN (12.8): oriunde intră într-un prompt trece prin `ca_continut_extern`
(`gateway.marcheaza_extern`). Colectorul nu trimite formulare și nu folosește autentificare.
"""

import datetime as dt
import ipaddress
import logging
import re
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from typing import Any

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app import gateway
from app.cercetare import html_text, ssrf, stocare
from app.cercetare import statut as statut
from app.cercetare.descarcator import Descarcator, Limite, Raspuns, Sarit
from app.cercetare.modele import Colectare, Document, PaginaColectata, SursaColectare
from app.cercetare.url_utile import (
    acelasi_domeniu,
    este_pagina_probabila,
    normalizeaza,
    rezolva_link,
    suspect_de_capcana,
)
from app.config import get_settings
from app.db import sesiune_tenant
from app.ids import new_id
from app.operare import audit

log = logging.getLogger("app.cercetare")

LOT = 5  # pagini într-un pas al fluxului
TEXT_MINIM = 30  # caractere: sub atât, pagina nu are text de păstrat
RETINERE_ZILE = 90  # documentele din exterior (docs/20 §20.4)
MAXIM_SARITE_EXTERNE = 20  # linkuri spre alte domenii păstrate ca rânduri (restul doar numărate)
MOTIVE = {
    "robots_interzis": "interzis de robots.txt",
    "alt_domeniu": "alt domeniu decât al sursei",
    "redirect_alt_domeniu": "redirecționare spre alt domeniu",
    "redirect_prea_multe": "prea multe redirecționări",
    "schema_nepermisa": "adresa nu e http / https",
    "url_invalid": "adresă invalidă",
    "url_cu_credentiale": "adresă cu nume și parolă",
    "port_nepermis": "port nepermis",
    "adresa_privata": "adresă privată sau internă (apărare SSRF)",
    "dns_esuat": "numele nu se rezolvă",
    "tip_continut": "tip de conținut nepermis",
    "prea_mare": "pagină prea mare",
    "autentificare": "cere autentificare sau interzice accesul",
    "lipsa": "pagina nu există (404 / 410)",
    "eroare_server": "eroare la server",
    "cod_neasteptat": "cod HTTP neașteptat",
    "limitat_de_server": "serverul cere să încetinim",
    "timeout": "timp depășit",
    "eroare_retea": "eroare de rețea",
    "meta_noindex": "pagina cere să nu fie indexată",
    "fara_text": "pagină fără text",
    "duplicat": "același text ca o pagină deja citită",
    "capcana_linkuri": "capcană de linkuri (cale repetitivă sau interogări fără sfârșit)",
    "limita_adancime": "dincolo de adâncimea permisă",
    "limita_pagini": "limita de pagini atinsă",
    "limita_octeti": "limita de octeți atinsă",
    "timp_epuizat": "timpul colectării a expirat",
    "server_suprasolicitat": "serverul a cerut repetat să încetinim",
    "robots_interzis_tot": "robots.txt interzice tot site-ul",
}
OPRIRI = ("limita_pagini", "limita_octeti", "timp_epuizat", "server_suprasolicitat")


class ColectareInvalida(ValueError):
    """Cererea nu poate fi pornită (sursă inexistentă sau de alt tip, format neacceptat …)."""


class FormatNeacceptat(ColectareInvalida):
    pass


# --- mediul de execuție (înlocuibil doar în teste)


@dataclass
class _Mediu:
    transport: httpx.BaseTransport | None = None
    rezolva: ssrf.Rezolvator = ssrf.rezolva_sistem
    exceptii_ssrf: frozenset[str] = frozenset()
    porturi: frozenset[int] = ssrf.PORTURI_IMPLICITE
    ceas: Callable[[], float] | None = None
    dormi: Callable[[float], None] | None = None


_mediu = _Mediu()
_descarcatoare: dict[uuid.UUID, Descarcator] = {}
_dupa_colectare: list[Callable[[uuid.UUID, uuid.UUID, uuid.UUID], None]] = []


def seteaza_mediu_test(
    *,
    transport: httpx.BaseTransport | None = None,
    rezolva: ssrf.Rezolvator | None = None,
    exceptii_ssrf: frozenset[str] = frozenset(),
    porturi: frozenset[int] | None = None,
    ceas: Callable[[], float] | None = None,
    dormi: Callable[[float], None] | None = None,
) -> None:
    """DOAR în mediul `test`: transport, DNS, porturi și ceas false, și excepția SSRF pentru serverul local
    fals.
    Altfel refuză (excepția SSRF nu poate exista în producție)."""
    if get_settings().env != "test":
        raise RuntimeError("mediul colectorului se schimbă doar în teste (AMA_ENV=test)")
    global _mediu
    _mediu = _Mediu(
        transport,
        rezolva or ssrf.rezolva_sistem,
        exceptii_ssrf,
        porturi or ssrf.PORTURI_IMPLICITE,
        ceas,
        dormi,
    )
    _descarcatoare.clear()


def reseteaza_mediu() -> None:
    global _mediu
    _mediu = _Mediu()
    for d in _descarcatoare.values():
        d.inchide()
    _descarcatoare.clear()


def dupa_colectare(callback: Callable[[uuid.UUID, uuid.UUID, uuid.UUID], None]) -> None:
    """Înregistrează o funcție `(tenant_id, sursa_id, colectare_id)` apelată la încheierea unei colectări
    (F4.3
    pune acolo indexarea). Idempotentă la înregistrare repetată."""
    if callback not in _dupa_colectare:
        _dupa_colectare.append(callback)


def user_agent() -> str:
    return get_settings().colector_user_agent


# --- surse


def creeaza_sursa(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    tip: str,
    statut_cod: str,
    nume: str,
    url: str | None = None,
    utilizator_id: uuid.UUID | None = None,
) -> SursaColectare:
    """O sursă nouă. Un `site` cere adresă și un statut care permite citirea automată (`statut.py`); o sursă
    `manual` cere un statut care acceptă încărcare manuală."""
    nume = nume.strip()
    if not nume or len(nume) > 200:
        raise ColectareInvalida("numele sursei: între 1 și 200 de caractere")
    if tip == "site":
        if not url:
            raise ColectareInvalida("un site cere o adresă")
        try:
            v = ssrf.valideaza_url(url, porturi=_mediu.porturi)
            if _este_ip(v.gazda):
                ssrf.adrese_sigure(v, exceptii=_mediu.exceptii_ssrf)  # adresă IP: se verifică direct
        except ssrf.UrlRefuzat as exc:
            raise ColectareInvalida(f"adresă nepermisă: {exc.cod}") from None
        statut.verifica_site(statut_cod, url)
        url = normalizeaza(url)
    elif tip == "manual":
        statut.verifica_manual(statut_cod)
        url = None
    else:
        raise ColectareInvalida("tipul sursei: site sau manual")
    s = SursaColectare(
        id=new_id(), tenant_id=tenant_id, tip=tip, statut=statut_cod, nume=nume, url_radacina=url,
        creat_de=utilizator_id,
    )  # fmt: skip
    db.add(s)
    db.flush()
    audit.record(
        db, "cercetare.sursa_creata", obiect_tip="sursa", obiect_id=s.id, utilizator_id=utilizator_id,
        tenant_id=tenant_id, detalii={"tip": tip, "statut": statut_cod},
    )  # fmt: skip
    return s


def _este_ip(gazda: str) -> bool:
    try:
        ipaddress.ip_address(gazda.strip("[]"))
    except ValueError:
        return False
    return True


def sursa(db: Session, sursa_id: uuid.UUID) -> SursaColectare:
    s = db.get(SursaColectare, sursa_id)
    if s is None:
        raise ColectareInvalida("sursa nu există")
    return s


def surse(db: Session, tenant_id: uuid.UUID) -> list[SursaColectare]:
    return list(
        db.execute(
            select(SursaColectare)
            .where(SursaColectare.tenant_id == tenant_id)
            .order_by(SursaColectare.creat_la)
        ).scalars()
    )


# --- pornirea unei colectări


def pregateste_colectare(
    db: Session, sursa_id: uuid.UUID, *, limite: Limite | None = None, utilizator_id: uuid.UUID | None = None
) -> Colectare:
    s = sursa(db, sursa_id)
    if s.tip != "site" or not s.activa:
        raise ColectareInvalida("doar un site activ se citește automat")
    statut.verifica_site(s.statut, s.url_radacina or "")
    c = Colectare(
        id=new_id(), tenant_id=s.tenant_id, sursa_id=s.id, limite=asdict(limite or Limite()),
        user_agent=user_agent(), creat_de=utilizator_id,
    )  # fmt: skip
    db.add(c)
    db.flush()
    audit.record(
        db, "cercetare.colectare_ceruta", obiect_tip="colectare", obiect_id=c.id, utilizator_id=utilizator_id,
        tenant_id=s.tenant_id, detalii={"sursa": s.id},
    )  # fmt: skip
    return c


def porneste_colectare(
    tenant_id: uuid.UUID,
    sursa_id: uuid.UUID,
    *,
    limite: Limite | None = None,
    utilizator_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Creează colectarea (tranzacție proprie, încheiată) și o pune în coada `io`. Întoarce `colectare_id`."""
    from app.cercetare import fluxuri

    with sesiune_tenant(tenant_id, utilizator_id) as db:
        c = pregateste_colectare(db, sursa_id, limite=limite, utilizator_id=utilizator_id)
        colectare_id = c.id
    fluxuri.trimite(tenant_id, colectare_id)
    return colectare_id


def _limite(c: Colectare) -> Limite:
    campuri = {k: v for k, v in c.limite.items() if k in Limite.__dataclass_fields__}
    return replace(Limite(), **campuri)


def _descarcator(c: Colectare, radacina: str) -> Descarcator:
    d = _descarcatoare.get(c.id)
    if d is None:
        extra: dict[str, Any] = {}
        if _mediu.ceas is not None:
            extra["ceas"] = _mediu.ceas
        if _mediu.dormi is not None:
            extra["dormi"] = _mediu.dormi
        d = Descarcator(
            user_agent=c.user_agent, radacina=radacina, limite=_limite(c), transport=_mediu.transport,
            rezolva=_mediu.rezolva, exceptii_ssrf=_mediu.exceptii_ssrf, porturi=_mediu.porturi, **extra,
        )  # fmt: skip
        _descarcatoare[c.id] = d
    return d


# --- frontiera


def _adauga_pagina(
    db: Session, c: Colectare, url: str, adancime: int, gasit_din: str | None,
    *, stare: str = "in_asteptare", motiv: str = "",
) -> bool:  # fmt: skip
    r = db.execute(
        pg_insert(PaginaColectata)
        .values(
            id=new_id(), tenant_id=c.tenant_id, colectare_id=c.id, url=url, adancime=adancime,
            gasit_din=gasit_din, stare=stare, motiv=motiv,
            procesat_la=None if stare == "in_asteptare" else dt.datetime.now(dt.UTC),
        )
        .on_conflict_do_nothing(index_elements=["colectare_id", "url"])
    )  # fmt: skip
    return bool(r.rowcount)  # type: ignore[attr-defined]


def _numar_randuri(db: Session, c: Colectare) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(PaginaColectata).where(PaginaColectata.colectare_id == c.id)
        ).scalar_one()
    )


def _locuri_sitemap(text: str) -> list[str]:
    """Adresele `<loc>` dintr-un sitemap (regulă simplă, fără parser XML: nu are entități de expandat)."""
    return [
        re.sub(r"<!\[CDATA\[|\]\]>", "", m).strip()
        for m in re.findall(r"<loc>\s*(.*?)\s*</loc>", text, re.S | re.I)
    ]


def _sitemapuri(d: Descarcator, radacina: str, limita: int) -> list[str]:
    robots = d.robots(radacina)
    candidate = list(robots.sitemapuri)
    p = ssrf.valideaza_url(radacina, porturi=_mediu.porturi)
    implicit = f"{p.schema}://{p.gazda}:{p.port}/sitemap.xml"
    if implicit not in candidate and normalizeaza(implicit) not in {normalizeaza(x) for x in candidate}:
        candidate.append(implicit)
    gasite: list[str] = []
    de_vizitat = candidate[:3]
    vizitate = 0
    while de_vizitat and vizitate < 6 and len(gasite) < limita:
        url = de_vizitat.pop(0)
        vizitate += 1
        try:
            r = d.ia_sitemap(url)
        except (Sarit, ssrf.UrlRefuzat):
            continue
        for loc in _locuri_sitemap(html_text.decodeaza(r.corp, r.content_type)):
            if loc.lower().split("?")[0].endswith(".xml") and len(de_vizitat) < 3:
                de_vizitat.append(loc)  # sitemap de sitemapuri: un singur nivel de coborâre
            else:
                gasite.append(loc)
    return gasite[:limita]


def initializeaza(tenant_id: uuid.UUID, colectare_id: uuid.UUID) -> str:
    """Pasul 1: marchează colectarea în curs și pune în frontieră rădăcina, adresele deja cunoscute (re-
    colectare) și
    cele din sitemap. Idempotent."""
    with sesiune_tenant(tenant_id) as db:
        c = _colectare(db, colectare_id)
        s = sursa(db, c.sursa_id)
        radacina = s.url_radacina or ""
        if c.inceput_la is None:
            c.inceput_la = dt.datetime.now(dt.UTC)
        c.stare = "in_curs"
        db.flush()
        _adauga_pagina(db, c, normalizeaza(radacina), 0, None)
        cunoscute = db.execute(
            select(Document.url).where(Document.sursa_id == s.id, Document.url.is_not(None)).limit(500)
        ).scalars()
        limite = _limite(c)
        for u in cunoscute:
            if u:
                _adauga_pagina(db, c, u, 1, None)
    d = _descarcator(c, radacina)
    try:
        locuri = _sitemapuri(d, radacina, limite.max_url_sitemap)
    except Exception as exc:  # sitemap-ul e un ajutor; fără el, colectarea merge pe linkuri
        log.warning("sitemap nelizibil", extra={"tip_eroare": type(exc).__name__}, exc_info=True)
        locuri = []
    with sesiune_tenant(tenant_id) as db:
        c = _colectare(db, colectare_id)
        gazda = ssrf.valideaza_url(radacina, porturi=_mediu.porturi).gazda
        for loc in locuri:
            try:
                u = normalizeaza(loc)
                if acelasi_domeniu(ssrf.valideaza_url(u, porturi=_mediu.porturi).gazda, gazda):
                    _adauga_pagina(db, c, u, 1, "sitemap")
            except ssrf.UrlRefuzat:
                continue
        _recalculeaza(db, c)
    return "initializat"


def _colectare(db: Session, colectare_id: uuid.UUID) -> Colectare:
    c = db.get(Colectare, colectare_id)
    if c is None:
        raise ColectareInvalida("colectarea nu există")
    return c


# --- citirea paginilor


def proceseaza_lot(tenant_id: uuid.UUID, colectare_id: uuid.UUID) -> str:
    """Pasul 2 (repetat): citește până la `LOT` pagini din frontieră. Întoarce `continua` sau `gata`."""
    with sesiune_tenant(tenant_id) as db:
        c = _colectare(db, colectare_id)
        radacina = sursa(db, c.sursa_id).url_radacina or ""
    d = _descarcator(c, radacina)
    limite = _limite(c)
    for _ in range(LOT):
        with sesiune_tenant(tenant_id) as db:
            c = _colectare(db, colectare_id)
            motiv = _motiv_oprire(db, c, limite)
            if motiv is not None:
                _opreste(db, c, motiv)
                return "gata"
            pagina = db.execute(
                select(PaginaColectata)
                .where(PaginaColectata.colectare_id == c.id, PaginaColectata.stare == "in_asteptare")
                .order_by(PaginaColectata.adancime, PaginaColectata.id)
                .limit(1)
            ).scalar_one_or_none()
            if pagina is None:
                return "gata"
            pid, url, adancime = pagina.id, pagina.url, pagina.adancime
            existent = db.execute(
                select(Document).where(Document.sursa_id == c.sursa_id, Document.url == url)
            ).scalar_one_or_none()
            conditii = (
                (existent.antete.get("etag"), existent.antete.get("last-modified"))
                if existent
                else (None, None)
            )
        try:
            raspuns = d.ia_pagina(url, etag=conditii[0], modificat=conditii[1])
            rezultat: tuple[Raspuns | None, Sarit | None] = (raspuns, None)
        except Sarit as exc:
            rezultat = (None, exc)
        except ssrf.UrlRefuzat as exc:
            rezultat = (None, Sarit(exc.cod, str(exc)))
        with sesiune_tenant(tenant_id) as db:
            _inregistreaza(db, _colectare(db, colectare_id), pid, url, adancime, rezultat, limite)
            _recalculeaza(db, _colectare(db, colectare_id), cereri=d.cereri)
    return "continua"


def _motiv_oprire(db: Session, c: Colectare, limite: Limite) -> str | None:
    if (
        c.inceput_la is not None
        and (dt.datetime.now(dt.UTC) - c.inceput_la).total_seconds() > limite.timp_total_sec
    ):
        return "timp_epuizat"
    prelucrate = int(
        db.execute(
            select(func.count())
            .select_from(PaginaColectata)
            .where(
                PaginaColectata.colectare_id == c.id,
                PaginaColectata.stare.in_(("citita", "nemodificata", "duplicat")),
            )
        ).scalar_one()
    )
    if prelucrate >= limite.max_pagini:
        return "limita_pagini"
    if c.octeti_cititi >= limite.max_octeti_total:
        return "limita_octeti"
    limitate = int(
        db.execute(
            select(func.count())
            .select_from(PaginaColectata)
            .where(PaginaColectata.colectare_id == c.id, PaginaColectata.motiv == "limitat_de_server")
        ).scalar_one()
    )
    return "server_suprasolicitat" if limitate >= 3 else None


def _opreste(db: Session, c: Colectare, motiv: str) -> None:
    db.execute(
        update(PaginaColectata)
        .where(PaginaColectata.colectare_id == c.id, PaginaColectata.stare == "in_asteptare")
        .values(stare="sarita", motiv=motiv, procesat_la=dt.datetime.now(dt.UTC))
    )
    c.motiv_oprire = motiv
    db.flush()
    _recalculeaza(db, c)


def _inregistreaza(
    db: Session,
    c: Colectare,
    pid: uuid.UUID,
    url: str,
    adancime: int,
    rezultat: tuple[Raspuns | None, Sarit | None],
    limite: Limite,
) -> None:
    pagina = db.get(PaginaColectata, pid)
    if pagina is None or pagina.stare != "in_asteptare":  # reluarea unui pas: pagina e deja înregistrată
        return
    acum = dt.datetime.now(dt.UTC)
    raspuns, sarit = rezultat
    pagina.procesat_la = acum
    if sarit is not None:
        pagina.stare = (
            "eroare"
            if sarit.cod in ("eroare_server", "eroare_retea", "timeout", "cod_neasteptat")
            else "sarita"
        )
        pagina.motiv = sarit.cod[:60]
        pagina.detaliu = str(sarit)[:300]
        pagina.cod_http = sarit.cod_http
        return
    assert raspuns is not None  # noqa: S101
    pagina.cod_http = raspuns.cod
    existent = db.execute(
        select(Document).where(Document.sursa_id == c.sursa_id, Document.url == url)
    ).scalar_one_or_none()
    if raspuns.cod == 304:
        pagina.stare = "nemodificata"
        if existent is not None:
            existent.verificat_la = acum
            pagina.document_id = existent.id
        return
    c.octeti_cititi += len(raspuns.corp)
    tip = raspuns.content_type.split(";")[0].strip().lower()
    text_brut = html_text.decodeaza(raspuns.corp, raspuns.content_type)
    if tip in ("text/html", "application/xhtml+xml"):
        pag = html_text.extrage(text_brut)
        if pag.noindex:
            pagina.stare, pagina.motiv = "sarita", "meta_noindex"
            return
        text, titlu = pag.text, pag.titlu
        linkuri = [] if pag.nofollow else pag.linkuri
    else:
        text, titlu, linkuri = _curata_text(text_brut), "", []
    if len(text) < TEXT_MINIM:
        pagina.stare, pagina.motiv = "sarita", "fara_text"
        return
    h_text = stocare.sha256(text.encode())
    h_continut = stocare.sha256(raspuns.corp)
    antete = {
        k: v for k, v in raspuns.antete.items() if k in ("etag", "last-modified", "content-type", "date")
    }
    antete["url_final"] = raspuns.url
    if existent is not None and existent.hash_continut == h_continut:
        existent.verificat_la = acum
        existent.antete = antete or existent.antete
        pagina.stare, pagina.document_id = "nemodificata", existent.id
    else:
        alt = db.execute(
            select(Document).where(Document.sursa_id == c.sursa_id, Document.hash_text == h_text)
        ).scalar_one_or_none()
        if alt is not None and (existent is None or alt.id != existent.id):
            pagina.stare, pagina.motiv, pagina.document_id = "duplicat", "duplicat", alt.id
        else:
            _, cale = stocare.scrie(c.tenant_id, c.sursa_id, raspuns.corp, tip)
            if existent is None:
                existent = Document(
                    id=new_id(), tenant_id=c.tenant_id, sursa_id=c.sursa_id, tip="pagina", url=url,
                    colectare_id=c.id, expira_la=acum + dt.timedelta(days=RETINERE_ZILE),
                )  # fmt: skip
                db.add(existent)
            else:
                existent.versiune += 1
                existent.colectare_id = c.id
            existent.titlu, existent.text, existent.hash_continut, existent.hash_text = (
                titlu,
                text,
                h_continut,
                h_text,
            )
            existent.content_type, existent.octeti, existent.cale_original = tip, len(raspuns.corp), cale
            existent.antete, existent.actualizat_la, existent.verificat_la = antete, acum, acum
            db.flush()
            pagina.stare, pagina.document_id = "citita", existent.id
    _descopera(db, c, url, adancime, linkuri, limite)


def _curata_text(t: str) -> str:
    t = unicodedata.normalize("NFC", t).replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _descopera(
    db: Session, c: Colectare, url: str, adancime: int, linkuri: list[str], limite: Limite
) -> None:
    gazda_radacina = ssrf.valideaza_url(url, porturi=_mediu.porturi).gazda
    max_randuri = limite.max_pagini * 5
    externe = 0
    for href in linkuri:
        abs_url = rezolva_link(url, href)
        if abs_url is None:
            continue
        try:
            u = normalizeaza(abs_url)
            v = ssrf.valideaza_url(u, porturi=_mediu.porturi)
        except ssrf.UrlRefuzat:
            c.linkuri_ignorate += 1
            continue
        if not este_pagina_probabila(u):
            continue
        if _numar_randuri(db, c) >= max_randuri:
            c.linkuri_ignorate += 1
            continue
        if not acelasi_domeniu(v.gazda, gazda_radacina):
            if externe < MAXIM_SARITE_EXTERNE and _adauga_pagina(
                db, c, u, adancime + 1, url, stare="sarita", motiv="alt_domeniu"
            ):
                externe += 1
            else:
                c.linkuri_ignorate += 1
            continue
        if suspect_de_capcana(u) or _prea_multe_variante(db, c, u, limite):
            _adauga_pagina(db, c, u, adancime + 1, url, stare="sarita", motiv="capcana_linkuri")
        elif adancime + 1 > limite.max_adancime:
            _adauga_pagina(db, c, u, adancime + 1, url, stare="sarita", motiv="limita_adancime")
        else:
            _adauga_pagina(db, c, u, adancime + 1, url)


def _prea_multe_variante(db: Session, c: Colectare, url: str, limite: Limite) -> bool:
    if "?" not in url:
        return False
    baza = url.split("?", 1)[0]
    n = db.execute(
        select(func.count())
        .select_from(PaginaColectata)
        .where(
            PaginaColectata.colectare_id == c.id,
            PaginaColectata.url.like(baza.replace("%", r"\%").replace("_", r"\_") + "?%", escape="\\"),
            PaginaColectata.url != url,
        )
    ).scalar_one()
    return int(n) >= limite.max_variante_interogare


def _recalculeaza(db: Session, c: Colectare, *, cereri: int | None = None) -> None:
    """Contoarele rezultă din paginile colectării: reluarea unui pas nu le poate strica."""
    rezultat = dict(
        db.execute(
            select(PaginaColectata.stare, func.count())
            .where(PaginaColectata.colectare_id == c.id)
            .group_by(PaginaColectata.stare)
        ).all()
    )
    c.pagini_gasite = sum(rezultat.values())
    c.pagini_citite = rezultat.get("citita", 0)
    c.pagini_sarite = rezultat.get("sarita", 0) + rezultat.get("eroare", 0)
    c.pagini_nemodificate = rezultat.get("nemodificata", 0)
    c.pagini_duplicate = rezultat.get("duplicat", 0)
    if cereri is not None:
        c.cereri_http = max(c.cereri_http, cereri)
    db.flush()


def incheie(tenant_id: uuid.UUID, colectare_id: uuid.UUID) -> str:
    """Pasul 3: starea finală, contoarele, eliberarea conexiunilor și anunțarea abonaților (F4.3)."""
    with sesiune_tenant(tenant_id) as db:
        c = _colectare(db, colectare_id)
        radacina = normalizeaza(sursa(db, c.sursa_id).url_radacina or "")
        pagina_radacina = db.execute(
            select(PaginaColectata).where(
                PaginaColectata.colectare_id == c.id, PaginaColectata.url == radacina
            )
        ).scalar_one_or_none()
        _recalculeaza(db, c)
        citite_total = c.pagini_citite + c.pagini_nemodificate + c.pagini_duplicate
        if pagina_radacina is not None and pagina_radacina.motiv == "robots_interzis" and citite_total == 0:
            c.motiv_oprire = "robots_interzis_tot"
            c.stare = "terminata"
        elif citite_total == 0:
            c.stare = "esuata"
            c.motiv_oprire = (pagina_radacina.motiv if pagina_radacina is not None else "") or "nimic_citit"
        else:
            c.stare = "terminata"
            c.motiv_oprire = c.motiv_oprire or "complet"
        c.sfarsit_la = dt.datetime.now(dt.UTC)
        sursa_id, stare = c.sursa_id, c.stare
        audit.record(
            db, "cercetare.colectare_incheiata", obiect_tip="colectare", obiect_id=c.id, tenant_id=tenant_id,
            detalii={
                "stare": stare,
                "citite": c.pagini_citite,
                "sarite": c.pagini_sarite,
                "motiv": c.motiv_oprire,
            },
        )  # fmt: skip
    d = _descarcatoare.pop(colectare_id, None)
    if d is not None:
        d.inchide()
    if stare == "terminata":
        for callback in list(_dupa_colectare):
            try:
                callback(tenant_id, sursa_id, colectare_id)
            except Exception as exc:  # un abonat stricat nu strică colectarea
                log.warning("abonat la colectare nereușit", extra={"tip_eroare": type(exc).__name__})
    return stare


# --- materiale încărcate manual


EXTENSII_TEXT = (".txt", ".md", ".markdown", ".text")
OCTETI_FISIER_MAXIM = 2_000_000
TEXT_MANUAL_MAXIM = 400_000


def _document_manual(
    db: Session, *, tenant_id: uuid.UUID, sursa_id: uuid.UUID, tip: str, titlu: str, text: str, corp: bytes,
    content_type: str, utilizator_id: uuid.UUID | None,
) -> tuple[Document, bool]:  # fmt: skip
    s = sursa(db, sursa_id)
    if s.tenant_id != tenant_id or s.tip != "manual":
        raise ColectareInvalida("materialele se încarcă doar într-o sursă manuală a clientului")
    text = _curata_text(text)
    if len(text) < 1:
        raise ColectareInvalida("textul e gol")
    if len(text) > TEXT_MANUAL_MAXIM:
        raise ColectareInvalida(f"textul depășește {TEXT_MANUAL_MAXIM} de caractere")
    h_text = stocare.sha256(text.encode())
    existent = db.execute(
        select(Document).where(Document.sursa_id == sursa_id, Document.hash_text == h_text)
    ).scalar_one_or_none()
    if existent is not None:
        return existent, False  # deduplicare: același text în aceeași sursă nu se păstrează de două ori
    h, cale = stocare.scrie(tenant_id, sursa_id, corp, content_type)
    d = Document(
        id=new_id(), tenant_id=tenant_id, sursa_id=sursa_id, tip=tip, url=None,
        titlu=titlu.strip()[:300], text=text,
        hash_continut=h, hash_text=h_text, content_type=content_type, octeti=len(corp), cale_original=cale,
        antete={}, creat_de=utilizator_id,
    )  # fmt: skip
    db.add(d)
    db.flush()
    audit.record(
        db, "cercetare.document_adaugat", obiect_tip="document", obiect_id=d.id, utilizator_id=utilizator_id,
        tenant_id=tenant_id, detalii={"tip": tip, "sursa": sursa_id},
    )  # fmt: skip
    return d, True


def adauga_text(
    db: Session, *, tenant_id: uuid.UUID, sursa_id: uuid.UUID, titlu: str, text: str,
    utilizator_id: uuid.UUID | None = None,
) -> tuple[Document, bool]:  # fmt: skip
    """Text lipit de un om. Întoarce (document, creat); `creat=False` dacă textul exista deja în sursă."""
    return _document_manual(
        db, tenant_id=tenant_id, sursa_id=sursa_id, tip="text_lipit", titlu=titlu, text=text,
        corp=text.encode(), content_type="text/plain", utilizator_id=utilizator_id,
    )  # fmt: skip


def adauga_fisier(
    db: Session, *, tenant_id: uuid.UUID, sursa_id: uuid.UUID, nume_fisier: str, continut: bytes,
    utilizator_id: uuid.UUID | None = None,
) -> tuple[Document, bool]:  # fmt: skip
    """Fișier text sau markdown (UTF-8). PDF-ul este AMÂNAT explicit: fără bibliotecă de extragere nu se
    acceptă (o extragere ieftină și sigură cere o dependență sau OCR local; vezi F4.2, „Ce nu se
    construiește”)."""
    nume = nume_fisier.strip().lower()
    if nume.endswith(".pdf") or continut[:5] == b"%PDF-":
        raise FormatNeacceptat(
            "PDF-urile nu se acceptă încă (extragerea de text din PDF este amânată); lipește textul"
        )
    if not nume.endswith(EXTENSII_TEXT):
        raise FormatNeacceptat("se acceptă doar fișiere .txt și .md")
    if len(continut) > OCTETI_FISIER_MAXIM:
        raise ColectareInvalida(f"fișierul depășește {OCTETI_FISIER_MAXIM} de octeți")
    if b"\x00" in continut:
        raise FormatNeacceptat("fișierul nu pare text")
    try:
        text = continut.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise FormatNeacceptat("fișierul trebuie să fie UTF-8") from None
    tip_continut = "text/markdown" if nume.endswith((".md", ".markdown")) else "text/plain"
    titlu = re.sub(r"\.[a-z]+$", "", nume_fisier.strip(), flags=re.IGNORECASE)[:300]
    return _document_manual(
        db, tenant_id=tenant_id, sursa_id=sursa_id, tip="fisier", titlu=titlu, text=text, corp=continut,
        content_type=tip_continut, utilizator_id=utilizator_id,
    )  # fmt: skip


# --- citire


def stare_colectare(db: Session, colectare_id: uuid.UUID) -> Colectare:
    return _colectare(db, colectare_id)


def pagini(db: Session, colectare_id: uuid.UUID, stare: str | None = None) -> list[PaginaColectata]:
    q = select(PaginaColectata).where(PaginaColectata.colectare_id == colectare_id)
    if stare:
        q = q.where(PaginaColectata.stare == stare)
    return list(db.execute(q.order_by(PaginaColectata.creat_la, PaginaColectata.id)).scalars())


def motive_sarire(db: Session, colectare_id: uuid.UUID) -> dict[str, int]:
    """De ce s-au sărit paginile: `{motiv: număr}`."""
    r = db.execute(
        select(PaginaColectata.motiv, func.count())
        .where(PaginaColectata.colectare_id == colectare_id, PaginaColectata.stare.in_(("sarita", "eroare")))
        .group_by(PaginaColectata.motiv)
    ).all()
    return {m or "necunoscut": int(n) for m, n in r}


def documente(db: Session, sursa_id: uuid.UUID) -> list[Document]:
    return list(
        db.execute(
            select(Document).where(Document.sursa_id == sursa_id).order_by(Document.colectat_la, Document.id)
        ).scalars()
    )


def document(db: Session, document_id: uuid.UUID) -> Document:
    d = db.get(Document, document_id)
    if d is None:
        raise ColectareInvalida("documentul nu există")
    return d


def ca_continut_extern(d: Document, *, max_caractere: int = 6000) -> str:
    """Textul documentului, pregătit pentru un prompt: marcat ca DATE, nu instrucțiuni (12.8). Singura cale
    prin care textul colectat intră într-un prompt."""
    sursa_text = "pagina" if d.tip == "pagina" else "fisier_client"
    return gateway.marcheaza_extern(d.text, sursa=sursa_text, max_caractere=max_caractere)


__all__ = [
    "ColectareInvalida",
    "FormatNeacceptat",
    "adauga_fisier",
    "adauga_text",
    "ca_continut_extern",
    "creeaza_sursa",
    "document",
    "documente",
    "dupa_colectare",
    "motive_sarire",
    "pagini",
    "porneste_colectare",
    "pregateste_colectare",
    "surse",
]
