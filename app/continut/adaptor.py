"""Adaptorul pe platformă (F6.5, E10, docs/05: „rescrie nativ pentru fiecare canal: lungime, hashtag-uri, apel
la acțiune”;
docs/15 §15.4: fiecare canal primește pachetul lui).

Din postarea-sursă care a trecut validarea, E10 (profilul `creatie`) scrie câte o variantă pe canal.
Lungimile-țintă pe
canal (`TINTE`, [I], mai stricte decât maximele G1, care rămân plasa de siguranță) se verifică DETERMINIST,
împreună cu
problemele de lungime ale G1 (`validare.probleme_structura`); o variantă în afara limitelor se cere încă o
dată, cu
instrucțiunea exactă; a doua ratare lasă canalul fără adaptare (raportat). Fiecare variantă bună devine un
livrabil nou
(același tip, același slot, brieful sursei cu canalul schimbat), legat în `adaptari`, scris de E10 și trimis
în
validare; de acolo merge pe lanțul obișnuit (reparație, aprobare).
"""

import uuid
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import creier, gateway, productie, validare
from app.continut import brief, calendar, editor, prompturi
from app.continut.modele import Adaptare, Brief
from app.ids import new_id
from app.operare.motor import Prioritate
from app.productie import Stare

COMPONENTA = "E10"
# [I] lungimi-țintă native (text în caractere, număr de hashtag-uri); maximele platformelor sunt în G1
# (structura.toml)
TINTE: dict[str, dict[str, int]] = {
    "facebook": {"text": 1500, "hashtaguri": 3},
    "instagram": {"text": 2200, "hashtaguri": 10},
    "linkedin": {"text": 3000, "hashtaguri": 3},
    "tiktok": {"text": 300, "hashtaguri": 5},
}
STARI_SURSA = frozenset({Stare.VALIDAT, Stare.ASTEAPTA_APROBARE, Stare.APROBAT})


class VariantaCanal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canal: str = Field(pattern=r"^[a-z][a-z0-9_]{1,39}$")
    text: str = Field(min_length=10, max_length=4000)
    hashtaguri: list[str] = Field(default_factory=list, max_length=30)


class Adaptari(gateway.Iesire):
    adaptari: list[VariantaCanal] = Field(min_length=1, max_length=6)


class AdaptareRefuzata(creier.RegulaCreier):
    """Sursa nu se poate adapta (fără conținut validat, canal necunoscut)."""


@dataclass
class Rezultat:
    livrabile: dict[str, uuid.UUID] = field(default_factory=dict)
    neadaptate: dict[str, list[str]] = field(default_factory=dict)  # canal → probleme


def probleme_lungime(canal: str, text: str, hashtaguri: list[str], tip: str = "postare") -> list[str]:
    """Nucleu pur: problemele de lungime ale unei variante (ținta nativă + limitele G1)."""
    t = TINTE[canal]
    probleme = []
    if len(text) > t["text"]:
        probleme.append(f"textul are {len(text)} de caractere; pe {canal} cel mult {t['text']}")
    if len(hashtaguri) > t["hashtaguri"]:
        probleme.append(f"{len(hashtaguri)} hashtag-uri; pe {canal} cel mult {t['hashtaguri']}")
    c = validare.Continut(versiune=1, text=text, campuri={"hashtaguri": hashtaguri})
    probleme += [
        p.instructiune
        for p in validare.probleme_structura(tip, canal, c)
        if p.regula in ("G1.peste_limita_canal", "G1.peste_recomandarea_canalului")
    ]
    return probleme


def ale_sursei(db: Session, sursa_id: uuid.UUID) -> list[Adaptare]:
    return list(
        db.execute(
            select(Adaptare).where(Adaptare.sursa_livrabil_id == sursa_id).order_by(Adaptare.canal)
        ).scalars()
    )


def _cere(
    db: Session, lv: productie.Livrabil, text: str, canale: list[str], indicatie: str
) -> tuple[dict[str, VariantaCanal], str]:
    r = gateway.apeleaza(
        db,
        prompt="continut.adapteaza@1",
        schema=Adaptari,
        tenant_id=lv.tenant_id,
        componenta="continut.adaptor",
        livrabil_id=lv.id,
        prioritate=Prioritate.P2,
        max_tokeni=2500,
        variabile={
            "canal_sursa": lv.canal,
            "text": text,
            "limite": "\n".join(f"- {c}: {TINTE[c]['text']} / {TINTE[c]['hashtaguri']}" for c in canale),
            "indicatie": indicatie,
        },
    )
    if not isinstance(r.iesire, Adaptari):
        raise TypeError("ieșirea nu respectă schema promptului")
    return {v.canal: v for v in r.iesire.adaptari if v.canal in canale}, r.model


def adapteaza(db: Session, sursa_id: uuid.UUID, canale: list[str] | None = None) -> Rezultat:
    """Variantele pe canal ale unei postări validate. Idempotent pe canal: un canal deja adaptat nu se mai
    cere."""
    sursa = productie.blocheaza(db, sursa_id)
    if Stare(sursa.stare) not in STARI_SURSA:
        raise AdaptareRefuzata("se adaptează doar o postare care a trecut validarea")
    b = brief.al_livrabilului(db, sursa.id)
    if b is None:
        raise AdaptareRefuzata("sursa nu are brief")
    tinta = [c for c in (canale or list(calendar.CANALE_CONTINUT)) if c != sursa.canal]
    necunoscute = [c for c in tinta if c not in TINTE]
    if necunoscute:
        raise AdaptareRefuzata("canale necunoscute: " + ", ".join(necunoscute))
    rez = Rezultat({a.canal: a.livrabil_id for a in ale_sursei(db, sursa.id)})
    de_facut = [c for c in tinta if c not in rez.livrabile]
    if not de_facut:
        return rez
    text = validare.continut.citeste(db, sursa.id).text
    prompturi.asigura()
    bune: dict[str, tuple[VariantaCanal, str]] = {}
    indicatie = ""
    for _ in range(2):
        variante, model = _cere(db, sursa, text, de_facut, indicatie)
        corecturi = []
        for c in de_facut:
            v = variante.get(c)
            if v is None:
                rez.neadaptate[c] = ["lipsește din răspuns"]
                corecturi.append(f"- {c}: lipsește; scrie varianta")
                continue
            curat = v.model_copy(
                update={"text": editor.editeaza(v.text), "hashtaguri": [h.lstrip("#") for h in v.hashtaguri]}
            )
            probleme = probleme_lungime(c, curat.text, curat.hashtaguri, sursa.tip)
            if probleme:
                rez.neadaptate[c] = probleme
                corecturi.append(f"- {c}: " + "; ".join(probleme))
            else:
                rez.neadaptate.pop(c, None)
                bune[c] = (curat, model)
        de_facut = [c for c in de_facut if c not in bune]
        if not de_facut:
            break
        indicatie = (
            "Corecturi pentru variantele de mai jos (scrie din nou doar aceste canale):\n"
            + "\n".join(corecturi)
        )
    for c, (v, model) in bune.items():
        rez.livrabile[c] = _livrabil(db, sursa, b, v, model)
    return rez


def _livrabil(db: Session, sursa: productie.Livrabil, b: Brief, v: VariantaCanal, model: str) -> uuid.UUID:
    lv = productie.creeaza(
        db,
        tenant_id=sursa.tenant_id,
        tip=sursa.tip,
        canal=v.canal,
        termen_la=sursa.termen_la,
        componenta=COMPONENTA,
    )
    db.add(
        Adaptare(
            id=new_id(),
            tenant_id=sursa.tenant_id,
            sursa_livrabil_id=sursa.id,
            livrabil_id=lv.id,
            canal=v.canal,
            model=model,
        )
    )
    db.add(
        Brief(
            id=new_id(),
            tenant_id=sursa.tenant_id,
            livrabil_id=lv.id,
            pachet_id=b.pachet_id,
            continut={**b.continut, "canal": v.canal, "adaptare_din": str(sursa.id)},
            model=b.model,
        )
    )
    db.flush()
    productie.muta(
        db, lv.id, Stare.PLANIFICAT, Stare.BRIEFAT, componenta=COMPONENTA, motiv="adaptare pe canal"
    )
    productie.muta(
        db, lv.id, Stare.BRIEFAT, Stare.IN_SCRIERE, componenta=COMPONENTA, motiv="adaptare pe canal"
    )
    propozitii = validare.propozitii(v.text)
    validare.continut.scrie(
        db,
        lv.id,
        text=v.text,
        campuri={"hook": propozitii[0] if propozitii else v.text[:100], "hashtaguri": v.hashtaguri},
        autor=COMPONENTA,
        model_autor=model,
    )
    productie.muta(
        db, lv.id, Stare.IN_SCRIERE, Stare.IN_VALIDARE, componenta=COMPONENTA, motiv="trimis la validare"
    )
    return lv.id
