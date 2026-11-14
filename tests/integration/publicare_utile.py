"""Ajutoare pentru testele publicării prin API (F9): conectorul înregistrat pe platforma simulată, contul
autorizat prin ușa executorului (OAuth cu cod), livrabilul trimis. Brandul e FICTIV: „Cafeneaua Zorilor”."""

import uuid
from typing import Any
from urllib.parse import parse_qs, urlsplit

from app import productie
from app.db import sesiune_agentie, sesiune_tenant
from app.operare import efecte
from app.operare.efecte import autorizare
from app.publicare import canale

REDIRECT = "https://ama.exemplu.test/publicare/autorizare"
BRAND = "Cafeneaua Zorilor"


def autorizeaza(
    tenant: uuid.UUID,
    om: uuid.UUID,
    canal: str,
    cod: str,
    *,
    agentie: bool = True,
    setari: dict[str, Any] | None = None,
) -> str:
    """Fluxul OAuth complet; întoarce adresa de consimțământ (pentru verificări)."""
    with sesiune_tenant(tenant) as db:
        canale.configureaza(db, tenant, canal, nume=BRAND, cont_agentie=agentie, setari=setari)
        url = autorizare.url_autorizare(db, tenant, canal, redirect=REDIRECT)
    stare = parse_qs(urlsplit(url).query)["state"][0]
    with sesiune_tenant(tenant) as db:
        autorizare.finalizeaza(db, tenant, canal, cod=cod, stare=stare, redirect=REDIRECT, utilizator_id=om)
    return url


def cere(tenant: uuid.UUID, lid: uuid.UUID, payload: dict[str, Any]) -> uuid.UUID:
    with sesiune_tenant(tenant) as db:
        return efecte.cere(db, lid, payload=payload, porneste=False).efect.id


def efect(tenant: uuid.UUID, efect_id: uuid.UUID) -> efecte.Efect:
    with sesiune_tenant(tenant) as db:
        e = efecte.citeste(db, efect_id)
        assert e is not None
        return e


def livrabil_stare(tenant: uuid.UUID, lid: uuid.UUID) -> str:
    with sesiune_tenant(tenant) as db:
        lv = productie.citeste(db, lid)
        assert lv is not None
        return lv.stare


def pune_aprobarea(platforma: str, permisiune: str, stare: str, inregistrare: str | None = "x.json") -> None:
    with sesiune_agentie() as db:
        a = canale.aprobare(db, platforma, permisiune)
        assert a is not None
        a.stare, a.inregistrare = stare, (inregistrare if stare not in ("in_test", "neceruta") else None)
