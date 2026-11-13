"""Întrebările de clarificare (F4.4, docs/19 §19.3 pasul 2: „cere clarificări unde răspunsul este vag”).

Un model (profilul `clasificare`, prin gateway, cu schemă strictă) judecă dacă un răspuns e destul de concret
și, dacă nu, formulează O întrebare. Numărul lor este limitat (`MAX_PE_INTREBARE`, `MAX_PE_SESIUNE`): după
limită răspunsul se păstrează ca atare, iar poarta de completitudine a brieful hotărăște dacă mai poate trece.
Când gateway-ul nu răspunde (amânat, refuzat, ieșire invalidă), un răspuns prea scurt primește
întrebarea-șablon
din interviu (`Intrebare.clarificare_sablon`), iar unul destul de lung se acceptă: interviul nu se blochează.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import Field
from sqlalchemy.orm import Session

from app import gateway
from app.onboarding.interviu import Intrebare
from app.operare.motor import Prioritate

REFERINTA_PROMPT = "onboarding.evalueaza_raspuns@1"
MAX_PE_INTREBARE = 2
MAX_PE_SESIUNE = 6


class EvaluareRaspuns(gateway.Iesire):
    suficient: bool
    lipseste: str = Field(default="", max_length=300)
    intrebare: str = Field(default="", max_length=400)


@dataclass(frozen=True)
class Verdict:
    suficient: bool
    intrebare: str
    generata_de: Literal["model", "sablon", "date"]
    lipseste: str = ""


def evalueaza(db: Session, *, tenant_id: object, intrebare: Intrebare, raspuns: str) -> Verdict:
    """Verdictul pentru răspunsul (agregat) la o întrebare. Nu ridică erori de gateway."""
    lung_ok = len(raspuns.strip()) >= intrebare.min_caractere
    try:
        r = gateway.apeleaza(
            db,
            prompt=REFERINTA_PROMPT,
            variabile={
                "intrebare": intrebare.text,
                "raspuns": gateway.marcheaza_extern(raspuns, sursa="raspuns_client", max_caractere=6000),
            },
            schema=EvaluareRaspuns,
            tenant_id=tenant_id,  # type: ignore[arg-type]
            componenta="onboarding.evalueaza_raspuns",
            prioritate=Prioritate.P2,
            max_tokeni=400,
        )
    except gateway.EroareGateway:
        if lung_ok:
            return Verdict(True, "", "date")
        return Verdict(False, intrebare.clarificare_sablon, "sablon", "prea scurt")
    iesire = r.iesire
    if not isinstance(iesire, EvaluareRaspuns):
        raise TypeError("ieșirea nu respectă schema promptului")
    if iesire.suficient and lung_ok:
        return Verdict(True, "", "model")
    q = iesire.intrebare.strip()
    if len(q) < 10:
        return Verdict(False, intrebare.clarificare_sablon, "sablon", iesire.lipseste or "prea scurt")
    return Verdict(False, q[:400], "model", iesire.lipseste)
