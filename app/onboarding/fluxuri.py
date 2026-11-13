"""Fluxurile durabile ale onboardingului (F4.4+): compunerea brieful, propunerea de ton și celelalte, pe coada
`io`. Primesc doar identificatori; la `gateway.Amanat` (profil care amână, cotă epuizată) își
reprogramează munca
pentru momentul cerut și se încheie, iar sesiunea arată `amanat_pana`. Nu degradează niciodată la un
model mai slab.
"""

import datetime as dt
import uuid

from sqlalchemy import update

from app import creier, gateway
from app.db import sesiune_tenant
from app.logging import get_logger
from app.onboarding import citate, completare, extractie, ghid, piata, prompturi, public, strategie
from app.onboarding.modele import Sesiune
from app.operare import motor
from app.operare.motor import Coada, Prioritate

log = get_logger("app.onboarding")
NUME_COMPUNERE = "onboarding.compune_brief"


def _amana(tenant_id: str, sesiune_id: str, pana: dt.datetime) -> None:
    with sesiune_tenant(uuid.UUID(tenant_id)) as db:
        db.execute(update(Sesiune).where(Sesiune.id == uuid.UUID(sesiune_id)).values(amanat_pana=pana))


@motor.pas(nume="onboarding.compune_brief_pas", reincercari=1)
def _compune(tenant_id: str, sesiune_id: str, utilizator_id: str) -> str:
    """`gata`, `amanat:<moment ISO>` sau `refuzat:<motiv>`."""
    try:
        with sesiune_tenant(uuid.UUID(tenant_id)) as db:
            completare.compune(db, uuid.UUID(sesiune_id), utilizator_id=uuid.UUID(utilizator_id))
    except gateway.Amanat as amanat:
        _amana(tenant_id, sesiune_id, amanat.pana_la)
        return f"amanat:{amanat.pana_la.isoformat()}"
    return "gata"


@motor.flux(NUME_COMPUNERE, timp_maxim_sec=600)
def compune_brief(tenant_id: str, sesiune_id: str, utilizator_id: str) -> str:
    r = _compune(tenant_id, sesiune_id, utilizator_id)
    if r.startswith("amanat:"):
        gateway.reprogrameaza(
            gateway.Amanat(dt.datetime.fromisoformat(r.split(":", 1)[1]), "brief"),
            compune_brief,
            tenant_id,
            sesiune_id,
            utilizator_id,
            cheie=f"brief:{sesiune_id}:reluare",
            coada=Coada.IO,
            prioritate=Prioritate.P2,
        )
        return "amanat"
    return r


def trimite_compunerea(
    tenant_id: uuid.UUID, sesiune_id: uuid.UUID, utilizator_id: uuid.UUID, *, cheie: str
) -> str:
    """Pune compunerea brieful în coadă (idempotent pe `cheie`). Sesiunea trece pe `compune`."""
    with sesiune_tenant(tenant_id) as db:
        db.execute(
            update(Sesiune)
            .where(Sesiune.id == sesiune_id, Sesiune.stare.in_(("interviu", "brief_gata", "compune")))
            .values(stare="compune", actualizat_la=dt.datetime.now(dt.UTC))
        )
    return motor.trimite(
        compune_brief, str(tenant_id), str(sesiune_id), str(utilizator_id), coada=Coada.IO,
        prioritate=Prioritate.P2, cheie=cheie,
    )  # fmt: skip


# --- propunerea de ton pentru ghidul de brand (F4.5)

NUME_TON = "onboarding.propune_ton"


@motor.pas(nume="onboarding.propune_ton_pas", reincercari=1)
def _propune_ton(tenant_id: str, utilizator_id: str) -> str:
    """`gata`, `amanat:<moment ISO>` sau `refuzat:variante_invalide` (verificările deterministe pică)."""
    try:
        with sesiune_tenant(uuid.UUID(tenant_id)) as db:
            ghid.propune_variante(db, tenant_id=uuid.UUID(tenant_id), utilizator_id=uuid.UUID(utilizator_id))
    except gateway.Amanat as amanat:
        return f"amanat:{amanat.pana_la.isoformat()}"
    except ghid.VariantaInvalida:
        return "refuzat:variante_invalide"
    except gateway.EroareGateway as exc:  # ieșire invalidă, furnizori indisponibili, apel refuzat
        return f"refuzat:{type(exc).__name__}"
    return "gata"


@motor.flux(NUME_TON, timp_maxim_sec=600)
def propune_ton(tenant_id: str, utilizator_id: str) -> str:
    r = _propune_ton(tenant_id, utilizator_id)
    if r.startswith("amanat:"):
        gateway.reprogrameaza(
            gateway.Amanat(dt.datetime.fromisoformat(r.split(":", 1)[1]), "ton"),
            propune_ton,
            tenant_id,
            utilizator_id,
            cheie=f"ton:{tenant_id}:reluare",
            coada=Coada.IO,
            prioritate=Prioritate.P2,
        )
        return "amanat"
    return r


def trimite_propunerea_de_ton(tenant_id: uuid.UUID, utilizator_id: uuid.UUID, *, cheie: str) -> str:
    """Pune în coadă propunerea celor trei variante de ton (idempotent pe `cheie`)."""
    return motor.trimite(
        propune_ton, str(tenant_id), str(utilizator_id), coada=Coada.IO, prioritate=Prioritate.P2, cheie=cheie
    )


# --- extragerile pe pasaje: citate (F4.9) și afirmațiile concurenței (F4.10)

NUME_EXTRAGERE = "onboarding.extrage"
PAUZA_INDISPONIBIL_SEC = 600
LOTURI_MAXIME = 500
TIPURI_EXTRAGERE = {
    "citate": (citate.REFERINTA_PROMPT, citate.extrage_din_pasaj),
    "afirmatii": (piata.REFERINTA_AFIRMATII, piata.extrage_din_pasaj),
}


@motor.pas(nume="onboarding.extrage_lot", reincercari=1)
def _extrage_lot(tenant_id: str, sursa_id: str, tip: str) -> str:
    """`continua`, `gata`, `amanat:<moment ISO>`, `pe_greu` (modelul local cere coada `greu`) sau
    `refuzat:<cod>`.
    Pasajele terminate nu se mai cheamă (rând în `creier_extrageri`)."""
    t, s = uuid.UUID(tenant_id), uuid.UUID(sursa_id)
    prompt, extrage_pasaj = TIPURI_EXTRAGERE[tip]
    with sesiune_tenant(t) as db:
        ids = extractie.pasaje_de_extras(db, t, s, prompt, extractie.PASAJE_PE_LOT)
    if not ids:
        return "gata"
    prompturi.asigura()
    for pid in ids:
        try:
            extrage_pasaj(t, pid)
        except gateway.Amanat as amanat:
            return f"amanat:{amanat.pana_la.isoformat()}"
        except gateway.FurnizoriIndisponibili:
            pana = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=PAUZA_INDISPONIBIL_SEC)
            return f"amanat:{pana.isoformat()}"
        except gateway.ApelRefuzat as exc:
            return "pe_greu" if exc.cod == "local_doar_pe_coada_greu" else f"refuzat:{exc.cod}"
    return "continua"


@motor.flux(NUME_EXTRAGERE, timp_maxim_sec=900)
def extrage(tenant_id: str, sursa_id: str, tip: str, pe_greu: bool = False) -> str:
    """Trece pasajele unei surse prin model (schemă strictă), verifică determinist ce propune modelul
    și salvează doar ce
    trece. La `Amanat` se reprogramează; dacă modelul local e singura cale, se mută pe coada `greu`."""
    for _ in range(LOTURI_MAXIME):
        r = _extrage_lot(tenant_id, sursa_id, tip)
        if r == "gata":
            return "gata"
        if r == "pe_greu" and not pe_greu:
            motor.trimite(
                extrage, tenant_id, sursa_id, tip, True, coada=Coada.GREU, prioritate=Prioritate.P3,
                cheie=f"extragere:{tip}:{sursa_id}:greu",
            )  # fmt: skip
            return "mutat_pe_greu"
        if r.startswith("amanat:"):
            gateway.reprogrameaza(
                gateway.Amanat(dt.datetime.fromisoformat(r.split(":", 1)[1]), "extragere"),
                extrage,
                tenant_id,
                sursa_id,
                tip,
                pe_greu,
                cheie=f"extragere:{tip}:{sursa_id}:reluare",
                coada=Coada.GREU if pe_greu else Coada.IO,
                prioritate=Prioritate.P3,
            )
            return "amanat"
        if r != "continua":
            return r
    return "partial"


def trimite_extragerea(tenant_id: uuid.UUID, sursa_id: uuid.UUID, tip: str, *, cheie: str) -> str:
    """Pune extragerea (`citate` sau `afirmatii`) dintr-o sursă în coadă (`io`). Idempotent pe `cheie`."""
    if tip not in TIPURI_EXTRAGERE:
        raise ValueError(f"tip de extragere necunoscut: {tip}")
    return motor.trimite(
        extrage,
        str(tenant_id),
        str(sursa_id),
        tip,
        False,
        coada=Coada.IO,
        prioritate=Prioritate.P3,
        cheie=cheie,
    )


def trimite_extragerea_citatelor(tenant_id: uuid.UUID, sursa_id: uuid.UUID, *, cheie: str) -> str:
    return trimite_extragerea(tenant_id, sursa_id, "citate", cheie=cheie)


# --- profilul de public (F4.9)

NUME_PUBLIC = "onboarding.profil_public"


@motor.pas(nume="onboarding.profil_public_pas", reincercari=1)
def _profil_public(tenant_id: str, utilizator_id: str) -> str:
    try:
        with sesiune_tenant(uuid.UUID(tenant_id)) as db:
            public.propune_profil(db, tenant_id=uuid.UUID(tenant_id), utilizator_id=uuid.UUID(utilizator_id))
    except gateway.Amanat as amanat:
        return f"amanat:{amanat.pana_la.isoformat()}"
    except creier.RegulaCreier as exc:
        log.warning("profilul de public nu s-a putut propune", extra={"motiv": str(exc)[:200]})
        return "refuzat:profil_invalid"
    except gateway.EroareGateway as exc:
        return f"refuzat:{type(exc).__name__}"
    return "gata"


@motor.flux(NUME_PUBLIC, timp_maxim_sec=600)
def profil_public(tenant_id: str, utilizator_id: str) -> str:
    r = _profil_public(tenant_id, utilizator_id)
    if r.startswith("amanat:"):
        gateway.reprogrameaza(
            gateway.Amanat(dt.datetime.fromisoformat(r.split(":", 1)[1]), "public"),
            profil_public,
            tenant_id,
            utilizator_id,
            cheie=f"public:{tenant_id}:reluare",
            coada=Coada.IO,
            prioritate=Prioritate.P2,
        )
        return "amanat"
    return r


def trimite_profilul_de_public(tenant_id: uuid.UUID, utilizator_id: uuid.UUID, *, cheie: str) -> str:
    return motor.trimite(
        profil_public,
        str(tenant_id),
        str(utilizator_id),
        coada=Coada.IO,
        prioritate=Prioritate.P2,
        cheie=cheie,
    )


# --- brieful de insight al pieței (F4.10)

NUME_INSIGHT = "onboarding.brief_insight"


@motor.pas(nume="onboarding.brief_insight_pas", reincercari=1)
def _brief_insight(tenant_id: str, utilizator_id: str) -> str:
    try:
        with sesiune_tenant(uuid.UUID(tenant_id)) as db:
            piata.propune_brief(db, tenant_id=uuid.UUID(tenant_id), utilizator_id=uuid.UUID(utilizator_id))
    except gateway.Amanat as amanat:
        return f"amanat:{amanat.pana_la.isoformat()}"
    except creier.RegulaCreier as exc:
        log.warning("brieful de insight nu s-a putut propune", extra={"motiv": str(exc)[:200]})
        return "refuzat:insight_invalid"
    except gateway.EroareGateway as exc:
        return f"refuzat:{type(exc).__name__}"
    return "gata"


@motor.flux(NUME_INSIGHT, timp_maxim_sec=900)
def brief_insight(tenant_id: str, utilizator_id: str) -> str:
    """Profilul `strategie` se amână, nu se degradează: la `Amanat` fluxul se reprogramează."""
    r = _brief_insight(tenant_id, utilizator_id)
    if r.startswith("amanat:"):
        gateway.reprogrameaza(
            gateway.Amanat(dt.datetime.fromisoformat(r.split(":", 1)[1]), "insight"),
            brief_insight,
            tenant_id,
            utilizator_id,
            cheie=f"insight:{tenant_id}:reluare",
            coada=Coada.IO,
            prioritate=Prioritate.P2,
        )
        return "amanat"
    return r


def trimite_brief_insight(tenant_id: uuid.UUID, utilizator_id: uuid.UUID, *, cheie: str) -> str:
    return motor.trimite(
        brief_insight,
        str(tenant_id),
        str(utilizator_id),
        coada=Coada.IO,
        prioritate=Prioritate.P2,
        cheie=cheie,
    )


# --- strategia pe 90 de zile (F4.11)

NUME_STRATEGIE = "onboarding.strategie"


@motor.pas(nume="onboarding.strategie_pas", reincercari=1)
def _strategie(tenant_id: str, utilizator_id: str) -> str:
    """`gata`, `amanat:<moment ISO>` (strategia se amână, nu se degradează) sau `refuzat:<motiv>`."""
    try:
        with sesiune_tenant(uuid.UUID(tenant_id)) as db:
            strategie.propune(db, tenant_id=uuid.UUID(tenant_id), utilizator_id=uuid.UUID(utilizator_id))
    except gateway.Amanat as amanat:
        return f"amanat:{amanat.pana_la.isoformat()}"
    except (
        gateway.EroareGateway
    ) as exc:  # ieșire invalidă, furnizori indisponibili, apel refuzat: fluxul se încheie curat
        return f"refuzat:{type(exc).__name__}"
    except creier.RegulaCreier as exc:
        log.warning("strategia nu s-a putut propune", extra={"motiv": str(exc)[:200]})
        return "refuzat:strategie_invalida"
    return "gata"


@motor.flux(NUME_STRATEGIE, timp_maxim_sec=900)
def propune_strategia(tenant_id: str, utilizator_id: str) -> str:
    r = _strategie(tenant_id, utilizator_id)
    if r.startswith("amanat:"):
        gateway.reprogrameaza(
            gateway.Amanat(dt.datetime.fromisoformat(r.split(":", 1)[1]), "strategie"),
            propune_strategia,
            tenant_id,
            utilizator_id,
            cheie=f"strategie:{tenant_id}:reluare",
            coada=Coada.IO,
            prioritate=Prioritate.P1,
        )
        return "amanat"
    return r


def trimite_strategia(tenant_id: uuid.UUID, utilizator_id: uuid.UUID, *, cheie: str) -> str:
    return motor.trimite(
        propune_strategia,
        str(tenant_id),
        str(utilizator_id),
        coada=Coada.IO,
        prioritate=Prioritate.P1,
        cheie=cheie,
    )
