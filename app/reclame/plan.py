"""Planificatorul media (F13.3, I1, docs/16 §16.3–16.4, §16.6–16.7).

Planul are: obiectivul, pagina de destinație, campaniile (structura: o campanie de scalare și, separat, o
campanie de test cu buget mic și egal pe variante), publicul, matricea de creativuri (o singură variabilă
testată),
măsurarea (schema UTM unică, evenimentul urmărit), plafoanele contului și criteriile de oprire.

`propune` construiește planul determinist din obiectiv, buget și unghiuri (D-008: regulile, nu un model,
împart banii). `verifica` e nucleul pur care îl judecă; un plan cu probleme nu se poate aproba. Aprobarea e a
omului.
"""

import datetime as dt
import re
import unicodedata
import uuid
from typing import Literal
from urllib.parse import urlencode, urlsplit

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.operare import audit
from app.reclame.modele import ContReclame, PlanMediaRand

PARTE_TEST = 0.2  # 20% din bugetul zilnic merge la testul creativ (16.6, 7.7)
ZILE_LUNA = 30
VARIABILE = ("hook", "oferta", "format", "public")


class CriteriiOprire(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cost_tinta_bani: int = Field(gt=0)
    multiplu_pierdere: float = Field(default=3.0, ge=1.5, le=10)  # oprire la CPR > 3 × ținta (16.4)
    afisari_minime: int = Field(default=1000, ge=100)
    clicuri_minime: int = Field(default=20, ge=1)
    ferestre_slabe: int = Field(default=2, ge=1, le=6)  # 16.9: două ferestre consecutive sub prag


class Masurare(BaseModel):
    model_config = ConfigDict(extra="forbid")
    utm_source: str
    utm_medium: str = "cpc"
    utm_campaign: str = Field(pattern=r"^[a-z0-9-]{3,60}$")
    eveniment: str = "lead"


class CampaniePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nume: str = Field(min_length=3, max_length=120)
    rol: Literal["scalare", "test"]
    buget_zilnic_bani: int = Field(gt=0)
    public: str = Field(min_length=3, max_length=300)
    variabila: Literal["hook", "oferta", "format", "public"] | None = None
    variante: list[str] = Field(default_factory=list, max_length=5)


class PlanMedia(BaseModel):
    model_config = ConfigDict(extra="forbid")
    obiectiv: Literal["lead", "trafic"]
    pagina_destinatie: str
    buget_lunar_bani: int = Field(gt=0)
    campanii: list[CampaniePlan] = Field(min_length=1, max_length=10)
    plafon_zilnic_bani: int
    plafon_lunar_bani: int
    plafon_campanie_bani: int
    criterii_oprire: CriteriiOprire
    masurare: Masurare

    @property
    def buget_zilnic_bani(self) -> int:
        return sum(c.buget_zilnic_bani for c in self.campanii)


class PlanRefuzat(ValueError):
    """Planul nu poate fi propus sau aprobat (problemele sunt în mesaj)."""


def slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:60] or "campanie"


def link_cu_utm(plan: PlanMedia, continut: str = "") -> str:
    """Pagina de destinație cu schema UTM unică a planului (16.7)."""
    m = plan.masurare
    q = {"utm_source": m.utm_source, "utm_medium": m.utm_medium, "utm_campaign": m.utm_campaign}
    if continut:
        q["utm_content"] = slug(continut)
    sep = "&" if urlsplit(plan.pagina_destinatie).query else "?"
    return plan.pagina_destinatie + sep + urlencode(q)


def verifica(plan: PlanMedia) -> list[str]:
    """Nucleu pur: problemele planului. Listă goală = planul trece verificarea."""
    p: list[str] = []
    u = urlsplit(plan.pagina_destinatie)
    if u.scheme != "https" or not u.netloc:
        p.append("pagina de destinație trebuie să fie o adresă https")
    nume = [c.nume for c in plan.campanii]
    if len(nume) != len(set(nume)):
        p.append("două campanii au același nume")
    if not any(c.rol == "scalare" for c in plan.campanii):
        p.append("planul nu are o campanie de scalare")
    for c in plan.campanii:
        if c.buget_zilnic_bani > plan.plafon_campanie_bani:
            p.append(f"„{c.nume}”: bugetul zilnic trece de plafonul pe campanie")
        if c.rol == "test":
            if c.variabila is None or not 2 <= len(c.variante) <= 3:
                p.append(f"„{c.nume}”: testul are o singură variabilă și 2–3 variante")
            elif len(set(c.variante)) != len(c.variante):
                p.append(f"„{c.nume}”: variantele testului se repetă")
        elif c.variabila is not None or c.variante:
            p.append(f"„{c.nume}”: doar campania de test are variante")
    if plan.buget_zilnic_bani > plan.plafon_zilnic_bani:
        p.append("suma bugetelor zilnice trece de plafonul zilnic")
    if plan.buget_zilnic_bani * ZILE_LUNA > min(plan.plafon_lunar_bani, plan.buget_lunar_bani):
        p.append("bugetul pe 30 de zile trece de plafonul lunar sau de bugetul aprobat")
    co = plan.criterii_oprire
    if co.cost_tinta_bani * co.multiplu_pierdere > plan.buget_lunar_bani:
        p.append("pragul de oprire la pierdere e mai mare decât tot bugetul: oprirea n-ar veni niciodată")
    if plan.masurare.utm_source not in ("meta", "google", "tiktok"):
        p.append("sursa UTM trebuie să fie platforma (meta, google sau tiktok)")
    return p


def construieste(
    cont: ContReclame,
    *,
    obiectiv: Literal["lead", "trafic"],
    pagina_destinatie: str,
    buget_lunar_bani: int,
    public: str,
    cost_tinta_bani: int,
    unghiuri: list[str],
    nume: str,
) -> PlanMedia:
    """Planul determinist: bugetul zilnic = bugetul lunar / 30 (în limita plafonului zilnic), 80% scalare,
    20% test egal pe 2–3 unghiuri (variabila „hook”)."""
    zilnic = min(buget_lunar_bani // ZILE_LUNA, cont.plafon_zilnic_bani)
    test = int(zilnic * PARTE_TEST) if len(unghiuri) >= 2 else 0
    campanii = [
        CampaniePlan(nume=f"{nume} · scalare", rol="scalare", buget_zilnic_bani=zilnic - test, public=public)
    ]
    if test:
        campanii.append(
            CampaniePlan(
                nume=f"{nume} · test",
                rol="test",
                buget_zilnic_bani=test,
                public=public,
                variabila="hook",
                variante=unghiuri[:3],
            )
        )
    return PlanMedia(
        obiectiv=obiectiv,
        pagina_destinatie=pagina_destinatie,
        buget_lunar_bani=buget_lunar_bani,
        campanii=campanii,
        plafon_zilnic_bani=cont.plafon_zilnic_bani,
        plafon_lunar_bani=cont.plafon_lunar_bani,
        plafon_campanie_bani=cont.plafon_campanie_bani,
        criterii_oprire=CriteriiOprire(cost_tinta_bani=cost_tinta_bani),
        masurare=Masurare(utm_source=cont.platforma, utm_campaign=slug(nume)),
    )


def salveaza(db: Session, cont: ContReclame, plan: PlanMedia) -> PlanMediaRand:
    """Salvează planul ca propunere, cu problemele găsite (rămâne vizibil, dar neaprobabil)."""
    r = PlanMediaRand(
        tenant_id=cont.tenant_id,
        cont_id=cont.id,
        continut=plan.model_dump(mode="json"),
        probleme=verifica(plan),
    )
    db.add(r)
    db.flush()
    audit.record(
        db,
        "reclame.plan_propus",
        obiect_tip="reclame_plan",
        obiect_id=r.id,
        tenant_id=cont.tenant_id,
        actor_tip="sistem",
        detalii={"probleme": len(r.probleme)},
    )
    return r


def propune(db: Session, cont_id: uuid.UUID, **parametri: object) -> PlanMediaRand:
    cont = db.get(ContReclame, cont_id)
    if cont is None:
        raise PlanRefuzat("cont inexistent")
    return salveaza(db, cont, construieste(cont, **parametri))  # type: ignore[arg-type]


def plan_din(r: PlanMediaRand) -> PlanMedia:
    return PlanMedia.model_validate(r.continut)


def decide(db: Session, plan_id: uuid.UUID, *, aprobat: bool, utilizator_id: uuid.UUID) -> PlanMediaRand:
    r = db.get(PlanMediaRand, plan_id)
    if r is None or r.stare != "propus":
        raise PlanRefuzat("planul nu mai așteaptă o decizie")
    if aprobat:
        cont = db.get(ContReclame, r.cont_id)
        plan = plan_din(r)
        if cont is not None:  # plafoanele contului se pot fi schimbat între timp: se verifică pe cele de acum
            plan = plan.model_copy(
                update={
                    "plafon_zilnic_bani": cont.plafon_zilnic_bani,
                    "plafon_lunar_bani": cont.plafon_lunar_bani,
                    "plafon_campanie_bani": cont.plafon_campanie_bani,
                }
            )
        probleme = verifica(plan)
        if probleme:
            raise PlanRefuzat("; ".join(probleme))
    r.stare, r.decis_de, r.decis_la = (
        ("aprobat" if aprobat else "respins"),
        utilizator_id,
        dt.datetime.now(dt.UTC),
    )
    audit.record(
        db,
        f"reclame.plan_{r.stare}",
        obiect_tip="reclame_plan",
        obiect_id=r.id,
        tenant_id=r.tenant_id,
        utilizator_id=utilizator_id,
    )
    return r


def ale_contului(db: Session, cont_id: uuid.UUID) -> list[PlanMediaRand]:
    q = select(PlanMediaRand).where(PlanMediaRand.cont_id == cont_id).order_by(PlanMediaRand.creat_la.desc())
    return list(db.execute(q).scalars())
