"""Validarea ca pas durabil (F5.1, ADR-03): fluxul `validare.livrabil` împinge livrabilul prin `în validare`
→
`în reparație` → `în validare` până se oprește (validat, aprobare, carantină, coada de erori) sau până îl
așteaptă un
autor. Primește doar identificatori. Fiecare pas pornește de la starea din bază, deci reluarea după o cădere
găsește
livrabilul unde l-a lăsat. Un judecător amânat (`gateway.Amanat`) reprogramează fluxul; nu degradează.
"""

import datetime as dt
import uuid

from app import gateway, productie
from app.db import sesiune_agentie, sesiune_tenant
from app.operare import motor
from app.operare.motor import Coada, Prioritate
from app.productie import Stare
from app.validare import ciclu

NUME = "validare.livrabil"
MAXIM_ITERATII = (
    12  # plasă de siguranță: 2 reparații cer cel mult 6 pași; restul îl taie limitele din productie
)


@motor.pas(nume="validare.pas_valideaza", reincercari=1)
def _valideaza(tenant_id: str, livrabil_id: str) -> str:
    """Starea după o rundă de validare, `amanat:<moment ISO>` sau starea găsită (dacă nu e în
    validare)."""
    lid = uuid.UUID(livrabil_id)
    with sesiune_tenant(uuid.UUID(tenant_id)) as db:
        livrabil = productie.citeste(db, lid)
        if livrabil is None:
            return "inexistent"
        if livrabil.stare != Stare.IN_VALIDARE.value:
            return livrabil.stare
        try:
            return ciclu.ruleaza_runda(db, lid).stare.value
        except gateway.Amanat as amanat:
            return f"amanat:{amanat.pana_la.isoformat()}"


@motor.pas(nume="validare.pas_repara", reincercari=1)
def _repara(tenant_id: str, livrabil_id: str) -> str:
    lid = uuid.UUID(livrabil_id)
    with sesiune_tenant(uuid.UUID(tenant_id)) as db:
        try:
            return ciclu.ruleaza_repararea(db, lid)
        except gateway.Amanat as amanat:
            return f"amanat:{amanat.pana_la.isoformat()}"


@motor.flux(NUME, timp_maxim_sec=900)
def valideaza_livrabil(tenant_id: str, livrabil_id: str) -> str:
    stare = Stare.IN_VALIDARE.value
    for _ in range(MAXIM_ITERATII):
        if stare == Stare.IN_REPARATIE.value:
            stare = _repara(tenant_id, livrabil_id)
            if stare == "fara_autor":
                return Stare.IN_REPARATIE.value
        else:
            stare = _valideaza(tenant_id, livrabil_id)
        if stare.startswith("amanat:"):
            gateway.reprogrameaza(
                gateway.Amanat(dt.datetime.fromisoformat(stare.split(":", 1)[1]), "validare"),
                valideaza_livrabil,
                tenant_id,
                livrabil_id,
                cheie=f"validare:{livrabil_id}:reluare",
                coada=Coada.IO,
                prioritate=Prioritate.P1,
            )
            return "amanat"
        if stare not in (Stare.IN_VALIDARE.value, Stare.IN_REPARATIE.value):
            return stare
    return stare


def trimite(tenant_id: uuid.UUID, livrabil_id: uuid.UUID, *, cheie: str) -> str:
    """Pune validarea în coadă (idempotent pe `cheie`). Livrabilul trebuie să fie `în validare`."""
    return motor.trimite(
        valideaza_livrabil,
        str(tenant_id),
        str(livrabil_id),
        coada=Coada.IO,
        prioritate=Prioritate.P1,
        cheie=cheie,
    )


# --- calibrarea judecătorilor (F5.8, G14)
# ----------------------------------------------------------------------
NUME_CALIBRARE = "validare.calibrare_saptamanala"
FEREASTRA_DERIVA_ZILE = 56  # 8 săptămâni de istoric pentru referința de derivă


@motor.pas(nume="validare.pas_calibrare")
def _calibreaza(moment_iso: str) -> str:
    from app.validare import calibrare  # import târziu: calibrarea trage exemplele și seturile

    moment = dt.datetime.fromisoformat(moment_iso)
    with sesiune_agentie() as db:
        noi = calibrare.esantioneaza(db, moment - dt.timedelta(days=7), moment)
        alerte = calibrare.verifica_si_anunta(db, moment - dt.timedelta(days=FEREASTRA_DERIVA_ZILE), moment)
    return f"esantion={len(noi)} alerte={len(alerte)}"


@motor.flux(NUME_CALIBRARE)
def calibrare_saptamanala(moment: dt.datetime, context: dict[str, object] | None) -> str:
    """Luni 05:41 (ora României): eșantionul săptămânii trecute la om, apoi alertele de acord și de derivă."""
    return _calibreaza(moment.isoformat())


def declara_programari() -> None:
    motor.programeaza_recurent(NUME_CALIBRARE, "41 5 * * 1", calibrare_saptamanala, coada=Coada.INVATARE)


declara_programari()
