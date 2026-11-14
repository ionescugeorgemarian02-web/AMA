"""F7.5 — portalul: materiale și inboxul de tendințe. „Gata când”: o fotografie încărcată apare în biblioteca de
active, cu sursă. Tipul se verifică după conținut (un executabil redenumit .jpg e refuzat)."""

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import media
from app.config import get_settings
from app.conturi import Rol
from app.db import sesiune_tenant
from tests.integration.conftest import Cont, csrf_din, login

pytestmark = pytest.mark.db
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"cafeneaua-zorilor-vitrina" * 40 + b"\xff\xd9"


def test_fotografia_incarcata_apare_in_biblioteca_cu_sursa(
    client: TestClient, fabrica_conturi: Callable[..., Cont]
) -> None:
    cont = fabrica_conturi(Rol.CLIENT_TITULAR)
    assert login(client, cont.email, cont.parola).status_code == 303
    h = client.get("/portal/materiale").text
    assert 'enctype="multipart/form-data"' in h
    r = client.post("/portal/materiale", data={"csrf_token": csrf_din(h), "descriere": "Vitrina cafenelei"},
                    files={"fisier": ("vitrina.jpg", JPEG, "image/jpeg")}, follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    with sesiune_tenant(cont.tenant_id) as db:  # type: ignore[arg-type]
        [a] = media.biblioteca.ale_clientului(db, cont.tenant_id)  # type: ignore[arg-type]
        assert (a.categorie, a.mime, a.sursa, a.nume_original) == (
            "foto",
            "image/jpeg",
            "portal",
            "vitrina.jpg",
        )
        assert a.incarcat_de == cont.id and a.descriere == "Vitrina cafenelei"
        assert media.biblioteca.citeste_fisier(a) == JPEG
        assert (Path(get_settings().media_dir) / a.cale).name == f"{a.sha256}.jpg"
    h = client.get("/portal/materiale").text
    assert "vitrina.jpg" in h and "sursa: portal" in h
    # același fișier, din nou: tot un singur activ; un executabil redenumit e refuzat după conținut
    client.post(
        "/portal/materiale", data={"csrf_token": csrf_din(h)}, files={"fisier": ("a.jpg", JPEG, "image/jpeg")}
    )
    r = client.post("/portal/materiale", data={"csrf_token": csrf_din(h)},
                    files={"fisier": ("poza.jpg", b"MZ\x90\x00" + b"\x00" * 100, "image/jpeg")})  # fmt: skip
    assert r.status_code == 422 and "tip de fișier neacceptat" in r.text
    with sesiune_tenant(cont.tenant_id) as db:  # type: ignore[arg-type]
        assert len(media.biblioteca.ale_clientului(db, cont.tenant_id)) == 1  # type: ignore[arg-type]
    # inboxul de tendințe
    r = client.post("/portal/tendinte", data={"csrf_token": csrf_din(h), "text": "https://example.org/trend cafea rece"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    h = client.get("/portal/materiale").text
    assert 'href="https://example.org/trend"' in h
    assert "✓ Încarcă logo" in client.get("/portal").text  # pasul 3 din bara de progres


def test_vizitatorul_nu_incarca_si_tipurile_detectate() -> None:
    assert media.biblioteca.detecteaza(JPEG) is media.biblioteca.TIPURI["jpeg"]
    assert media.biblioteca.detecteaza(b"\x00\x00\x00\x18ftypqt  ") is media.biblioteca.TIPURI["mov"]
    assert media.biblioteca.detecteaza(b"RIFF\x00\x00\x00\x00WEBPVP8 ") is media.biblioteca.TIPURI["webp"]
    assert media.biblioteca.detecteaza(b"<html>") is None
    with pytest.raises(media.biblioteca.FisierRefuzat):
        media.biblioteca.verifica(b"")


def test_vizitatorul_nu_poate_incarca(client: TestClient, fabrica_conturi: Callable[..., Cont]) -> None:
    cont = fabrica_conturi(Rol.CLIENT_VIZITATOR)
    assert login(client, cont.email, cont.parola).status_code == 303
    assert client.get("/portal/materiale").status_code == 403
