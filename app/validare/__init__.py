"""Sistemul de validare (docs/09): cascada V0–V5, validatorii G, verdictele salvate.

Restul aplicației folosește doar ce se exportă aici. Cum se folosește (F6 și celelalte componente):

    from app import validare

    # conținutul livrabilului (acoperire provizorie până la F6)
    validare.continut.scrie(db, livrabil_id, text="…", campuri={"titlu": "…"}, autor="E4",
    model_autor="groq/llama")
    # livrabilul trece în `in_validare` (productie.muta), apoi, ca pas durabil:
    job = validare.trimite(tenant_id, livrabil_id, cheie=f"validare:{livrabil_id}:{versiune}")
    # sau, într-o tranzacție proprie:
    r = validare.ruleaza_runda(db, livrabil_id)       # RezultatRunda: decizie, stare, instrucțiune,
    verdicte
    # verdictele salvate (cu validatorul și versiunea lui), pentru ecrane, seturi de aur și calibrare:
    validare.verdicte(db, livrabil_id, versiune=2); validare.rulari(db, livrabil_id)
    # autorii reparațiilor (F6) se înregistrează o dată: validare.autor.inregistreaza(f)

Un validator nou se adaugă cu `@validare.registru.validator(DefinitieValidator(cod, nume, versiune, treapta,
...))`
pe o funcție `(Intrare) -> Verdict | list[Verdict] | None`.
"""

from app.validare import agregare, autor, cascada, ciclu, continut, depozit, registru, verdict
from app.validare.agregare import Agregat, Decizie, agrega, unifica_instructiunile
from app.validare.autor import ContinutNou, SarcinaReparatie
from app.validare.cascada import Evaluare, FaraValidatori, evalueaza, ruleaza_pasii
from app.validare.ciclu import NuSeValideaza, RezultatRunda, ruleaza_repararea, ruleaza_runda
from app.validare.continut import FaraContinut
from app.validare.depozit import pentru_ecran, rulari, ultima_rulare, verdicte, verdicte_rulare
from app.validare.fluxuri import trimite
from app.validare.intrare import Continut, Intrare, SituatieLivrabil, amprenta_text
from app.validare.modele import ContinutLivrabil, Rulare, VerdictSalvat
from app.validare.registru import DefinitieValidator
from app.validare.verdict import (
    Cost,
    Dovada,
    Rezultat,
    Severitate,
    Treapta,
    Verdict,
    VerdictInvalid,
    avertisment,
    esec,
    trece,
)

__all__ = [
    "Agregat",
    "Continut",
    "ContinutLivrabil",
    "ContinutNou",
    "Cost",
    "Decizie",
    "DefinitieValidator",
    "Dovada",
    "Evaluare",
    "FaraContinut",
    "FaraValidatori",
    "Intrare",
    "NuSeValideaza",
    "Rezultat",
    "RezultatRunda",
    "Rulare",
    "SarcinaReparatie",
    "Severitate",
    "SituatieLivrabil",
    "Treapta",
    "Verdict",
    "VerdictInvalid",
    "VerdictSalvat",
    "agrega",
    "agregare",
    "amprenta_text",
    "autor",
    "avertisment",
    "cascada",
    "ciclu",
    "continut",
    "depozit",
    "esec",
    "evalueaza",
    "pentru_ecran",
    "registru",
    "rulari",
    "ruleaza_pasii",
    "ruleaza_repararea",
    "ruleaza_runda",
    "trece",
    "trimite",
    "ultima_rulare",
    "unifica_instructiunile",
    "verdict",
    "verdicte",
    "verdicte_rulare",
]
