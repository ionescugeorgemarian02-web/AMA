"""Randarea unei liste de montaj cu FFmpeg (F8.6, docs/14 §14.5 pasul 7, §14.9): formatele A, B și E.

Programul determinist traduce lista în graful de filtre: fiecare scenă se aduce la cadrul țintă (umplere sau
centrare), fotografiile primesc mișcarea lentă (zoom / panoramare, `zoompan`), scenele se lipesc, apoi se pun
subtitrările (F8.7) și sunetul. Ieșirea: H.264 + AAC, 30 de cadre pe secundă, `yuv420p`, pornire rapidă.
Calitatea `ciorna` randează la jumătate de rezoluție, mai repede (14.11).
"""

import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.media import ffmpeg, lista

FUNDAL_CENTRAT = "0x1E1E1E"


@dataclass(frozen=True)
class Intrari:
    """Căile pe disc ale activelor din listă."""

    scene: dict[str, Path]  # activ_id (str) -> fișier
    categorii: dict[str, str]  # activ_id (str) -> foto / video
    voce: Path
    muzica: Path | None = None


def _miscare(m: str, cadre: int) -> tuple[str, str, str]:
    """(zoom, x, y) pentru `zoompan`; `on` = numărul cadrului de ieșire."""
    centru_x, centru_y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    n = max(1, cadre - 1)
    if m == "zoom_in":
        return f"1+0.12*on/{n}", centru_x, centru_y
    if m == "zoom_out":
        return f"1.12-0.12*on/{n}", centru_x, centru_y
    if m == "panoramare_stanga":
        return "1.12", f"(iw-iw/zoom)*(1-on/{n})", centru_y
    if m == "panoramare_dreapta":
        return "1.12", f"(iw-iw/zoom)*on/{n}", centru_y
    return "1", centru_x, centru_y


def _incadrare(s: lista.Scena, w: int, h: int) -> str:
    if s.incadrare == "centrat":
        return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={FUNDAL_CENTRAT}")  # fmt: skip
    return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"


def comanda(
    lm: lista.ListaMontaj,
    intrari: Intrari,
    iesire: Path,
    *,
    ass: Path | None = None,
    sunet: Path | None = None,
    calitate: str = "final",
) -> list[str]:
    """Argumentele FFmpeg pentru listă. `sunet`: pista finală deja mixată (F8.7); altfel vocea, completată cu
    liniște până la durata listei."""
    w, h = (lm.latime, lm.inaltime) if calitate == "final" else (lm.latime // 2, lm.inaltime // 2)
    fps = lm.cadre_pe_secunda
    args: list[str] = []
    filtre: list[str] = []
    for i, s in enumerate(lm.scene):
        cheie = str(s.activ_id)
        d = round(s.sfarsit - s.inceput, 3)
        cadre = max(1, round(s.sfarsit * fps) - round(s.inceput * fps))  # granițele pe cadre: suma = durata
        if intrari.categorii[cheie] == "foto":
            args += ["-i", str(intrari.scene[cheie])]
            z, x, y = _miscare(s.miscare, cadre)
            filtre.append(
                f"[{i}:v]{_incadrare(s, w, h)},setsar=1,"
                f"zoompan=z='{z}':x='{x}':y='{y}':d={cadre}:s={w}x{h}:fps={fps},"
                f"trim=end_frame={cadre},setpts=PTS-STARTPTS[s{i}]"
            )
        else:
            args += ["-ss", f"{s.sursa_de_la:.3f}", "-t", f"{d + 0.5:.3f}", "-i", str(intrari.scene[cheie])]
            filtre.append(
                f"[{i}:v]{_incadrare(s, w, h)},setsar=1,fps={fps},"
                f"trim=end_frame={cadre},setpts=PTS-STARTPTS[s{i}]"
            )
    n = len(lm.scene)
    lipite = "".join(f"[s{i}]" for i in range(n))
    video = f"{lipite}concat=n={n}:v=1:a=0,format=yuv420p"
    if ass is not None:
        fonturi = Path(get_settings().media_fonturi)
        video += f",ass={ass}:fontsdir={fonturi}"
    filtre.append(video + "[v]")
    args += ["-i", str(sunet or intrari.voce)]
    filtre.append(f"[{n}:a]aresample=48000,apad,atrim=0:{lm.durata:.3f}[a]")
    preset = get_settings().media_preset if calitate == "final" else "ultrafast"
    args += [
        "-filter_complex", ";".join(filtre),
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", preset, "-crf", "23" if calitate == "final" else "30",
        "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
        "-t", f"{lm.durata:.3f}", "-movflags", "+faststart", str(iesire),
    ]  # fmt: skip
    return args


def randeaza(
    lm: lista.ListaMontaj,
    intrari: Intrari,
    *,
    ass: Path | None = None,
    sunet: Path | None = None,
    calitate: str = "final",
) -> tuple[bytes, ffmpeg.Rulare]:
    with tempfile.TemporaryDirectory() as d:
        iesire = Path(d) / "video.mp4"
        r = ffmpeg.ruleaza(
            comanda(lm, intrari, iesire, ass=ass, sunet=sunet, calitate=calitate),
            fir=get_settings().media_fire,
        )
        return iesire.read_bytes(), r
