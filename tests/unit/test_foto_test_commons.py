"""Scriptul fotografiilor din Wikimedia Commons (F-editorial, decizia 8): parsarea răspunsurilor, pe JSON fictiv.
Fără rețea (CI nu face apeluri reale în testele obișnuite)."""

import importlib.util
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("foto_test_commons", ROOT / "scripts" / "foto_test_commons.py")
assert spec and spec.loader
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)

CAUTARE = {
    "batchcomplete": True,
    "query": {
        "searchinfo": {"totalhits": 3},
        "search": [
            {"ns": 6, "title": "File:Chain on cassette.jpg"},
            {"ns": 6, "title": "File:Drivetrain diagram.svg"},
            {"ns": 6, "title": "File:Brake caliper.JPEG"},
        ],
    },
}


def _pagina(
    titlu: str, *, mime: str = "image/jpeg", latime: int = 4000, licenta: str = "CC BY-SA 4.0"
) -> dict:
    return {
        "title": titlu,
        "imageinfo": [{
            "width": latime, "height": 3000, "mime": mime,
            "url": f"https://upload.wikimedia.org/x/{titlu[5:]}",
            "thumburl": f"https://upload.wikimedia.org/x/1080px-{titlu[5:]}",
            "descriptionurl": f"https://commons.wikimedia.org/wiki/{titlu}",
            "extmetadata": {
                "LicenseShortName": {"value": licenta},
                "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"},
                "Artist": {"value": '<a href="//commons.wikimedia.org/wiki/User:Foto">Foto&amp;Co</a>'},
            },
        }],
    }  # fmt: skip


def test_cautarea_pastreaza_doar_fisierele_jpeg_in_ordine() -> None:
    assert fc.parseaza_cautare(CAUTARE) == ["File:Chain on cassette.jpg", "File:Brake caliper.JPEG"]
    assert fc.parseaza_cautare({}) == []
    q = urllib.parse.parse_qs(urllib.parse.urlparse(fc.url_cautare("bicycle chain")).query)
    assert q["list"] == ["search"] and q["srnamespace"] == ["6"]
    i = urllib.parse.parse_qs(urllib.parse.urlparse(fc.url_info(["File:A.jpg", "File:B.jpg"])).query)
    assert (
        i["prop"] == ["imageinfo"]
        and i["iiurlwidth"] == ["1080"]
        and i["titles"] == ["File:A.jpg|File:B.jpg"]
    )
    assert set(i["iiprop"][0].split("|")) >= {"url", "extmetadata", "size"}


def test_info_formatversion_2_si_1_autorul_fara_html() -> None:
    v2 = {
        "query": {
            "pages": [_pagina("File:B.jpg"), _pagina("File:A.jpg"), {"title": "File:C.jpg", "missing": True}]
        }
    }
    c = fc.parseaza_info(v2, ["File:A.jpg", "File:B.jpg"])
    assert [x.titlu for x in c] == ["File:A.jpg", "File:B.jpg"]
    assert c[0].autor == "Foto&Co" and c[0].licenta == "CC BY-SA 4.0" and c[0].latime == 4000
    assert c[0].url_fisier.endswith("1080px-A.jpg") and fc.acceptat(c[0]) == ""
    v1 = {"query": {"pages": {"12": _pagina("File:A.jpg")}}}
    assert fc.parseaza_info(v1)[0].titlu == "File:A.jpg"


def test_filtrele_licenta_mime_latime() -> None:
    for bun in ("CC0", "Public domain", "CC BY 2.0", "CC BY-SA 3.0 de", "cc by-sa 4.0"):
        assert fc.licenta_libera(bun), bun
    for rau in ("CC BY-NC 2.0", "CC BY-NC-SA 4.0", "CC BY-ND 4.0", "GFDL", "", "All rights reserved"):
        assert not fc.licenta_libera(rau), rau
    [png] = fc.parseaza_info({"query": {"pages": [_pagina("File:P.jpg", mime="image/png")]}})
    [mic] = fc.parseaza_info({"query": {"pages": [_pagina("File:M.jpg", latime=640)]}})
    [nc] = fc.parseaza_info({"query": {"pages": [_pagina("File:N.jpg", licenta="CC BY-NC 2.0")]}})
    assert fc.acceptat(png).startswith("mime") and fc.acceptat(mic).startswith("lățime")
    assert fc.acceptat(nc).startswith("licență")


def test_fiecare_subiect_are_cautari_de_rezerva_si_subiecte_in_romana() -> None:
    assert set(fc.CAUTARI) == {"transmisie", "frana", "deviz"}
    assert all(len(c) >= 3 for c in fc.CAUTARI.values())
    assert any("bancul de lucru" in s for _, s in fc.CAUTARI["deviz"])  # rezerva: bancul mecanicului
    assert fc.UA == "AMA-test/1.0"
