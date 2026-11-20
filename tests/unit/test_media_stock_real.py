"""Furnizorii de stock reali (F-idee, „Imagini reale”) pe răspunsuri JSON fictive, fără rețea: căutarea,
licențele, alegerea fișierelor, atribuirea, transcodarea verticală (ffmpeg real, pe un webm generat local)."""

import io
import json
import subprocess
import sys
import urllib.parse
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from app.media import ffmpeg, furnizori, licente
from app.media import stock_commons as sc
from app.media.stock_pexels import StockPexels, alege_fisier_video
from app.media.stock_pixabay import StockPixabay, alege_varianta_video

CAUTARE = {
    "query": {
        "search": [
            {"ns": 6, "title": "File:Chain rotating.webm"},
            {"ns": 6, "title": "File:Chain NC.webm"},
            {"ns": 6, "title": "File:Too short.ogv"},
            {"ns": 6, "title": "File:Chain cc0.webm"},
        ]
    }
}


def _pagina(titlu: str, *, mime: str = "video/webm", licenta: str = "CC BY-SA 4.0", durata: float | None = 12.0,
            latime: int = 1920, inaltime: int = 1080, artist: str = '<a href="//x">Ana Pop</a>') -> dict[str, Any]:  # fmt: skip
    nume = titlu.removeprefix("File:")
    info: dict[str, Any] = {
        "url": f"https://upload.wikimedia.org/x/{nume}",
        "thumburl": f"https://upload.wikimedia.org/thumb/{nume}/1080px.jpg",
        "descriptionurl": f"https://commons.wikimedia.org/wiki/{titlu}",
        "width": latime, "height": inaltime, "mime": mime,
        "extmetadata": {
            "LicenseShortName": {"value": licenta},
            "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"},
            "Artist": {"value": artist},
            "ImageDescription": {"value": "Lanț de <b>bicicletă</b> în mișcare"},
        },
    }  # fmt: skip
    if durata is not None:
        info["metadata"] = [{"name": "length", "value": durata}]
    return {"title": titlu, "imageinfo": [info]}


INFO = {
    "query": {
        "pages": [
            _pagina("File:Chain cc0.webm", licenta="CC0"),
            _pagina("File:Chain rotating.webm"),
            _pagina("File:Chain NC.webm", licenta="CC BY-NC-SA 4.0"),
            _pagina("File:Too short.ogv", mime="application/ogg", licenta="Public domain", durata=1.5),
        ]
    }
}


class HttpFals:
    def __init__(self, raspunsuri: dict[str, Any]) -> None:
        self.raspunsuri, self.cereri = raspunsuri, []  # type: list[tuple[str, Mapping[str, str]]]

    def __call__(self, url: str, antete: Mapping[str, str]) -> bytes:
        self.cereri.append((url, antete))
        for prefix, r in self.raspunsuri.items():
            if prefix in url:
                return r if isinstance(r, bytes) else json.dumps(r).encode()
        raise AssertionError(f"cerere neașteptată: {url}")


@pytest.mark.parametrize(
    ("nume", "ok"),
    [("CC0", True), ("Public domain", True), ("PD-US", True), ("CC BY 4.0", True), ("CC BY-SA 3.0", True),
     ("cc-by-sa-4.0", True), ("CC BY-NC 4.0", False), ("CC BY-ND 2.0", False), ("CC BY-NC-SA 4.0", False),
     ("Fair use", False), ("GFDL", False), ("", False)],
)  # fmt: skip
def test_filtrul_de_licente(nume: str, ok: bool) -> None:
    assert sc.licenta_libera(nume) is ok


def test_cautarea_video_parseaza_filtreaza_si_pastreaza_ordinea() -> None:
    http = HttpFals({"list=search": CAUTARE, "prop=imageinfo": INFO})
    s = sc.StockCommons(http=http)
    rez = s.cauta("bicycle chain rotating", tip="video", n=3)
    assert [r.identificator for r in rez] == ["File:Chain rotating.webm", "File:Chain cc0.webm"]
    assert dict(s.refuzate) == {
        "File:Chain NC.webm": "licență CC BY-NC-SA 4.0",
        "File:Too short.ogv": "durată 1.5 s",
    }
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(http.cereri[0][0]).query))
    assert q["srnamespace"] == "6" and q["srsearch"].endswith("filetype:video")
    q2 = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(http.cereri[1][0]).query))
    assert "metadata" in q2["iiprop"] and "iiurlwidth" not in q2
    r = rez[0]
    assert (
        r.url_fisier == "https://upload.wikimedia.org/x/Chain rotating.webm"
    )  # originalul, pentru transcodare
    assert r.autor == "Ana Pop" and r.licenta == "CC BY-SA 4.0" and r.tip == "video"
    assert r.descriere == "Lanț de bicicletă în mișcare"


def test_atribuirea_completeaza_licenta_de_stock() -> None:
    f = sc.parseaza_info(INFO)[1]
    r = sc.rezultat(f, "video")
    assert "Ana Pop" in r.licenta_text and "CC BY-SA 4.0" in r.licenta_text and r.url in r.licenta_text
    lic = {"tip": "stock", "statut": "verificata", "furnizor": r.furnizor, "identificator": r.identificator,
           "autor": r.autor, "url": r.url, "copie": r.licenta_text, "descarcat_la": "2026-01-01T00:00:00+00:00"}  # fmt: skip
    assert licente.probleme(lic) == []


def test_alegerea_fotografiilor() -> None:
    pagini = {"query": {"pages": [
        _pagina("File:Mic.jpg", mime="image/jpeg", latime=640, durata=None),
        _pagina("File:Desen.svg", mime="image/svg+xml", durata=None),
        _pagina("File:Bun.png", mime="image/png", latime=3000, durata=None),
    ]}}  # fmt: skip
    fis = {f.titlu: sc.motiv_refuz(f, "foto") for f in sc.parseaza_info(pagini)}
    assert fis == {
        "File:Mic.jpg": "lățime 640 px",
        "File:Desen.svg": "mime image/svg+xml",
        "File:Bun.png": "",
    }
    r = sc.rezultat(sc.parseaza_info(pagini)[2], "foto")
    assert r.url_fisier.endswith("1080px.jpg")  # miniatura de 1080 px
    png = io.BytesIO()
    Image.new("RGBA", (1080, 1500), (10, 20, 30, 255)).save(png, "PNG")
    http = HttpFals({"1080px.jpg": png.getvalue()})
    corp = sc.StockCommons(http=http).descarca(r)
    assert corp[:2] == b"\xff\xd8"


def test_filtrul_vertical() -> None:
    opt, f = sc.filtru_vertical(1920, 1080)
    assert opt == "-vf" and "crop='min(iw,ih*9/16)'" in f and "scale=1080:1920" in f
    opt, f = sc.filtru_vertical(3000, 1000)  # panoramic: fundal estompat
    assert opt == "-filter_complex" and "boxblur" in f
    cmd = sc.comanda_transcodare("in.webm", "out.mp4", latime=1920, inaltime=1080)
    assert cmd[cmd.index("-t") + 1] == "15" and "-an" in cmd and cmd[cmd.index("-c:v") + 1] == "libx264"


@pytest.mark.skipif(not ffmpeg.disponibil(), reason="ffmpeg lipsește")
@pytest.mark.parametrize(("dim", "durata"), [("640x360", 4), ("1500x500", 3.5)])
def test_transcodarea_reala_la_1080x1920_h264(tmp_path: Path, dim: str, durata: float) -> None:
    sursa = tmp_path / "s.webm"
    ffmpeg.ruleaza(["-f", "lavfi", "-i", f"testsrc=s={dim}:r=25:d={durata}", "-f", "lavfi", "-i",
                    f"sine=d={durata}", "-shortest", "-c:v", "libvpx", "-b:v", "300k", "-c:a", "libvorbis",
                    str(sursa)])  # fmt: skip
    r = furnizori.RezultatStock("wikimedia-commons", "File:s.webm", "A", "https://c/x", "video", "t", "d",
                                url_fisier="https://upload.wikimedia.org/s.webm")  # fmt: skip
    corp = sc.StockCommons(http=HttpFals({"s.webm": sursa.read_bytes()})).descarca(r)
    iesire = tmp_path / "o.mp4"
    iesire.write_bytes(corp)
    info = ffmpeg.probe(iesire)
    video = [s for s in info["streams"] if s["codec_type"] == "video"]
    assert len(video) == 1 and len(info["streams"]) == 1  # fără sunet
    assert (video[0]["width"], video[0]["height"], video[0]["codec_name"]) == (1080, 1920, "h264")
    assert float(info["format"]["duration"]) <= 15.1


@pytest.mark.skipif(not ffmpeg.disponibil(), reason="ffmpeg lipsește")
def test_clipul_prea_scurt_e_refuzat(tmp_path: Path) -> None:
    sursa = tmp_path / "s.webm"
    ffmpeg.ruleaza(["-f", "lavfi", "-i", "testsrc=s=320x240:r=10:d=1", "-c:v", "libvpx", str(sursa)])
    with pytest.raises(ValueError, match="prea scurt"):
        sc.transcodeaza_vertical(sursa.read_bytes())


def test_pexels_alege_vertical_hd_si_trimite_cheia_in_antet() -> None:
    fisiere = [
        {"file_type": "video/mp4", "width": 3840, "height": 2160, "link": "https://p/4k.mp4"},
        {"file_type": "video/mp4", "width": 1080, "height": 1920, "link": "https://p/v1080.mp4"},
        {"file_type": "video/mp4", "width": 720, "height": 1280, "link": "https://p/v720.mp4"},
    ]
    assert alege_fisier_video(fisiere)["link"] == "https://p/v1080.mp4"  # type: ignore[index]
    raspuns = {"videos": [
        {"id": 7, "duration": 12, "url": "https://www.pexels.com/video/lant-7/", "user": {"name": "Ion"},
         "video_files": fisiere},
        {"id": 8, "duration": 90, "url": "https://www.pexels.com/video/lung-8/", "user": {"name": "X"},
         "video_files": fisiere},
    ]}  # fmt: skip
    http = HttpFals({"api.pexels.com/videos": raspuns})
    rez = StockPexels(cheie="k-fals", http=http).cauta("chain", tip="video", n=3)
    assert [r.identificator for r in rez] == ["video-7"]  # cel de 90 s e prea lung
    assert http.cereri[0][1]["Authorization"] == "k-fals" and "orientation=portrait" in http.cereri[0][0]
    assert (
        rez[0].autor == "Ion" and "Pexels" in rez[0].licenta_text and rez[0].url_fisier.endswith("v1080.mp4")
    )
    foto = {"photos": [{"id": 1, "width": 3000, "url": "https://www.pexels.com/photo/1/", "photographer": "Ana",
                        "alt": "lanț", "src": {"large2x": "https://images.pexels.com/1.jpg"}}]}  # fmt: skip
    [f] = StockPexels(cheie="k", http=HttpFals({"api.pexels.com/v1": foto})).cauta("chain")
    assert (f.tip, f.autor, f.url_fisier) == ("foto", "Ana", "https://images.pexels.com/1.jpg")


def test_pixabay_alege_varianta_si_parseaza() -> None:
    variante = {
        "large": {"url": "https://cdn.pixabay.com/l.mp4", "width": 3840, "height": 2160},
        "medium": {"url": "https://cdn.pixabay.com/m.mp4", "width": 1920, "height": 1080},
        "small": {"url": "https://cdn.pixabay.com/s.mp4", "width": 1280, "height": 720},
        "tiny": {"url": "", "width": 640, "height": 360},
    }
    assert alege_varianta_video(variante)["url"] == "https://cdn.pixabay.com/m.mp4"  # type: ignore[index]
    raspuns = {"hits": [{"id": 5, "duration": 20, "pageURL": "https://pixabay.com/videos/5/", "user": "Mara",
                         "tags": "chain, bicycle", "videos": variante}]}  # fmt: skip
    http = HttpFals({"pixabay.com/api/videos": raspuns})
    [r] = StockPixabay(cheie="k", http=http).cauta("chain", tip="video")
    assert (r.autor, r.url, r.licenta) == ("Mara", "https://pixabay.com/videos/5/", "Pixabay Content License")
    foto = {"hits": [{"id": 9, "imageWidth": 4000, "pageURL": "https://pixabay.com/photos/9/", "user": "Dan",
                      "tags": "lanț", "largeImageURL": "https://pixabay.com/get/9.jpg"}]}  # fmt: skip
    http2 = HttpFals({"pixabay.com/api/": foto})
    [f] = StockPixabay(cheie="k", http=http2).cauta("chain")
    assert f.url_fisier == "https://pixabay.com/get/9.jpg" and "orientation=vertical" in http2.cereri[0][0]


def test_furnizorii_cu_cheie_refuza_fara_cheie(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    with pytest.raises(ValueError, match="PEXELS_API_KEY"):
        StockPexels()
    with pytest.raises(ValueError, match="PIXABAY_API_KEY"):
        StockPixabay()


def test_alegerea_furnizorului_din_mediu(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    for k in ("AMA_STOCK", "PEXELS_API_KEY", "PIXABAY_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert isinstance(furnizori.stock_din_mediu(), furnizori.StockSimulat)  # AMA_ENV=test
    monkeypatch.setenv("PEXELS_API_KEY", "k")
    assert isinstance(
        furnizori.stock_din_mediu(), furnizori.StockSimulat
    )  # în teste doar la cerere explicită
    monkeypatch.setenv("AMA_STOCK", "commons")
    assert isinstance(furnizori.stock_din_mediu(), sc.StockCommons)
    monkeypatch.delenv("AMA_STOCK")
    monkeypatch.setenv("AMA_ENV", "dev")
    get_settings.cache_clear()
    try:
        assert isinstance(furnizori.stock_din_mediu(), StockPexels)
        monkeypatch.delenv("PEXELS_API_KEY")
        monkeypatch.setenv("PIXABAY_API_KEY", "k")
        assert isinstance(furnizori.stock_din_mediu(), StockPixabay)
        monkeypatch.delenv("PIXABAY_API_KEY")
        assert isinstance(furnizori.stock_din_mediu(), sc.StockCommons)
    finally:
        monkeypatch.setenv("AMA_ENV", "test")
        get_settings.cache_clear()


def test_scriptul_de_proba_porneste() -> None:
    rad = Path(__file__).resolve().parents[2]
    r = subprocess.run([sys.executable, str(rad / "scripts/stock_proba.py"), "--help"], capture_output=True, text=True,
                       check=False, cwd=rad)  # fmt: skip
    assert r.returncode == 0 and "--tip" in r.stdout


class _Raspuns(io.BytesIO):
    def __enter__(self) -> "_Raspuns":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _urlopen_cu(raspunsuri: list[Any], cereri: list[str]) -> Any:
    def urlopen(cerere: Any, timeout: float) -> _Raspuns:
        cereri.append(cerere.full_url)
        r = raspunsuri.pop(0)
        if isinstance(r, Exception):
            raise r
        return _Raspuns(r)

    return urlopen


def _http_error(cod: int, retry_after: str | None = None) -> Any:
    import email.message
    import urllib.error

    antete = email.message.Message()
    if retry_after is not None:
        antete["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://commons.wikimedia.org/w/api.php", cod, "x", antete, None)


def test_http_get_respecta_limitarea_de_rata(monkeypatch: pytest.MonkeyPatch) -> None:
    """429 (cu și fără `Retry-After`) și 503 se reîncearcă după pauza cerută; cererile sunt rărite."""
    cereri: list[str] = []
    raspunsuri = [_http_error(429, "7"), _http_error(429), _http_error(503, "500"), b"{}"]
    monkeypatch.setattr(sc.urllib.request, "urlopen", _urlopen_cu(raspunsuri, cereri))
    pauze: list[float] = []
    assert sc.http_get("https://commons.wikimedia.org/w/api.php?q=1", {}, dormi=pauze.append) == b"{}"
    assert len(cereri) == 4
    lungi = [p for p in pauze if p > sc.PAUZA_MIN]  # fără pauzele de rărire (≤ 1 s)
    assert lungi == [7.0, 4.0, sc.ASTEPTARE_MAX]


def test_http_get_renunta_dupa_limitarea_persistenta_si_la_4xx(monkeypatch: pytest.MonkeyPatch) -> None:
    cereri: list[str] = []
    monkeypatch.setattr(
        sc.urllib.request, "urlopen", _urlopen_cu([_http_error(429)] * sc.INCERCARI_LIMITARE, cereri)
    )
    with pytest.raises(sc.urllib.error.HTTPError, match="429"):
        sc.http_get("https://commons.wikimedia.org/w/api.php", {}, dormi=lambda _: None)
    assert len(cereri) == sc.INCERCARI_LIMITARE
    cereri.clear()
    monkeypatch.setattr(sc.urllib.request, "urlopen", _urlopen_cu([_http_error(403)], cereri))
    with pytest.raises(sc.urllib.error.HTTPError, match="403"):
        sc.http_get("https://commons.wikimedia.org/w/api.php", {}, dormi=lambda _: None)
    assert len(cereri) == 1  # un refuz (ex. proxy-ul local) nu se reîncearcă
