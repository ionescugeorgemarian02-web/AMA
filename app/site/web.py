"""Rutele site-ului public (F7.1, docs/19 §19.1): randate pe server, fără JavaScript, rapide pe telefon.

Site-ul stă sub `/site` în aplicație; pe VPS, domeniul public al agenției trimite rădăcina lui aici
(NEVERIFICAT: regula din proxy, la migrare). Adresele canonice și harta site-ului folosesc `AMA_SITE_URL`.
Cookie-uri: fără acord nu se pune nimic în afară de alegerea însăși; analiza numără vizitele doar cu acord."""

import datetime as dt
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app import db as baza
from app.config import get_settings
from app.conturi import csrf_prelogin, jeton_csrf_prelogin, seteaza_csrf_prelogin
from app.db import sesiune_agentie
from app.panou.sabloane import DIRECTOR
from app.site import analiza, blog, pagini

router = APIRouter(prefix="/site", tags=["site"])
templates = Jinja2Templates(directory=str(DIRECTOR))
UN_AN = 365 * 24 * 3600


def url_public(cale: str) -> str:
    return get_settings().site_url.rstrip("/") + ("/" + cale if cale else "/")


def randeaza(
    request: Request, sablon: str, cale: str, *, status: int = 200, **context: object
) -> HTMLResponse:
    """Randarea unei pagini publice: meniul, bannerul de acord și analiza (doar cu acord)."""
    acord = request.cookies.get(analiza.COOKIE)
    p = pagini.TOATE.get(cale)
    # Formularul de acord are CSRF dublu-trimis: jetonul (cookie esențial) se pune doar unde apare formularul.
    cu_formular = acord not in analiza.VALORI or cale == "legal/cookie-uri"
    jeton_banner = str(context.pop("csrf_token", "") or "") or (
        jeton_csrf_prelogin(request) if cu_formular else ""
    )
    r = templates.TemplateResponse(
        request,
        sablon,
        {
            "nume": pagini.NUME,
            "meniu": pagini.MENIU,
            "subsol": pagini.SUBSOL,
            "cale": cale,
            "canonic": url_public(cale),
            "site_url": url_public(""),
            "arata_banner": acord not in analiza.VALORI,
            "acord": acord,
            "p": p,
            "csrf_token": jeton_banner,
            **context,
        },
        status_code=status,
    )
    r.headers["Cache-Control"] = "private, max-age=60"
    r.headers["Vary"] = "Cookie"
    if jeton_banner:
        seteaza_csrf_prelogin(r, jeton_banner)
    if analiza.acord_analiza(acord) and status == 200:
        analiza.inregistreaza("/" + cale)
    return r


def _pagina(request: Request, cale: str) -> HTMLResponse:
    if cale not in pagini.TOATE:
        raise HTTPException(status_code=404, detail="Pagina nu există.")
    return randeaza(request, "site/pagina.html", cale)


@router.get("")
@router.get("/")
def acasa(request: Request) -> HTMLResponse:
    return randeaza(request, "site/pagina.html", "", acasa=True)


@router.get("/blog")
def lista_blog(request: Request) -> HTMLResponse:
    with sesiune_agentie() as db:
        articole = [(a.slug, a.titlu, a.descriere, a.publicat_la) for a in blog.publicate(db)]
    return randeaza(request, "site/blog.html", "blog", articole=articole)


@router.get("/blog/{slug}")
def articol(request: Request, slug: str) -> HTMLResponse:
    with sesiune_agentie() as db:
        a = blog.dupa_slug(db, slug)
        if a is None:
            raise HTTPException(status_code=404, detail="Articolul nu există.")
        date = {
            "titlu": a.titlu,
            "descriere": a.descriere,
            "corp": a.corp,
            "surse": a.surse,
            "publicat_la": a.publicat_la,
            "dezvaluire_ai": a.dezvaluire_ai,
        }
    return randeaza(request, "site/articol.html", f"blog/{slug}", a=date)


@router.get("/stare")
def stare(request: Request) -> HTMLResponse:
    try:
        baza.verifica_baza()
        functioneaza = True
    except Exception:  # starea publică nu arată detalii tehnice
        functioneaza = False
    return randeaza(request, "site/stare.html", "stare", functioneaza=functioneaza)


@router.get("/sitemap.xml")
def harta() -> Response:
    with sesiune_agentie() as db:
        articole = [(f"blog/{a.slug}", a.publicat_la) for a in blog.publicate(db, limita=1000)]
    azi = dt.datetime.now(dt.UTC).date().isoformat()
    intrari = [(url_public(c), azi) for c in pagini.CAI_SITEMAP] + [
        (url_public(c), (t or dt.datetime.now(dt.UTC)).date().isoformat()) for c, t in articole
    ]
    xml = "".join(f"<url><loc>{u}</loc><lastmod>{d}</lastmod></url>" for u, d in intrari)
    return Response(
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{xml}</urlset>',
        media_type="application/xml",
    )


@router.get("/robots.txt")
def robots() -> PlainTextResponse:
    return PlainTextResponse(f"User-agent: *\nAllow: /\nSitemap: {url_public('sitemap.xml')}\n")


def _inapoi_sigur(inapoi: str) -> str:
    p = urlsplit(inapoi)
    if p.scheme or p.netloc or not p.path.startswith("/site") or "//" in p.path:
        return "/site"
    return p.path


@router.post("/consimtamant", dependencies=[Depends(csrf_prelogin)])
def consimtamant(alege: Annotated[str, Form()], inapoi: Annotated[str, Form()] = "/site") -> Response:
    """Alegerea privind cookie-urile (se poate schimba oricând din pagina Cookie-uri)."""
    if alege not in analiza.VALORI:
        raise HTTPException(status_code=422, detail="Alegere necunoscută.")
    r = RedirectResponse(_inapoi_sigur(inapoi), status_code=303)
    r.set_cookie(
        analiza.COOKIE,
        alege,
        max_age=UN_AN,
        httponly=True,
        samesite="lax",
        secure=get_settings().cookie_secure,
    )
    return r


@router.get("/{cale:path}")
def pagina_statica(request: Request, cale: str) -> HTMLResponse:
    return _pagina(request, cale.strip("/"))
