"""Popularea modului local: proprietarul + brandul fictiv „Cafeneaua Zorilor”, cu brieful aprobat în Creier.

    python -m app.demo.populare --email admin@local.test     # parola din AMA_DEMO_PAROLA sau de la stdin

Idempotentă: o a doua rulare nu dublează nimic (caută după email, nume și cheia brief-ului).
SIMULAT: toate datele sunt fictive; brandul nu există. Nu se rulează în staging sau producție.
"""

import argparse
import os
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app import creier
from app.config import get_settings
from app.conturi import Actor, DateInvalide, creeaza_client, creeaza_utilizator
from app.conturi.roluri import Rol
from app.creier.compartimente import Compartiment, SursaTip
from app.db import sesiune_agentie, sesiune_tenant
from app.onboarding import completare

BRAND_DEMO = "Cafeneaua Zorilor"


def _camp(valoare: str) -> dict[str, Any]:
    return {"valoare": valoare, "surse": [{"tip": "operator", "ref": "demo-local", "citat": None}]}


BRIEF_DEMO: dict[str, Any] = {
    "nume_brand": _camp(BRAND_DEMO),
    "ce_vinde": _camp(
        "Cafea de specialitate prăjită în loturi mici, băuturi la pahar și patiserie proaspătă."
    ),
    "preturi": _camp("Espresso 9 lei, flat white 15 lei, pachet de cafea boabe 250 g între 45 și 60 de lei."),
    "public_tinta": _camp(
        "Tineri profesioniști din cartier, 25–40 de ani, care lucrează hibrid și vor o cafea bună."
    ),
    "de_ce_ne_aleg": _camp(
        "Prăjim chiar noi, cu data prăjirii pe fiecare pachet, și deschidem la 6:30 dimineața."
    ),
    "obiectii": _camp("„E mai scump decât la benzinărie” și „nu am timp să stau la coadă dimineața”."),
    "concurenti": _camp("Două lanțuri de cafenele din zonă și chioșcul de cafea de la stația de metrou."),
    "ce_a_incercat": _camp(
        "Flyere în blocurile din jur și o pagină de Facebook postată neregulat, fără buget."
    ),
    "interdictii": _camp(
        "Fără promisiuni despre efecte asupra sănătății și fără comparații cu firme numite."
    ),
    "ton_dorit": _camp("Cald, de vecin care știe cafea, fără jargon tehnic și fără superlative goale."),
    "obiectiv_90_zile": _camp(
        "Cu 30% mai mulți clienți dimineața și 100 de abonați la newsletterul cafenelei."
    ),
}


@dataclass(frozen=True)
class Rezultat:
    proprietar_id: uuid.UUID
    client_id: uuid.UUID
    creat_acum: tuple[str, ...]


def populeaza(email: str, parola: str) -> Rezultat:
    """Creează ce lipsește: proprietar, client demo, brieful aprobat. Întoarce id-urile și ce a creat."""
    if get_settings().env in ("staging", "prod"):
        raise RuntimeError("Popularea demo rulează doar local (AMA_ENV=dev sau test).")
    creat: list[str] = []
    with sesiune_agentie() as db:
        uid = db.execute(text("SELECT id FROM utilizatori WHERE email = :e"), {"e": email}).scalar()
        if uid is None:
            u = creeaza_utilizator(
                db, email=email, parola=parola, nume_afisat="Proprietar (local)",
                rol=Rol.PROPRIETAR, tenant_id=None, actor=Actor.cli(),
            )  # fmt: skip
            uid = u.id
            creat.append("proprietar")
        cid = db.execute(text("SELECT id FROM clienti WHERE nume = :n"), {"n": BRAND_DEMO}).scalar()
        if cid is None:
            cid = creeaza_client(db, BRAND_DEMO, actor=Actor.cli()).id
            creat.append("client")
    with sesiune_tenant(cid, uid) as db:
        cheie = completare.CHEIE_BRIEF
        i = creier.gaseste_intrare(db, tenant_id=cid, compartiment=Compartiment.BRIEF, cheie=cheie)
        if i is None or creier.versiune_aprobata(db, i.id) is None:
            sursa = creier.Sursa(SursaTip.OM, detalii={"demo": "populare-locala"})
            if i is None:
                i, v = creier.creeaza_intrare(
                    db, tenant_id=cid, compartiment=Compartiment.BRIEF, cheie=cheie,
                    continut=BRIEF_DEMO, sursa=sursa, utilizator_id=uid,
                )  # fmt: skip
            else:
                v = creier.propune_schimbare(db, i.id, continut=BRIEF_DEMO, sursa=sursa, utilizator_id=uid)
            creier.aproba(db, i.id, v.nr, utilizator_id=uid)
            creat.append("brief")
    return Rezultat(uid, cid, tuple(creat))


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.demo.populare")
    p.add_argument("--email", default=os.environ.get("AMA_DEMO_EMAIL", "admin@local.test"))
    args = p.parse_args(argv)
    parola = os.environ.get("AMA_DEMO_PAROLA") or sys.stdin.readline().rstrip("\r\n")
    try:
        r = populeaza(args.email, parola)
    except DateInvalide as exc:
        print(f"Eroare: {exc}", file=sys.stderr)
        return 1
    ce = ", ".join(r.creat_acum) or "nimic (exista deja)"
    print(f"Populare demo: creat {ce}. Proprietar {args.email}; client „{BRAND_DEMO}” ({r.client_id}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
