"""Vocea clientului (F4.9, C5): citate reale din recenzii, comentarii și întrebări frecvente, fiecare
cu sursă și poziție.

Un model (profilul `clasificare`, prin gateway, schemă strictă; pasajul marcat ca date externe) propune
citate dintr-un
pasaj. Un verificator DETERMINIST le primește sau le respinge:
- citatul trebuie să apară LITERAL în pasaj (același verificator ca la fapte, `creier.citat_in_text`);
- fără date personale: orice detecție a gărzii din F3.9 (email, telefon, IBAN, CNP …) respinge citatul;
- fără numele autorului: citatele care se termină cu o semnătură („— Ioana M.”) sau încep cu o
atribuire („Ioana M.:”)
  sunt respinse; numele autorilor nu se salvează nicăieri (nici câmp, nici sursă);
- lungime între 20 și 400 de caractere.
Ce trece devine intrare `insight_public` (cheia `citat-<amprentă>`), cu sursa pasaj + citatul + poziția
(document, URL,
pasaj, decalaje), aprobată de sistem (compartimentul permite; citatul e verificat mecanic, nu interpretat).
"""

import hashlib
import re
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app import cercetare, creier, gateway
from app.creier.compartimente import Compartiment, SursaTip
from app.db import sesiune_tenant
from app.onboarding import extractie
from app.onboarding.extractie import RezultatPasaj
from app.operare.motor import Prioritate

REFERINTA_PROMPT = "onboarding.extrage_citate@1"
LUNGIME_MINIMA, LUNGIME_MAXIMA = 20, 400
MINIM_CITATE = 20
_NUME = r"[A-ZĂÂÎȘȚ][a-zăâîșț]+(?:[ -][A-ZĂÂÎȘȚ][a-zăâîșț]+)?(?: [A-ZĂÂÎȘȚ]\.)?"
SEMNATURA_FINAL = re.compile(rf"[—–-]\s*{_NUME}\s*[”\"»]?\s*$")
ATRIBUIRE_INCEPUT = re.compile(rf"^\s*{_NUME}\s*:\s")


class CitatExtras(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(description="Citatul EXACT din text, fără numele autorului", max_length=600)
    tip: Literal["recenzie", "comentariu", "intrebare"]
    tema: str = Field(description="Despre ce vorbește citatul (două-trei cuvinte)", max_length=80)
    sentiment: Literal["pozitiv", "negativ", "neutru"]


class PropunereCitate(gateway.Iesire):
    citate: list[CitatExtras] = Field(default_factory=list, max_length=30)


def motiv_respingere(c: CitatExtras, text_pasaj: str) -> str | None:
    """Motivul respingerii (nucleu determinist, fără model), sau `None`."""
    t = c.text.strip()
    if not (LUNGIME_MINIMA <= len(t) <= LUNGIME_MAXIMA):
        return "lungime"
    if not creier.citat_in_text(t, text_pasaj):
        return "citat_negasit"
    if gateway.detecteaza_date_personale(t):
        return "date_personale"
    if SEMNATURA_FINAL.search(t) or ATRIBUIRE_INCEPUT.search(t):
        return "nume_autor"
    return None


def cheie_citat(text: str) -> str:
    return "citat-" + hashlib.sha256(" ".join(text.lower().split()).encode()).hexdigest()[:24]


def extrage_din_pasaj(tenant_id: uuid.UUID, pasaj_id: uuid.UUID) -> RezultatPasaj:
    """Un pasaj → citate verificate. Ridică `gateway.Amanat` / `gateway.ApelRefuzat` (fluxul decide)."""
    with sesiune_tenant(tenant_id) as db:
        p = db.get(creier.Pasaj, pasaj_id)
        if p is None or extractie.deja_extras(db, pasaj_id, REFERINTA_PROMPT):
            return RezultatPasaj(pasaj_id)
        d = db.get(cercetare.Document, p.document_id)
        r = RezultatPasaj(pasaj_id)
        try:
            ap = gateway.apeleaza(
                db,
                prompt=REFERINTA_PROMPT,
                variabile={"pasaj": gateway.marcheaza_extern(p.text, sursa="recenzie")},
                schema=PropunereCitate,
                tenant_id=tenant_id,
                componenta="onboarding.extrage_citate",
                prioritate=Prioritate.P3,
                max_tokeni=2500,
                demasca=True,
            )
        except gateway.IesireInvalida:
            r.respinse.append({"motiv": "iesire_invalida"})
            extractie.noteaza(db, tenant_id, p, REFERINTA_PROMPT, r, None)
            return r
        iesire = ap.iesire
        if not isinstance(iesire, PropunereCitate):
            raise TypeError("ieșirea nu respectă schema promptului")
        for c in iesire.citate:
            motiv = motiv_respingere(c, p.text)
            if motiv is None:
                t = " ".join(c.text.split())
                sursa = creier.Sursa(
                    SursaTip.PASAJ, ref=str(pasaj_id), citat=t,
                    detalii={"document_id": str(p.document_id), "url": d.url if d else None, "pozitie":
                    p.pozitie,
                             "car_inceput": p.car_inceput, "car_sfarsit": p.car_sfarsit},
                )  # fmt: skip
                try:
                    cheie = cheie_citat(t)
                    if creier.gaseste_intrare(
                        db, tenant_id=tenant_id, compartiment=Compartiment.INSIGHT_PUBLIC, cheie=cheie
                    ):
                        r.duplicate += 1
                        continue
                    creier.fapte.verifica_sursa(
                        db, tenant_id, sursa
                    )  # citatul se regăsește în pasaj (a doua verificare)
                    i, v = creier.creeaza_intrare(
                        db, tenant_id=tenant_id, compartiment=Compartiment.INSIGHT_PUBLIC, cheie=cheie,
                        continut={"tip": "citat", "text": t, "categorie": c.tip, "tema":
                        c.tema.strip(), "sentiment": c.sentiment},
                        sursa=sursa,
                    )  # fmt: skip
                    creier.aproba(db, i.id, v.nr, utilizator_id=None, prin_sistem=True)
                    r.propuse += 1
                    continue
                except creier.RegulaCreier as exc:
                    motiv = getattr(exc, "cod", None) or "propunere_invalida"
            r.respinse.append({"motiv": motiv, "citat": c.text[:160]})
        extractie.noteaza(db, tenant_id, p, REFERINTA_PROMPT, r, ap.model)
    return r


def citate_aprobate(db: Session, tenant_id: uuid.UUID) -> list[tuple[uuid.UUID, dict[str, Any]]]:
    """Citatele aprobate ale clientului (id intrare, conținut), în ordine stabilă."""
    return [
        (i.id, v.continut)
        for i, v in creier.lista(db, tenant_id=tenant_id, compartiment=Compartiment.INSIGHT_PUBLIC)
        if v is not None and v.continut.get("tip") == "citat"
    ]
