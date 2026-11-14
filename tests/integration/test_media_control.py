"""F8.8 — controlul media (G6) și auditorul vizual (G5). „Gata când”: colecția de clipuri defecte este respinsă
integral. Clipul bun vine din montajul real; defectele se fac din el cu FFmpeg (fiecare cu un singur defect)."""

# ruff: noqa: F811
import io
import tempfile
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from app import validare
from app.config import get_settings
from app.db import sesiune_tenant
from app.media import control, ffmpeg, montaj, subtitrari, vizual
from app.media.modele import Activ
from tests.integration.utile_productie import fabrica_clienti, tenant  # noqa: F401
from tests.media_utile import lista_simpla

pytestmark = [pytest.mark.db, pytest.mark.skipif(not ffmpeg.disponibil(), reason="ffmpeg lipsește")]
COD = ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000"]

DEFECTE: dict[str, Callable[[float], list[str]]] = {
    "rezolutie": lambda d: ["-vf", "scale=720:1280", *COD],
    "cadre_pe_secunda": lambda d: ["-r", "25", *COD],
    "codec": lambda d: ["-c:v", "mpeg4", "-q:v", "5", "-c:a", "aac"],
    "fara_sunet": lambda d: ["-an", "-c:v", "copy"],
    "cadre_negre": lambda d: ["-vf", "drawbox=enable='between(t,1,2.2)':color=black:t=fill", *COD],
    "imagine_inghetata": lambda d: [
        "-vf",
        "loop=loop=100:size=1:start=20,setpts=N/30/TB",
        "-t",
        f"{d:.2f}",
        *COD,
    ],
    "tacere": lambda d: ["-af", "volume=enable='between(t,1,3.4)':volume=0", "-c:v", "copy", "-c:a", "aac"],
    "prea_tare": lambda d: ["-af", "volume=14dB", "-c:v", "copy", "-c:a", "aac"],
    "desincronizare": lambda d: ["-af", f"atrim=0:{d - 0.6:.2f}", "-c:v", "copy", "-c:a", "aac"],
}


@pytest.fixture
def clip_bun(tenant: uuid.UUID) -> Iterator[tuple[Path, control.Asteptari, float]]:
    with sesiune_tenant(tenant) as db:
        lm = lista_simpla(db, tenant, "A")
        r = montaj.produ(db, tenant, lm)
        assert r.stare == "gata", r.control
        a = db.get(Activ, r.activ_id)
        assert a is not None
        cale = Path(get_settings().media_dir) / a.cale
        yield cale, control.Asteptari(canal=lm.canal, ecrane=tuple(subtitrari.grupeaza(lm))), lm.durata


def test_colectia_de_clipuri_defecte_este_respinsa_integral(
    clip_bun: tuple[Path, control.Asteptari, float],
) -> None:
    cale, ast, durata = clip_bun
    v, masuri = control.verdict(cale, ast)
    assert v.rezultat == validare.Rezultat.TRECE, v.dovezi
    respinse: dict[str, list[str]] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for nume, args in DEFECTE.items():
            iesire = Path(tmp) / f"{nume}.mp4"
            ffmpeg.ruleaza(["-i", str(cale), *args(durata), str(iesire)], fir=4)
            vd, _ = control.verdict(iesire, ast)
            respinse[nume] = [d.regula for d in vd.dovezi] if vd.rezultat == validare.Rezultat.ESEC else []
        # subtitrări în afara zonei sigure (sub butoanele aplicației) și tăiate la marginea imaginii
        e = ast.ecrane[0]
        jos = subtitrari.Ecran(e.cuvinte, e.inceput, e.sfarsit, e.text, (e.cutie[0], 1700, e.cutie[2], 1790))
        taiata = subtitrari.Ecran(e.cuvinte, e.inceput, e.sfarsit, e.text, (-40, e.cutie[1], 900, e.cutie[3]))
        for nume, ec in (("subtitrari_jos", jos), ("subtitrari_taiate", taiata)):
            vd, _ = control.verdict(cale, control.Asteptari(canal=ast.canal, ecrane=(ec,)))
            respinse[nume] = [d.regula for d in vd.dovezi] if vd.rezultat == validare.Rezultat.ESEC else []
    asteptat = {
        "rezolutie": "G6.format", "cadre_pe_secunda": "G6.format", "codec": "G6.format", "fara_sunet": "G6.format",
        "cadre_negre": "G6.cadre_negre", "imagine_inghetata": "G6.cadre_inghetate", "tacere": "G6.tacere",
        "prea_tare": "G6.nivel_sonor", "desincronizare": "G6.sincronizare", "subtitrari_jos": "G6.subtitrari",
        "subtitrari_taiate": "G6.subtitrari",
    }  # fmt: skip
    for nume, regula in asteptat.items():
        assert regula in respinse[nume], (nume, respinse[nume])
    assert masuri["lufs"] == pytest.approx(-14, abs=1)


PALETA = ("#1E4D6B", "#F4F1EA", "#1A1A1A", "#E07A2E", "#FFFFFF")


def _coperta(*, fundal: str = "#F4F1EA", text: str = "#1A1A1A", cu_logo: bool = True, logo_turtit: bool = False,
             pata: str | None = None) -> tuple[bytes, vizual.AsteptariVizuale]:  # fmt: skip
    img = Image.new("RGB", (1080, 1350), fundal)
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(str(subtitrari.cale_font()), 80)
    d.text((100, 300), "Cafea proaspătă", font=f, fill=text)
    if pata:
        d.rectangle((0, 900, 1080, 1100), fill=pata)
    logo = Image.new("RGB", (140, 140), "#F4F1EA")
    ImageDraw.Draw(logo).ellipse((0, 0, 139, 139), fill="#1E4D6B")
    if cu_logo:
        img.paste(logo.resize((140, 60)) if logo_turtit else logo, (880, 1150))
    out, ref = io.BytesIO(), io.BytesIO()
    img.save(out, "PNG")
    logo.save(ref, "PNG")
    cutie_text = (94, 294, 100 + round(f.getlength("Cafea proaspătă")) + 6, 400)
    return out.getvalue(), vizual.AsteptariVizuale(
        paleta=PALETA, texte=((cutie_text, 80),), logo=ref.getvalue(), cutie_logo=(880, 1150, 1020, 1290),
        margini=(60, 60, 60, 60), nume="copertă")  # fmt: skip


def test_auditorul_vizual_respinge_copertile_defecte() -> None:
    bun, ast = _coperta()
    assert vizual.verdict(bun, ast).rezultat == validare.Rezultat.TRECE, vizual.probleme(bun, ast)
    defecte = {
        "logo lipsă": _coperta(cu_logo=False),
        "logo deformat": _coperta(logo_turtit=True),
        "culoare în afara paletei": _coperta(pata="#22CC22"),
        "contrast slab": _coperta(text="#D8D2C4"),
    }
    for motiv, (img, a) in defecte.items():
        p = vizual.probleme(img, a)
        assert vizual.verdict(img, a).rezultat == validare.Rezultat.ESEC, motiv
        cheie = {"logo lipsă": "logo", "logo deformat": "logo", "culoare în afara paletei": "paletei",
                 "contrast slab": "contrast"}[motiv]  # fmt: skip
        assert any(cheie in x for x in p), (motiv, p)
    img, a = _coperta()
    afara = vizual.AsteptariVizuale(
        paleta=a.paleta, texte=(((20, 294, 900, 400), 80),), margini=(60, 60, 60, 60)
    )
    assert any("zonei sigure" in x for x in vizual.probleme(img, afara))
