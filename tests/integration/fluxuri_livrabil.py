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
# Cât timp livrabilul e într-una dintre aceste stări, fluxul îl împinge mai departe. Se oprește la
# `asteapta_aprobare` (așteaptă un om), la `expirat`, `respins`, `coada_de_erori`, `inchis` și la cele terminale.
ACTIVE = {
    Stare.PLANIFICAT,
    Stare.BRIEFAT,
    Stare.IN_SCRIERE,
    Stare.IN_VALIDARE,
    Stare.IN_REPARATIE,
    Stare.VALIDAT,
    Stare.APROBAT,
    Stare.IN_RANDARE,
    Stare.CONTROL_MEDIA,
    Stare.GATA,
    Stare.PROGRAMAT,
    Stare.IN_PUBLICARE,
    Stare.PUBLICAT,
    Stare.IN_MASURARE,
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
            rezultat = _urmatorul(db, livrabil, stare, scenariu)
            return rezultat.value if isinstance(rezultat, Stare) else rezultat
        except productie.ProductieOprita:
            return "oprita"


def _urmatorul(db, livrabil, stare: Stare, scenariu: str) -> Stare | str:  # type: ignore[no-untyped-def]
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
    if stare == Stare.VALIDAT:
        # Autonomia (F2.10) hotărăște: L0 umbră (parcat), L1 / eșantion aprobare (se oprește la un om), altfel automat.
        decizie = productie.autonomie.decide(db, livrabil)
        if decizie is productie.Decizie.UMBRA:
            return "umbra"  # L0 produce, dar nu publică: livrabilul rămâne „validat”
        if decizie is productie.Decizie.AUTOMAT:
            return muta(
                Stare.APROBAT,
                "autonomie",
                temei=productie.Temei.autonomie(),
                detalii={"autonomie": "automat"},
            )
        productie.aprobari.cere(db, lid)
        return Stare.ASTEAPTA_APROBARE
    if stare == Stare.APROBAT:
        # SIMULAT: un video trece prin randare și controlul media; un text merge direct la programare
        return muta(Stare.IN_RANDARE if livrabil.tip == "video" else Stare.PROGRAMAT, "H1")
    if stare == Stare.IN_RANDARE:
        return muta(Stare.CONTROL_MEDIA, "F3")  # SIMULAT: nicio randare reală
    if stare == Stare.CONTROL_MEDIA:
        return muta(Stare.GATA, "G5")  # SIMULAT: nicio verificare reală
    if stare == Stare.GATA:
        return muta(Stare.PROGRAMAT, "B4")
    if stare == Stare.PROGRAMAT:
        return muta(Stare.IN_PUBLICARE, "B4")
    if stare == Stare.IN_PUBLICARE:
        return muta(Stare.PUBLICAT, "B7")  # SIMULAT: NU se publică nimic; executorul de efecte este F2.5
    if stare == Stare.PUBLICAT:
        return muta(Stare.IN_MASURARE, "K1")
    if stare == Stare.IN_MASURARE:
        return muta(Stare.INCHIS, "K8")
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
