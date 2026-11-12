"""F1.7 — fișiere statice: sume de control, manifest, pictograme, service worker, fără cod inline în șabloane."""

import hashlib
import json
import re
import struct
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "app" / "web" / "static"
SABLOANE = ROOT / "app" / "web" / "templates"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def test_sumele_fisierelor_vendorizate_corespund_cu_vendor_md() -> None:
    vendor = STATIC / "vendor"
    md = (vendor / "VENDOR.md").read_text(encoding="utf-8")
    fisiere = sorted(p for p in vendor.iterdir() if p.suffix == ".js")
    assert len(fisiere) >= 2
    for f in fisiere:
        suma = hashlib.sha256(f.read_bytes()).hexdigest()
        assert f.name in md and suma in md, f"{f.name}: suma din VENDOR.md nu corespunde ({suma})"


def test_manifestul_este_json_valid_cu_campurile_cerute(client: TestClient) -> None:
    r = client.get("/manifest.webmanifest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/manifest+json")
    m = r.json()
    for camp in ("name", "short_name", "start_url", "display", "theme_color", "background_color", "icons"):
        assert m.get(camp), camp
    assert m["display"] == "standalone" and m["start_url"] == "/"
    scopuri = {(i["sizes"], i.get("purpose", "any")) for i in m["icons"]}
    assert {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")} <= scopuri


def _dimensiuni_png(cale: Path) -> tuple[int, int]:
    """Verifică semnătura, CRC-urile blocurilor și că IDAT se decomprimă la exact dimensiunea declarată."""
    brut = cale.read_bytes()
    assert brut[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, lat, inalt = 8, b"", 0, 0
    while pos < len(brut):
        (lung,) = struct.unpack(">I", brut[pos : pos + 4])
        tip, date = brut[pos + 4 : pos + 8], brut[pos + 8 : pos + 8 + lung]
        (crc,) = struct.unpack(">I", brut[pos + 8 + lung : pos + 12 + lung])
        assert crc == zlib.crc32(tip + date), f"CRC greșit în {cale.name}/{tip!r}"
        if tip == b"IHDR":
            lat, inalt = struct.unpack(">II", date[:8])
        elif tip == b"IDAT":
            idat += date
        pos += 12 + lung
    assert len(zlib.decompress(idat)) == inalt * (1 + lat * 4)
    return lat, inalt


def test_pictogramele_declarate_exista_si_sunt_png_reale_de_marimea_declarata(client: TestClient) -> None:
    m = client.get("/manifest.webmanifest").json()
    for icon in m["icons"]:
        assert icon["src"].startswith("/static/")
        cale = STATIC / icon["src"].removeprefix("/static/")
        lat, inalt = _dimensiuni_png(cale)
        declarat = tuple(int(x) for x in icon["sizes"].split("x"))
        assert (lat, inalt) == declarat, icon["src"]
        assert client.get(icon["src"]).headers["content-type"] == "image/png"
    assert _dimensiuni_png(STATIC / "icons" / "apple-touch-icon.png") == (180, 180)


def test_service_worker_din_radacina_cu_tip_si_antete_corecte(client: TestClient) -> None:
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/javascript")
    assert r.headers["service-worker-allowed"] == "/"
    assert r.headers["cache-control"] == "no-cache"
    sw = r.text
    # cache doar pentru /static/, niciodată HTML sau API: orice alt GET trece la rețea
    assert "pathname.startsWith('/static/')" in sw
    assert "addEventListener('push'" in sw and "addEventListener('notificationclick'" in sw
    assert "showNotification" in sw and "openWindow" in sw and "focus" in sw
    assert "/conturi" not in sw and ".html" not in sw


def test_csp_permite_doar_worker_si_manifest_din_aceeasi_origine(client: TestClient) -> None:
    csp = client.get("/healthz").headers["content-security-policy"]
    assert "worker-src 'self'" in csp and "manifest-src 'self'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert "script-src 'self';" in csp


def test_fisierele_statice_se_servesc_cu_politica_de_cache(client: TestClient) -> None:
    v = client.get("/static/vendor/htmx-2.0.4.min.js")
    assert v.status_code == 200 and "immutable" in v.headers["cache-control"]
    c = client.get("/static/css/tema.css")
    assert c.status_code == 200 and c.headers["cache-control"] == "no-cache"
    assert client.get("/static/../config.py").status_code == 404


SABLOANE_FISIERE = sorted(SABLOANE.rglob("*.html"))


def test_exista_sabloane_de_scanat() -> None:
    assert len(SABLOANE_FISIERE) >= 10


@pytest.mark.parametrize("cale", SABLOANE_FISIERE, ids=lambda p: str(p.relative_to(SABLOANE)))
def test_niciun_sablon_nu_are_cod_inline(cale: Path) -> None:
    html = cale.read_text(encoding="utf-8")
    scripturi_inline = [
        m for m in re.finditer(r"<script\b([^>]*)>", html, re.IGNORECASE) if "src=" not in m.group(1)
    ]
    assert not scripturi_inline, "script inline interzis de CSP"
    assert not re.search(r"<style\b", html, re.IGNORECASE), "bloc <style> interzis de CSP"
    assert not re.search(r"\sstyle\s*=", html, re.IGNORECASE), "atribut style= interzis de CSP"
    assert not re.search(r"\son[a-z]+\s*=", html, re.IGNORECASE), "atribut on*= interzis de CSP"
    assert "javascript:" not in html.lower()


def test_scanarea_chiar_prinde_cod_inline() -> None:
    """Garda de mai sus nu trebuie să fie oarbă."""
    rau = '<p style="x" onclick="y()"></p><script>alert(1)</script>'
    assert re.search(r"\sstyle\s*=", rau) and re.search(r"\son[a-z]+\s*=", rau)
    assert [m for m in re.finditer(r"<script\b([^>]*)>", rau) if "src=" not in m.group(1)]


def test_iconitele_se_pot_regenera_identic(tmp_path: Path) -> None:
    import subprocess
    import sys

    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "genereaza_icoane.py"), str(tmp_path)],
        check=True,
        capture_output=True,
    )
    for nume in ("icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png"):
        assert (tmp_path / nume).read_bytes() == (STATIC / "icons" / nume).read_bytes(), nume


def test_manifestul_este_json_pe_disc() -> None:
    json.loads((STATIC / "manifest.webmanifest").read_text(encoding="utf-8"))
