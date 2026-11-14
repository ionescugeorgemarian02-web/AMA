"""Controlul tehnic media, G6 (F8.8, docs/09 §9.4–9.5): un video final trece doar dacă formatul, imaginea,
sunetul, sincronizarea și subtitrările sunt în regulă. Totul se măsoară determinist, dintr-o singură decodare:

- format: H.264 + AAC, rezoluția și cadrele pe secundă ale canalului, `yuv420p`, sub limita de mărime;
- imagine: fără cadre negre mai lungi de 0,5 s și fără cadre înghețate mai lungi de 2 s (cu excepțiile
  intenționate);
- sunet: nivel integrat −14 LUFS ± 1, vârf sub −1 dBTP, fără tăceri mai lungi de 1,5 s;
- sincronizare: sub 100 ms între durata sunetului și a imaginii;
- subtitrări: fiecare ecran în zona sigură a canalului, niciun cuvânt tăiat (din geometria calculată la
  montaj; OCR pe cadre-eșantion: NEVERIFICAT, la migrare).

Verdictul este un `validare.Verdict` (G6, V0), cu dovezi pentru fiecare problemă.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app import validare
from app.media import ffmpeg, subtitrari, sunet

VERSIUNE = "1"
NEGRU_MAX, INGHETAT_MAX, LINISTE_MAX = 0.5, 2.0, 1.5
DESINCRONIZARE_MAX = 0.1
MB = 1024 * 1024
LIMITE_CANAL = {"tiktok": 287 * MB, "instagram": 300 * MB, "facebook": 300 * MB, "youtube": 300 * MB}  # [I]


@dataclass(frozen=True)
class Asteptari:
    canal: str = "tiktok"
    latime: int = 1080
    inaltime: int = 1920
    cadre_pe_secunda: int = 30
    ecrane: tuple[subtitrari.Ecran, ...] = ()
    intentionate: tuple[tuple[float, float], ...] = field(default_factory=tuple)  # intervale permise (îngheț)


@dataclass(frozen=True)
class Problema:
    regula: str
    detalii: str


def _intervale(text: str, cheie_start: str, cheie_sfarsit: str) -> list[tuple[float, float]]:
    """Intervalele raportate de filtru, cu cele lipite (sfârșitul unuia = începutul următorului) unite."""
    starturi = [float(x) for x in re.findall(cheie_start + r":\s*(-?[\d.]+)", text)]
    sfarsituri = [float(x) for x in re.findall(cheie_sfarsit + r":\s*(-?[\d.]+)", text)]
    brute = zip(starturi, sfarsituri + [float("inf")] * (len(starturi) - len(sfarsituri)), strict=False)
    out: list[tuple[float, float]] = []
    for a, b in sorted(brute):
        if out and a - out[-1][1] <= 0.1:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def masoara(cale: Path) -> dict[str, Any]:
    """O decodare: cadre negre, înghețate, tăceri și nivelul sonor (ebur128)."""
    r = ffmpeg.ruleaza([
        "-i", str(cale),
        "-vf", "blackdetect=d=0.1:pix_th=0.10,freezedetect=n=-60dB:d=0.5",
        "-af", "silencedetect=n=-50dB:d=0.3,ebur128=peak=true",
        "-f", "null", "-",
    ], fir=2)  # fmt: skip
    t = r.stderr
    negre = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", t)]
    inghetate = _intervale(t, r"lavfi\.freezedetect\.freeze_start", r"lavfi\.freezedetect\.freeze_end")
    linisti = _intervale(t, r"silence_start", r"silence_end")
    rez = t[t.rfind("Summary:") :]
    i = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", rez)
    p = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", rez)
    return {
        "negre": negre,
        "inghetate": inghetate,
        "linisti": linisti,
        "lufs": float(i.group(1)) if i and i.group(1) != "-inf" else -99.0,
        "varf": float(p.group(1)) if p and p.group(1) != "-inf" else -99.0,
    }


def _permis(a: float, b: float, intentionate: tuple[tuple[float, float], ...]) -> bool:
    return any(x <= a + 0.05 and b <= y + 0.05 for x, y in intentionate)


def probleme(cale: Path, a: Asteptari) -> tuple[list[Problema], dict[str, Any]]:
    out: list[Problema] = []
    info = ffmpeg.probe(cale)
    durata_fisier = float(info["format"].get("duration", 0))
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    au = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    if v is None:
        return [Problema("format", "fără pistă video")], {}
    if au is None:
        out.append(Problema("format", "fără pistă audio"))
    if v.get("codec_name") != "h264":
        out.append(Problema("format", f"codec video {v.get('codec_name')}, nu H.264"))
    if au is not None and au.get("codec_name") != "aac":
        out.append(Problema("format", f"codec audio {au.get('codec_name')}, nu AAC"))
    if (v.get("width"), v.get("height")) != (a.latime, a.inaltime):
        out.append(
            Problema("format", f"rezoluție {v.get('width')}×{v.get('height')}, nu {a.latime}×{a.inaltime}")
        )
    num, _, den = str(v.get("avg_frame_rate", "0/1")).partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    if abs(fps - a.cadre_pe_secunda) > 0.05:
        out.append(Problema("format", f"{fps:.2f} cadre pe secundă, nu {a.cadre_pe_secunda}"))
    if v.get("pix_fmt") != "yuv420p":
        out.append(Problema("format", f"format de pixeli {v.get('pix_fmt')}"))
    marime = cale.stat().st_size
    if marime > LIMITE_CANAL.get(a.canal, 287 * MB):
        out.append(Problema("format", f"{marime // MB} MB, peste limita canalului"))
    if au is not None:
        dv, da = float(v.get("duration", durata_fisier)), float(au.get("duration", durata_fisier))
        if abs(dv - da) > DESINCRONIZARE_MAX:
            out.append(Problema("sincronizare", f"sunetul durează {da:.2f} s, imaginea {dv:.2f} s"))
    m = masoara(cale)
    for x, y in m["negre"]:
        if y - x > NEGRU_MAX:
            out.append(Problema("cadre_negre", f"negru între {x:.2f} și {y:.2f} s"))
    for x, y in m["inghetate"]:
        y = min(y, durata_fisier)
        if y - x > INGHETAT_MAX and not _permis(x, y, a.intentionate):
            out.append(Problema("cadre_inghetate", f"imagine înghețată între {x:.2f} și {y:.2f} s"))
    if au is not None:
        for x, y in m["linisti"]:
            y = min(y, durata_fisier)
            if y - x > LINISTE_MAX:
                out.append(Problema("tacere", f"tăcere între {x:.2f} și {y:.2f} s"))
        if abs(m["lufs"] - sunet.TINTA_LUFS) > sunet.TOLERANTA_LU:
            out.append(Problema("nivel_sonor", f"{m['lufs']:.1f} LUFS, ținta {sunet.TINTA_LUFS:.0f} ± 1"))
        if m["varf"] > sunet.VARF_MAX_DBTP:
            out.append(Problema("nivel_sonor", f"vârf {m['varf']:.1f} dBTP, peste {sunet.VARF_MAX_DBTP:.0f}"))
    for e in a.ecrane:
        if not subtitrari.in_zona(e, a.canal, a.latime, a.inaltime):
            out.append(Problema("subtitrari", f"„{e.text}” iese din zona sigură ({e.inceput:.2f} s)"))
        if e.cutie[0] < 0 or e.cutie[2] > a.latime:
            out.append(Problema("subtitrari", f"„{e.text}” e tăiată la marginea imaginii"))
    return out, {**m, "durata": durata_fisier, "marime": marime, "fps": fps}


def verdict(cale: Path, a: Asteptari) -> tuple[validare.Verdict, dict[str, Any]]:
    p, masuri = probleme(cale, a)
    if not p:
        return validare.trece("G6", VERSIUNE, validare.Treapta.V0), masuri
    dovezi = [validare.Dovada(fragment="", regula=f"G6.{x.regula}", detalii=x.detalii) for x in p]
    return (
        validare.esec(
            "G6",
            VERSIUNE,
            validare.Treapta.V0,
            dovezi=dovezi,
            instructiune="Refă montajul: " + "; ".join(x.detalii for x in p[:4]),
        ),
        masuri,
    )
