"""Conectorul „Site și blog” (F9.9, H6): articolul aprobat ajunge pe blogul agenției (pagini găzduite de
platformă) sau în CMS-ul clientului (WordPress, REST API v2).

- **Găzduit** (contul `gazduit`): blogul platformei (`site.blog.publica`), pe adresa articolului (slug). E
  idempotent pe slug; `verifica` caută slugul.
- **WordPress**: `POST /wp-json/wp/v2/posts` (titlu, conținut HTML, rezumat, slug, `status=publish`), cu o
parolă
  de aplicație (autentificare Basic) dată de client în panou și ținută criptat; site-ul e contul extern.
  `verifica`: `GET posts?slug=`. Parolele de aplicație nu expiră și nu au OAuth: se schimbă din panou.
- Limitele: un CMS propriu nu declară limite de publicare; sursa o spune.

# NEVERIFICAT: WordPress-ul real al unui client (versiune, module de securitate); API simulat.
"""

import base64
import html
import uuid
from typing import Any

import httpx

from app.connectors.contract import EfectDeTrimis, Limite, RezultatPlatforma, StarePostare, Token
from app.connectors.publicare.baza import ClientHttp, DepozitBaza, DepozitTokenuri, token_sau_autentificare
from app.operare.motor import EroareDefinitiva

GAZDUIT = "gazduit"


def html_articol(payload: dict[str, Any]) -> str:
    """Nucleu pur: corpul articolului (secțiuni, paragrafe, surse) ca HTML simplu, cu textul scăpat."""
    parti: list[str] = []
    for s in payload.get("corp", []):
        if s.get("titlu"):
            parti.append(f"<h2>{html.escape(str(s['titlu']))}</h2>")
        parti.extend(f"<p>{html.escape(str(p))}</p>" for p in s.get("paragrafe", []))
    surse = payload.get("surse") or []
    if surse:
        parti.append(
            "<h2>Surse</h2><ol>"
            + "".join(
                f'<li><a href="{html.escape(str(x["url"]))}" rel="nofollow">'
                f"{html.escape(str(x['titlu']))}</a></li>"
                for x in surse
            )
            + "</ol>"
        )
    return "\n".join(parti)


class ConectorBlog:
    canal = "blog"

    def __init__(
        self, *, depozit: DepozitTokenuri | None = None, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.depozit = depozit or DepozitBaza()
        self.transport = transport

    @classmethod
    def din_setari(cls) -> "ConectorBlog":
        return cls()

    def _token(self, tenant_id: uuid.UUID) -> Token:
        return token_sau_autentificare(self.depozit, tenant_id, self.canal)

    def _http(self, t: Token) -> ClientHttp:
        return ClientHttp(t.cont_extern.rstrip("/") + "/wp-json/wp/v2", self.transport)

    @staticmethod
    def _basic(t: Token) -> dict[str, str]:
        return {"Authorization": "Basic " + base64.b64encode(t.acces.encode()).decode()}

    # --- autorizare: nu există OAuth (găzduit: nimic; WordPress: parolă de aplicație din panou)
    # ---------------
    def url_autorizare(self, stare: str, redirect: str) -> str:
        raise EroareDefinitiva("blogul se configurează din panou (găzduit sau parolă de aplicație WordPress)")

    def schimba_cod(self, cod: str, redirect: str) -> Token:
        raise EroareDefinitiva("blogul nu folosește OAuth")

    def reimprospateaza(self, token: Token) -> Token:
        return token  # parolele de aplicație nu expiră

    # --- publicare ------------------------------------------------------------------------------------------
    def trimite(self, efect: EfectDeTrimis) -> RezultatPlatforma:
        t, p = self._token(efect.tenant_id), efect.payload
        if not p.get("slug") or not p.get("titlu") or not p.get("corp"):
            raise EroareDefinitiva("articolul nu are titlu, adresă sau corp")
        if t.cont_extern == GAZDUIT:
            return self._gazduit(p)
        r = self._http(t).cere(
            "POST",
            "posts",
            headers=self._basic(t),
            json={
                "title": p["titlu"],
                "content": html_articol(p),
                "excerpt": p.get("descriere", ""),
                "slug": p["slug"],
                "status": "publish",
            },
        )
        d = r.json()
        return RezultatPlatforma(str(d["id"]), str(d.get("link", "")))

    def _gazduit(self, p: dict[str, Any]) -> RezultatPlatforma:
        from app import site  # la execuție
        from app.config import get_settings
        from app.db import sesiune_agentie

        with sesiune_agentie() as db:
            a = site.blog.publica(
                db,
                titlu=str(p["titlu"]),
                descriere=str(p.get("descriere", "")),
                corp=p["corp"],
                surse=p.get("surse") or [],
                cuvant_cheie=str(p.get("subiect", "")),
                slug=str(p["slug"]),
            )
            slug = a.slug
        return RezultatPlatforma(slug, f"{get_settings().site_url.rstrip('/')}/blog/{slug}")

    def verifica(self, efect: EfectDeTrimis) -> RezultatPlatforma | None:
        t, slug = self._token(efect.tenant_id), str(efect.payload.get("slug", ""))
        if t.cont_extern == GAZDUIT:
            from app import site
            from app.config import get_settings
            from app.db import sesiune_agentie

            with sesiune_agentie() as db:
                a = site.blog.dupa_slug(db, slug)
                gasit = a is not None and a.titlu == efect.payload.get("titlu")
            return (
                RezultatPlatforma(slug, f"{get_settings().site_url.rstrip('/')}/blog/{slug}")
                if gasit
                else None
            )
        d = (
            self._http(t)
            .cere("GET", "posts", headers=self._basic(t), params={"slug": slug, "status": "publish"})
            .json()
        )
        return RezultatPlatforma(str(d[0]["id"]), str(d[0].get("link", ""))) if d else None

    def stare(self, tenant_id: uuid.UUID, id_extern: str) -> StarePostare:
        t = self._token(tenant_id)
        if t.cont_extern == GAZDUIT:
            from app import site
            from app.db import sesiune_agentie

            with sesiune_agentie() as db:
                return (
                    StarePostare.PUBLICATA if site.blog.dupa_slug(db, id_extern) else StarePostare.INEXISTENTA
                )
        r = self._http(t).cere("GET", f"posts/{id_extern}", headers=self._basic(t), clasifica_erori=False)
        if r.status_code == 404:
            return StarePostare.INEXISTENTA
        return StarePostare.PUBLICATA if r.json().get("status") == "publish" else StarePostare.IN_PROCESARE

    def limite(self, tenant_id: uuid.UUID) -> Limite:
        self._token(tenant_id)
        return Limite("CMS propriu: fără limită de publicare declarată")
