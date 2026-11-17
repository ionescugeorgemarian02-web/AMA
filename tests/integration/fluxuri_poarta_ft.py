"""Fluxurile lunii simulate a porții FT: o zi = un job care publică la o platformă SIMULATĂ (HTTP real, transport în
proces); unele zile platforma răspunde 500 sau 429, alteori refuză (400), iar producția refuză o tranziție."""

import httpx

from app.connectors.publicare.baza import ClientHttp
from app.db import sesiune_tenant
from app.operare import evenimente, motor


def raspuns_platforma(zi: int) -> int:
    if zi % 7 == 3:
        return 500
    if zi % 10 == 5:
        return 429
    if zi % 11 == 8:
        return 400
    return 200


def _platforma(cerere: httpx.Request) -> httpx.Response:  # SIMULAT: platforma de publicare
    zi = int(cerere.url.path.rsplit("/", 1)[-1])
    return httpx.Response(raspuns_platforma(zi), json={"id": f"post-{zi}"})


@motor.pas("poarta_ft.publica")
def _publica(tenant_id: str, zi: int) -> str:
    ClientHttp("https://platforma.simulata.test", transport=httpx.MockTransport(_platforma)).cere(
        "POST", f"/feed/{zi}"
    )
    return "publicat"


@motor.pas("poarta_ft.productie")
def _productie(tenant_id: str, zi: int) -> str:
    import uuid

    with sesiune_tenant(uuid.UUID(tenant_id)) as db:
        evenimente.emite(
            db, "livrabil.tranzitie_refuzata", sursa="productie", obiect_tip="livrabil", obiect_id=f"zi-{zi}",
            date={"motiv": "versiunea nu a trecut validarea"},
        )  # fmt: skip
    return "refuzat"


@motor.flux("poarta_ft.zi")
def zi(tenant_id: str, numar: int) -> str:
    if numar % 9 == 4:
        return _productie(tenant_id, numar)
    return _publica(tenant_id, numar)
