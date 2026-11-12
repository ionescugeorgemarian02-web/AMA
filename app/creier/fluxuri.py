"""Fluxul durabil al indexării (F4.3): `creier.indexeaza_sursa(tenant_id, sursa_id)` pe coada `io`.

Primește doar identificatori. Pasul de pregătire taie documentele în pasaje; pașii de vectorizare lucrează în
loturi.
Când gateway-ul spune `Amanat` (niciun model de vectori activ, server căzut) fluxul își reprogramează munca
pentru
momentul cerut (`gateway.reprogrameaza`) și se încheie; la reluare continuă cu ce a rămas, fiindcă pasajele
fără vector
sunt chiar lista de lucru.
"""

import datetime as dt
import uuid
from typing import Any

from app import cercetare, gateway
from app.creier import extragere, fapte, indexare
from app.db import sesiune_agentie, sesiune_tenant
from app.logging import get_logger
from app.operare import motor, notificari
from app.operare.motor import Coada, Prioritate

log = get_logger("app.creier")
NUME_FLUX = "creier.indexeaza_sursa"
NUME_EXTRAGERE = "creier.extrage_fapte"
NUME_EXPIRARE = "creier.expira_valabilitati"
PAUZA_INDISPONIBIL_SEC = 600
LOTURI_MAXIME = 500


@motor.pas(nume="creier.pregateste_pasaje", reincercari=1)
def _pregateste(tenant_id: str, sursa_id: str) -> str:
    with sesiune_tenant(uuid.UUID(tenant_id)) as db:
        return f"pasaje_noi={indexare.pregateste_sursa(db, uuid.UUID(sursa_id))}"


@motor.pas(nume="creier.lot_vectori", reincercari=1)
def _lot(tenant_id: str, sursa_id: str) -> str:
    """`continua`, `gata` sau `amanat:<moment ISO>` (nu ridică `Amanat`: fluxul îl tratează singur)."""
    try:
        n = indexare.vectorizeaza_lot(uuid.UUID(tenant_id), uuid.UUID(sursa_id))
    except gateway.Amanat as amanat:
        return f"amanat:{amanat.pana_la.isoformat()}"
    return "continua" if n else "gata"


@motor.flux(NUME_FLUX, timp_maxim_sec=900)
def indexeaza_sursa(tenant_id: str, sursa_id: str) -> str:
    _pregateste(tenant_id, sursa_id)
    for _ in range(LOTURI_MAXIME):
        r = _lot(tenant_id, sursa_id)
        if r == "gata":
            return "gata"
        if r.startswith("amanat:"):
            pana = dt.datetime.fromisoformat(r.split(":", 1)[1])
            gateway.reprogrameaza(
                gateway.Amanat(pana, "vectori"),
                indexeaza_sursa,
                tenant_id,
                sursa_id,
                cheie=f"indexare:{sursa_id}:reluare",
                coada=Coada.IO,
                prioritate=Prioritate.P3,
            )
            return "amanat"
    return "partial"


def trimite(tenant_id: uuid.UUID, sursa_id: uuid.UUID, *, cheie: str) -> str:
    """Pune indexarea în coadă. Aceeași `cheie` (`indexare:<colectare_id>`), același job."""
    return motor.trimite(
        indexeaza_sursa, str(tenant_id), str(sursa_id), coada=Coada.IO, prioritate=Prioritate.P3, cheie=cheie
    )


def trimite_reindexarea(tenant_id: uuid.UUID, *, cheie: str) -> list[str]:
    """După schimbarea modelului: câte o indexare pentru fiecare sursă cu pasaje de re-vectorizat."""
    with sesiune_tenant(tenant_id) as db:
        surse = indexare.surse_de_vectorizat(db, tenant_id)
    return [trimite(tenant_id, s, cheie=f"{cheie}:{s}") for s in surse]


def _dupa_colectare(tenant_id: uuid.UUID, sursa_id: uuid.UUID, colectare_id: uuid.UUID) -> None:
    trimite(tenant_id, sursa_id, cheie=f"indexare:{colectare_id}")


def activeaza_indexarea_dupa_colectare() -> None:
    """Fiecare colectare terminată pornește indexarea sursei ei (apelat de worker la pornire)."""
    cercetare.dupa_colectare(_dupa_colectare)


# --- extragerea faptelor din materiale (F4.6)


@motor.pas(nume="creier.pregateste_prompt_fapte", reincercari=1)
def _prompt_fapte() -> str:
    extragere.pregateste_prompt()
    return "ok"


@motor.pas(nume="creier.extrage_lot", reincercari=1)
def _extrage_lot(tenant_id: str, sursa_id: str) -> str:
    """`continua`, `gata`, `amanat:<moment ISO>`, `pe_greu` (modelul local cere coada `greu`) sau
    `refuzat:<cod>`.
    Pasajele terminate nu se mai cheamă (rând în `creier_extrageri`)."""
    t, s = uuid.UUID(tenant_id), uuid.UUID(sursa_id)
    with sesiune_tenant(t) as db:
        ids = extragere.pasaje_de_extras(db, t, s, extragere.PASAJE_PE_LOT)
    if not ids:
        return "gata"
    for pid in ids:
        try:
            extragere.extrage_din_pasaj(t, pid)
        except gateway.Amanat as amanat:
            return f"amanat:{amanat.pana_la.isoformat()}"
        except gateway.FurnizoriIndisponibili:
            pana = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=PAUZA_INDISPONIBIL_SEC)
            return f"amanat:{pana.isoformat()}"
        except gateway.ApelRefuzat as exc:
            return "pe_greu" if exc.cod == "local_doar_pe_coada_greu" else f"refuzat:{exc.cod}"
    return "continua"


@motor.flux(NUME_EXTRAGERE, timp_maxim_sec=900)
def extrage_fapte(tenant_id: str, sursa_id: str, pe_greu: bool = False) -> str:
    """Trece pasajele unei surse prin model (schemă strictă), verifică determinist citatele și propune
    faptele. Nimic nu
    se aprobă aici. La `Amanat` se reprogramează; dacă modelul local e singura cale, se mută pe coada
    `greu`."""
    _prompt_fapte()
    for _ in range(LOTURI_MAXIME):
        r = _extrage_lot(tenant_id, sursa_id)
        if r == "gata":
            return "gata"
        if r == "pe_greu" and not pe_greu:
            motor.trimite(
                extrage_fapte,
                tenant_id,
                sursa_id,
                True,
                coada=Coada.GREU,
                prioritate=Prioritate.P3,
                cheie=f"extragere:{sursa_id}:greu",
            )
            return "mutat_pe_greu"
        if r.startswith("amanat:"):
            pana = dt.datetime.fromisoformat(r.split(":", 1)[1])
            gateway.reprogrameaza(
                gateway.Amanat(pana, "extragere"),
                extrage_fapte,
                tenant_id,
                sursa_id,
                pe_greu,
                cheie=f"extragere:{sursa_id}:reluare",
                coada=Coada.GREU if pe_greu else Coada.IO,
                prioritate=Prioritate.P3,
            )
            return "amanat"
        if r != "continua":
            return r
    return "partial"


def trimite_extragerea(tenant_id: uuid.UUID, sursa_id: uuid.UUID, *, cheie: str) -> str:
    """Pune extragerea faptelor dintr-o sursă în coadă (`io`). Idempotent pe `cheie`."""
    return motor.trimite(
        extrage_fapte,
        str(tenant_id),
        str(sursa_id),
        False,
        coada=Coada.IO,
        prioritate=Prioritate.P3,
        cheie=cheie,
    )


# --- expirarea faptelor și ofertelor (F4.6, docs/10 §10.4)


@motor.pas(nume="creier.expira")
def _expira() -> str:
    """Retrage faptele și ofertele al căror „valabil până la” a trecut și anunță agenția (clientul trebuie
    întrebat dacă
    mai sunt valabile). Idempotent: ce a expirat o dată nu mai apare."""
    with sesiune_agentie() as db:
        expirate = fapte.expira(db, dt.datetime.now(dt.UTC))
    if expirate:
        clienti = len({e.tenant_id for e in expirate})
        eticheta = "; ".join(sorted({e.eticheta for e in expirate if e.eticheta})[:4])
        notificari.notifica(
            notificari.Nivel.INFORMATIV,
            f"Valabilitate expirată: {len(expirate)} intrări",
            f"{len(expirate)} fapte / oferte au expirat la {clienti} clienți ({eticheta}). "
            "Întreabă clientul dacă mai sunt valabile.",
            url="/creier/fapte?stare=expirate",
        )
    return f"expirate={len(expirate)}"


@motor.flux(NUME_EXPIRARE)
def expira_valabilitati(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _expira()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME_EXPIRARE, "10 5 * * *", expira_valabilitati, coada=Coada.IO)


declara_programari()
