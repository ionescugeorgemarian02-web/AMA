"""F4.2 — originalele colectate pe disc: nume doar din identificatori și hash, scriere atomică, fără ieșire din director."""

import hashlib
import uuid
from pathlib import Path

import pytest

from app.cercetare import stocare
from app.config import get_settings


@pytest.fixture(autouse=True)
def _media(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMA_MEDIA_DIR", str(tmp_path / "media"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_originalul_se_scrie_sub_client_si_sursa_cu_numele_hash_ului_si_este_idempotent() -> None:
    t, s = uuid.uuid4(), uuid.uuid4()
    corp = "<p>Prăjim marți și vineri.</p>".encode()
    h, rel = stocare.scrie(t, s, corp, "text/html; charset=utf-8")
    assert h == hashlib.sha256(corp).hexdigest() and rel == f"{t}/surse/{s}/{h}.html"
    assert stocare.citeste(rel) == corp
    assert stocare.scrie(t, s, corp, "text/html") == (h, rel)  # același conținut, același fișier
    assert [p.name for p in (stocare.radacina() / f"{t}/surse/{s}").iterdir()] == [
        f"{h}.html"
    ]  # fără fișiere temporare
    assert stocare.scrie(t, s, b"alt text", "text/markdown")[1].endswith(".md")
    assert stocare.scrie(t, s, b"\x00\x01", "application/octet-stream")[1].endswith(".bin")


@pytest.mark.parametrize("rau", ["../../etc/passwd", "../x", "/etc/passwd", "a/../../b"])
def test_citirea_nu_poate_iesi_din_directorul_de_media(rau: str) -> None:
    with pytest.raises(ValueError):
        stocare.citeste(rau)


def test_numele_de_fisier_nesigur_este_refuzat() -> None:
    with pytest.raises(ValueError):
        stocare.cale_relativa(uuid.uuid4(), uuid.uuid4(), "../../x", "html")
