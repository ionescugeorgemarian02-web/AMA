"""Brieful SEO, articolul în trei pași și lista on-page deterministă (F7.10, C6, E5, E7, docs/13, docs/19
§19.1).

1. Brieful SEO (determinist): cuvântul principal și secundarele grupului, intenția, sursele numerotate.
2. Articolul în trei pași, prin gateway: planul (E5), scrierea (E5), editarea (E7); apoi editorul determinist.
   Sursele se citează în text ca [1], [2] — doar sursele din brief.
3. Lista on-page (deterministă, `verifica_on_page`) și validarea (cascada deterministă,
`validare.independent`).
4. Articolul care trece amândouă se publică pe blogul agenției, cu sursele citate."""

import re
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app import continut, gateway, site
from app.db import sesiune_agentie
from app.operare import audit
from app.operare.motor import Prioritate
from app.seo.cuvinte import Grup, normal
from app.validare.independent import evalueaza_text

CITARE = re.compile(r"\[(\d{1,2})\]")
MIN_CUVINTE = 450  # [I]
MAX_DENSITATE = 0.03  # [I]


class SectiunePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    titlu: str = Field(min_length=5, max_length=90)
    idee: str = Field(min_length=10, max_length=400)


class PlanArticol(gateway.Iesire):
    titlu: str = Field(min_length=20, max_length=80)
    descriere: str = Field(min_length=60, max_length=200)
    sectiuni: list[SectiunePlan] = Field(min_length=3, max_length=7)


class SectiuneScrisa(BaseModel):
    model_config = ConfigDict(extra="forbid")
    titlu: str = Field(min_length=5, max_length=90)
    paragrafe: list[str] = Field(min_length=1, max_length=8)


class ArticolScris(gateway.Iesire):
    introducere: str = Field(min_length=40, max_length=1500)
    sectiuni: list[SectiuneScrisa] = Field(min_length=3, max_length=7)


def brief(g: Grup, surse: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "principal": g.principal,
        "secundare": g.cuvinte[1:6],
        "intentie": g.intentie,
        "surse": [
            {"nr": i + 1, "titlu": s["titlu"], "url": s["url"], "pasaj": s["pasaj"]}
            for i, s in enumerate(surse)
        ],
    }


def _surse_text(b: dict[str, Any]) -> str:
    return "\n".join(f"[{s['nr']}] {s['titlu']} ({s['url']}): {s['pasaj']}" for s in b["surse"])


def text_articol(a: dict[str, Any]) -> str:
    return "\n".join([a["introducere"], *(p for s in a["sectiuni"] for p in [s["titlu"], *s["paragrafe"]])])


def verifica_on_page(
    titlu: str, descriere: str, slug: str, a: dict[str, Any], b: dict[str, Any]
) -> list[str]:
    """Nucleu pur: problemele on-page (listă goală = trece)."""
    p = normal(b["principal"])
    probleme = []
    if not 30 <= len(titlu) <= 65 or p not in normal(titlu):
        probleme.append("titlul are 30–65 de caractere și conține cuvântul principal")
    if not 120 <= len(descriere) <= 160 or p not in normal(descriere):
        probleme.append("descrierea are 120–160 de caractere și conține cuvântul principal")
    if p.replace(" ", "-") not in slug:
        probleme.append("adresa conține cuvântul principal")
    if p not in normal(a["introducere"]):
        probleme.append("cuvântul principal apare în primul paragraf")
    if len(a["sectiuni"]) < 3:
        probleme.append("cel puțin 3 subtitluri")
    text = text_articol(a)
    cuvinte = normal(text).split()
    if len(cuvinte) < MIN_CUVINTE:
        probleme.append(f"cel puțin {MIN_CUVINTE} de cuvinte")
    aparitii = normal(text).count(p)
    if cuvinte and aparitii * len(p.split()) / len(cuvinte) > MAX_DENSITATE:
        probleme.append("cuvântul principal nu se repetă excesiv (≤ 3%)")
    citate = {int(n) for n in CITARE.findall(text)}
    numere = {s["nr"] for s in b["surse"]}
    if len(citate & numere) < 2:
        probleme.append("cel puțin 2 surse citate în text")
    if citate - numere:
        probleme.append("fiecare citare are o sursă în listă")
    return probleme


def _apel(
    db: Session, tenant_id: uuid.UUID, prompt: str, schema: type[gateway.Iesire], variabile: dict[str, Any]
) -> tuple[Any, str]:
    r = gateway.apeleaza(
        db,
        prompt=prompt,
        schema=schema,
        tenant_id=tenant_id,
        componenta=prompt.split("@")[0],
        prioritate=Prioritate.P3,
        max_tokeni=3000,
        variabile=variabile,
    )
    if not isinstance(r.iesire, schema):
        raise TypeError("ieșirea nu respectă schema")
    return r.iesire, r.model


def scrie(db: Session, tenant_id: uuid.UUID, g: Grup, surse: list[dict[str, str]]) -> dict[str, Any]:
    """Brieful, cei trei pași, lista on-page și validarea. Publică doar dacă trece tot."""
    continut.prompturi.asigura()
    b = brief(g, surse)
    var = {
        "principal": b["principal"],
        "secundare": ", ".join(b["secundare"]) or "—",
        "intentie": b["intentie"],
        "surse": _surse_text(b),
    }
    plan, _ = _apel(db, tenant_id, "seo.plan@1", PlanArticol, var)
    plan_text = "\n".join(f"- {s.titlu}: {s.idee}" for s in plan.sectiuni)
    ciorna, _ = _apel(
        db,
        tenant_id,
        "seo.scriere@1",
        ArticolScris,
        {"principal": b["principal"], "surse": var["surse"], "titlu": plan.titlu, "plan": plan_text},
    )
    editat, model = _apel(
        db,
        tenant_id,
        "seo.editare@1",
        ArticolScris,
        {"principal": b["principal"], "articol": text_articol(ciorna.model_dump())},
    )
    a = editat.model_dump()
    a["introducere"] = continut.editor.editeaza(a["introducere"])
    for s in a["sectiuni"]:
        s["paragrafe"] = [continut.editor.editeaza(x) for x in s["paragrafe"]]
    slug = site.blog.slug_din(plan.titlu)
    on_page = verifica_on_page(plan.titlu, plan.descriere, slug, a, b)
    # Citările [n] sunt trimiteri la surse, nu afirmații cu cifre: nu intră în textul validat.
    text_validat = CITARE.sub("", text_articol(a))
    rez = evalueaza_text(db, tenant_id, tip="articol", canal="blog", text=text_validat, model_autor=model)
    folosite = {int(n) for n in CITARE.findall(text_articol(a))}
    surse_citate = [{"titlu": s["titlu"], "url": s["url"]} for s in b["surse"] if s["nr"] in folosite]
    rezultat = {
        "titlu": plan.titlu,
        "slug": slug,
        "brief": b,
        "on_page": on_page,
        "validare": rez.trece,
        "blocante": rez.blocante(),
        "rulate": list(rez.rulate),
        "omise": list(rez.omise),
        "surse_citate": surse_citate,
        "publicat": False,
    }
    if not on_page and rez.trece:
        with sesiune_agentie() as adb:  # blogul e al agenției (site_articole: contextul de agenție)
            site.blog.publica(
                adb,
                titlu=plan.titlu,
                descriere=plan.descriere,
                slug=slug,
                cuvant_cheie=b["principal"],
                corp=[{"titlu": "", "paragrafe": [a["introducere"]]}, *a["sectiuni"]],
                surse=surse_citate,
            )
        rezultat["publicat"] = True
    audit.record(
        db,
        "seo.articol",
        obiect_tip="articol",
        tenant_id=tenant_id,
        actor_tip="sistem",
        detalii={"slug": slug, "publicat": rezultat["publicat"], "on_page": len(on_page)},
    )
    return rezultat
