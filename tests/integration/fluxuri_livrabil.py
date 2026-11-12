"""# SIMULAT: fluxul de probă al livrabilului (F2.4, F2.8, F2.10), construit pe `motor.flux` / `motor.pas`.

Împinge un livrabil prin stări cu PAȘI FALȘI: scrierea, validarea și reparația nu produc conținut real, nu apelează
niciun model și nu au validatori; doar mută starea prin `productie.muta` și consumă din buget cifre inventate. Nimic
de aici nu e cod de producție: modulul trăiește în `tests/`.

Fiecare pas pornește de la starea din bază (nu de la una ținută în memorie): un pas reluat după o cădere găsește
livrabilul unde l-a lăsat. Scenarii (al treilea argument al fluxului):
- `ok`: validarea trece din prima;
- `o_runda`: validarea pică o dată, apoi trece (o rundă de reparație);
- `mereu_esueaza`: validarea pică mereu (a treia rundă merge la om);
- `buget`: validarea pică mereu, iar fiecare scriere sau reparație „consumă” 25 de apeluri (bugetul de 40
  se depășește la prima reparație).
"""

import uuid

from app import productie
from app.db import sesiune_tenant
from app.operare import motor
from app.productie import Stare

SCENARII = ("ok", "o_runda", "mereu_esueaza", "buget")
ACTIVE = {
    Stare.PLANIFICAT,
    Stare.BRIEFAT,
    Stare.IN_SCRIERE,
    Stare.IN_VALIDARE,
    Stare.IN_REPARATIE,
}
MAXIM_PASI = 80  # plasă de siguranță: un flux de probă nu se rotește la nesfârșit


def _trece_validarea(scenariu: str, runde_reparatie: int) -> bool:
    return scenariu == "ok" or (scenariu == "o_runda" and runde_reparatie >= 1)


@motor.pas()
def avanseaza(tenant_id: str, livrabil_id: str, scenariu: str) -> str:
    """SIMULAT: un pas al fluxului; întoarce starea livrabilului după el."""
    tenant, lid = uuid.UUID(tenant_id), uuid.UUID(livrabil_id)
    with sesiune_tenant(tenant) as db:
        livrabil = productie.citeste(db, lid)
        if livrabil is None:
            return "inexistent"
        stare = Stare(livrabil.stare)
        try:
            return _urmatorul(db, livrabil, stare, scenariu).value
        except productie.ProductieOprita:
            return "oprita"


def _urmatorul(db, livrabil, stare: Stare, scenariu: str) -> Stare:  # type: ignore[no-untyped-def]
    lid = livrabil.id

    def muta(la: Stare, componenta: str, **kw):  # type: ignore[no-untyped-def]
        return productie.muta(db, lid, stare, la, componenta=componenta, **kw).stare

    if stare == Stare.PLANIFICAT:
        return muta(Stare.BRIEFAT, "D5")
    if stare == Stare.BRIEFAT:
        return muta(Stare.IN_SCRIERE, "E1")
    if stare == Stare.IN_SCRIERE:
        consum = productie.inregistreaza_consum(
            db, lid, apeluri_llm=25 if scenariu == "buget" else 1, secunde=2.0, componenta="E1"
        )
        if consum.escaladat:
            return Stare.COADA_DE_ERORI
        return muta(Stare.IN_VALIDARE, "E1")
    if stare == Stare.IN_VALIDARE:
        productie.inregistreaza_consum(db, lid, apeluri_llm=1, secunde=1.0, componenta="G1")
        if _trece_validarea(scenariu, livrabil.runde_reparatie):
            return muta(Stare.VALIDAT, "G1")
        return muta(Stare.IN_REPARATIE, "G1", detalii={"verdict": "SIMULAT: hook slab", "validator": "G1"})
    if stare == Stare.IN_REPARATIE:
        consum = productie.inregistreaza_consum(
            db, lid, apeluri_llm=25 if scenariu == "buget" else 1, secunde=2.0, componenta="E1"
        )
        if consum.escaladat:
            return Stare.COADA_DE_ERORI
        productie.versiune_noua(db, lid, componenta="E1", motiv="reparație simulată")
        return muta(Stare.IN_VALIDARE, "E1")
    return stare


@motor.flux("proba.livrabil")
def proba(tenant_id: str, livrabil_id: str, scenariu: str) -> str:
    """SIMULAT: împinge livrabilul cât timp stările sunt „active”; întoarce starea la care s-a oprit."""
    stare = "planificat"
    for _ in range(MAXIM_PASI):
        stare = avanseaza(tenant_id, livrabil_id, scenariu)
        if stare not in {s.value for s in ACTIVE}:
            break
    return stare
