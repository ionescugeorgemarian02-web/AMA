"""Site și blog (F9.9, H6, docs/15 §15.1): articolul din F7.10 ajunge pe blog prin aprobare și prin
executorul de efecte, ca orice publicare.

1. `pregateste`: articolul scris de F7.10 (`seo.articole.scrie(..., publica=False)`), care a trecut lista
on-page și
   validarea, devine livrabil `articol` pe canalul `blog`, cu conținutul lui (titlu, descriere, adresă, corp,
   surse citate, brieful), și cere aprobarea omului.
2. După aprobare, canalul `blog` (fără aprobare de la vreo platformă; contul: blogul găzduit al agenției sau
   WordPress-ul clientului) e automat: postarea se programează (F9.7) și pleacă la slot.
3. Chiar înainte de plecare, lista on-page se verifică din nou pe versiunea aprobată (`verifica_on_page`); un
   articol care nu o mai trece nu pleacă.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app import productie, seo, validare
from app.connectors.contract import Token
from app.publicare import canale
from app.publicare.modele import ContCanal

CANAL = "blog"
GAZDUIT = "gazduit"


class ArticolRefuzat(ValueError):
    pass


def configureaza_gazduit(
    db: Session, tenant_id: uuid.UUID, *, utilizator_id: uuid.UUID | None = None
) -> ContCanal:
    """Blogul găzduit de platformă (al agenției): nu are parolă; contul se marchează „găzduit”."""
    canale.configureaza(
        db, tenant_id, CANAL, nume="Blogul agenției", cont_agentie=True, setari={"tip": GAZDUIT}
    )
    return canale.salveaza_token(
        db, tenant_id, CANAL, Token(GAZDUIT, None, "", GAZDUIT), utilizator_id=utilizator_id
    )


def pregateste(
    db: Session, tenant_id: uuid.UUID, rezultat: dict[str, Any], *, utilizator_id: uuid.UUID
) -> uuid.UUID:
    if rezultat.get("on_page") or not rezultat.get("validare"):
        raise ArticolRefuzat("doar articolul care trece lista on-page și validarea merge la aprobare")
    lv = productie.creeaza(
        db, tenant_id=tenant_id, tip="articol", canal=CANAL, componenta="H6", utilizator_id=utilizator_id
    )
    for din, la in (
        (productie.Stare.PLANIFICAT, productie.Stare.BRIEFAT),
        (productie.Stare.BRIEFAT, productie.Stare.IN_SCRIERE),
    ):
        productie.muta(db, lv.id, din, la, componenta="E5", motiv="articol SEO (F7.10)")
    a = rezultat["articol"]
    corp = [{"titlu": "", "paragrafe": [a["introducere"]]}, *a["sectiuni"]]
    campuri = {
        "titlu": rezultat["titlu"],
        "descriere": rezultat["descriere"],
        "slug": rezultat["slug"],
        "corp": corp,
        "surse": rezultat["surse_citate"],
        "subiect": rezultat["brief"]["principal"],
        "articol": a,
        "brief": rezultat["brief"],
    }
    # textul validat: fără trimiterile [n] (ca în F7.10); corpul publicat le păstrează
    text = seo.articole.CITARE.sub("", seo.articole.text_articol(a))
    validare.continut.scrie(
        db, lv.id, text=text, campuri=campuri, autor="E7", model_autor=rezultat.get("model")
    )
    productie.muta(
        db,
        lv.id,
        productie.Stare.IN_SCRIERE,
        productie.Stare.IN_VALIDARE,
        componenta="E7",
        motiv="articol scris",
    )
    r = validare.ciclu.ruleaza_runda(db, lv.id, utilizator_id=utilizator_id)
    if productie.Stare(productie.citeste(db, lv.id).stare) is not productie.Stare.VALIDAT:  # type: ignore[union-attr]
        raise ArticolRefuzat(f"articolul nu a trecut validarea: {r}")
    productie.aprobari.cere(db, lv.id)
    return lv.id


def pachet(c: validare.Continut) -> dict[str, Any]:
    """Pachetul articolului pentru conector; refuză versiunea care nu mai trece lista on-page."""
    k = c.campuri
    probleme = seo.articole.verifica_on_page(k["titlu"], k["descriere"], k["slug"], k["articol"], k["brief"])
    if probleme:
        raise ArticolRefuzat("lista on-page nu trece: " + "; ".join(probleme))
    return {
        "titlu": k["titlu"],
        "descriere": k["descriere"],
        "slug": k["slug"],
        "corp": k["corp"],
        "surse": k["surse"],
        "subiect": k["subiect"],
        "text": c.text,
    }
