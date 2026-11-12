"""Extragerea faptelor din materiale (F4.6, docs/09 §9.3): fiecare pasaj trece printr-un model cu schemă
strictă, iar
FIECARE fapt propus păstrează citatul exact din sursă. Un verificator determinist (`citat.verifica_propunere`)
respinge
propunerile al căror citat nu se regăsește literal în pasaj sau ale căror cifre nu apar în citat: modelul nu
poate
introduce un fapt pe care materialul nu-l conține. Ce trece devine fapt `propus` (niciodată `aprobat`:
aprobarea e a unui om).

Textul pasajului este conținut extern: intră în prompt doar prin `gateway.marcheaza_extern`. Promptul este
versionat în
fișierul `prompts/creier.extrage_fapte.v1.md` și se aduce în registrul de prompturi cu `pregateste_prompt`
(idempotent).
Modelul primește valorile reale ale datelor mascate (`demasca=True`), ca citatele cu emailuri și telefoane să
se poată
verifica literal.

Fiecare pasaj se extrage o singură dată pe versiune de prompt (`creier_extrageri`): reluarea fluxului nu
cheamă din nou
modelul pentru pasajele terminate.
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import gateway
from app.cercetare import Document
from app.creier import citat as verificator
from app.creier import fapte
from app.creier.compartimente import SursaTip
from app.creier.modele import Extragere, Pasaj
from app.creier.versiuni import RegulaCreier, Sursa
from app.db import sesiune_agentie, sesiune_tenant
from app.ids import new_id
from app.operare.motor import Prioritate

NUME_PROMPT = "creier.extrage_fapte"
VERSIUNE_PROMPT = 1
REFERINTA_PROMPT = f"{NUME_PROMPT}@{VERSIUNE_PROMPT}"
DIRECTOR_PROMPTURI = Path(__file__).resolve().parents[2] / "prompts"
PASAJE_PE_LOT = 3
MAXIM_RESPINSE_PASTRATE = 20


class FaptExtras(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tip: Literal[
        "pret",
        "caracteristica",
        "cifra",
        "garantie",
        "termen",
        "program",
        "date_contact",
        "adresa",
        "mentiune_legala",
        "afirmatie_performanta",
        "altul",
    ]
    subiect: str = Field(description="Despre ce este faptul (produs, serviciu, temă)", max_length=160)
    afirmatie: str = Field(description="Faptul, într-o singură propoziție atomică", max_length=500)
    valoare_numar: str | None = Field(
        default=None, description="Numărul exact, dacă faptul are unul", max_length=40
    )
    moneda: str | None = Field(
        default=None, description="Codul valutar din 3 litere mari (RON), dacă e un preț"
    )
    unitate: str | None = Field(default=None, description="Unitatea (g, lună, persoană …)", max_length=40)
    valoare_text: str | None = Field(
        default=None, description="Valoarea ca text, dacă nu e număr", max_length=200
    )
    citat: str = Field(
        description="Citatul EXACT din text care susține faptul, cuvânt cu cuvânt", max_length=800
    )


class PropunereFapte(gateway.Iesire):
    """Ieșirea modelului: lista de fapte propuse dintr-un pasaj (poate fi goală)."""

    fapte: list[FaptExtras] = Field(default_factory=list, max_length=12)


def pregateste_prompt() -> list[str]:
    """Aduce promptul versionat din `prompts/` în registrul gateway-ului (idempotent)."""
    with sesiune_agentie() as db:
        return gateway.prompturi.sincronizeaza(db, DIRECTOR_PROMPTURI)


@dataclass(frozen=True)
class RezultatPasaj:
    pasaj_id: uuid.UUID
    propuse: int
    duplicate: int
    respinse: list[dict[str, str]]


def valideaza_propunere(p: FaptExtras, text_pasaj: str) -> str | None:
    """Motivul respingerii unei propuneri, sau `None` dacă trece (nucleu determinist, fără model)."""
    motiv = verificator.verifica_propunere(p.citat, text_pasaj, valoare_numar=p.valoare_numar)
    if motiv is not None:
        return motiv
    if p.moneda is not None and (len(p.moneda) != 3 or not p.moneda.isupper() or not p.moneda.isalpha()):
        return "moneda_invalida"
    if not p.afirmatie.strip() or len(p.afirmatie.strip()) < 5:
        return "afirmatie_invalida"
    if (
        p.valoare_numar is not None
        and p.valoare_numar.strip()
        and not p.valoare_numar.replace(",", ".").replace(".", "", 1).isdigit()
    ):
        return "valoare_invalida"
    return None


def _continut(p: FaptExtras) -> fapte.ContinutFapt:
    valoare = None
    if any((p.valoare_numar, p.moneda, p.unitate, p.valoare_text)):
        numar = verificator.numar_canonic(p.valoare_numar) if p.valoare_numar else None
        valoare = fapte.Valoare(
            numar=None if numar is None else Decimal(numar),
            moneda=p.moneda,
            unitate=p.unitate,
            text=p.valoare_text,
        )
    return fapte.ContinutFapt(
        tip=fapte.TipFapt(p.tip), subiect=p.subiect.strip(), afirmatie=p.afirmatie.strip(), valoare=valoare
    )


def pasaje_de_extras(db: Session, tenant_id: uuid.UUID, sursa_id: uuid.UUID, limita: int) -> list[uuid.UUID]:
    """Pasajele sursei care nu au fost încă extrase cu versiunea curentă a promptului."""
    q = (
        select(Pasaj.id)
        .where(
            Pasaj.tenant_id == tenant_id,
            Pasaj.sursa_id == sursa_id,
            ~select(Extragere.id)
            .where(Extragere.pasaj_id == Pasaj.id, Extragere.prompt == REFERINTA_PROMPT)
            .exists(),
        )
        .order_by(Pasaj.document_id, Pasaj.pozitie)
        .limit(limita)
    )
    return list(db.execute(q).scalars())


def extrage_din_pasaj(tenant_id: uuid.UUID, pasaj_id: uuid.UUID) -> RezultatPasaj:
    """Un pasaj → propuneri verificate. Ridică `gateway.Amanat` / `gateway.ApelRefuzat` (apelantul decide:
    reprogramare,
    mutare pe altă coadă). O ieșire care nu respectă schema se înregistrează ca extragere fără fapte (nu se
    repetă la infinit)."""
    with sesiune_tenant(tenant_id) as db:
        p = db.get(Pasaj, pasaj_id)
        if p is None:
            return RezultatPasaj(pasaj_id, 0, 0, [])
        if db.execute(
            select(Extragere.id).where(Extragere.pasaj_id == pasaj_id, Extragere.prompt == REFERINTA_PROMPT)
        ).first():
            return RezultatPasaj(pasaj_id, 0, 0, [])
        d = db.get(Document, p.document_id)
        sursa_text = "pagina" if d is not None and d.tip == "pagina" else "fisier_client"
        text_pasaj = p.text
        try:
            r = gateway.apeleaza(
                db,
                prompt=REFERINTA_PROMPT,
                variabile={"pasaj": gateway.marcheaza_extern(text_pasaj, sursa=sursa_text)},
                schema=PropunereFapte,
                tenant_id=tenant_id,
                componenta="creier.extrage_fapte",
                prioritate=Prioritate.P3,
                max_tokeni=1800,
                demasca=True,
            )
        except gateway.IesireInvalida:
            db.add(
                Extragere(
                    id=new_id(),
                    tenant_id=tenant_id,
                    pasaj_id=pasaj_id,
                    document_id=p.document_id,
                    prompt=REFERINTA_PROMPT,
                    propuse=0,
                    duplicate=0,
                    respinse=[{"motiv": "iesire_invalida"}],
                )
            )
            return RezultatPasaj(pasaj_id, 0, 0, [{"motiv": "iesire_invalida"}])
        propuse = duplicate = 0
        respinse: list[dict[str, str]] = []
        iesire = r.iesire
        if not isinstance(iesire, PropunereFapte):
            raise TypeError("ieșirea nu respectă schema promptului")
        for f in iesire.fapte:
            motiv = valideaza_propunere(f, text_pasaj)
            if motiv is None:
                try:
                    _, _, creat = fapte.propune_fapt(
                        db,
                        tenant_id=tenant_id,
                        continut=_continut(f),
                        sursa=Sursa(
                            SursaTip.PASAJ,
                            ref=str(pasaj_id),
                            citat=f.citat.strip(),
                            detalii={
                                "document_id": str(p.document_id),
                                "url": d.url if d else None,
                                "pozitie": p.pozitie,
                                "car_inceput": p.car_inceput,
                                "car_sfarsit": p.car_sfarsit,
                            },
                        ),
                    )
                except (fapte.CitatNegasit, RegulaCreier, ValueError) as exc:
                    motiv = getattr(exc, "cod", None) or "propunere_invalida"
                else:
                    propuse += creat
                    duplicate += not creat
                    continue
            respinse.append({"motiv": motiv, "afirmatie": f.afirmatie[:160], "citat": f.citat[:160]})
        db.add(
            Extragere(
                id=new_id(),
                tenant_id=tenant_id,
                pasaj_id=pasaj_id,
                document_id=p.document_id,
                prompt=REFERINTA_PROMPT,
                propuse=propuse,
                duplicate=duplicate,
                respinse=respinse[:MAXIM_RESPINSE_PASTRATE],
                model=r.model,
            )
        )
    return RezultatPasaj(pasaj_id, propuse, duplicate, respinse)


def rezumat(db: Session, tenant_id: uuid.UUID, sursa_id: uuid.UUID) -> dict[str, int]:
    """Cât s-a extras dintr-o sursă: pasaje, fapte propuse, duplicate, propuneri respinse de verificator."""
    r = db.execute(
        text(
            "SELECT count(*), COALESCE(sum(e.propuse), 0), COALESCE(sum(e.duplicate), 0), "
            "COALESCE(sum(jsonb_array_length(e.respinse)), 0) FROM creier_extrageri e "
            "JOIN pasaje p ON p.id = e.pasaj_id WHERE e.tenant_id = :t AND p.sursa_id = :s AND e.prompt = :p"
        ),
        {"t": tenant_id, "s": sursa_id, "p": REFERINTA_PROMPT},
    ).one()
    return {"pasaje": int(r[0]), "propuse": int(r[1]), "duplicate": int(r[2]), "respinse": int(r[3])}


_ = dt
