"""Auditorul vizual, G5 (F8.8, docs/09 §9.4): coperți, creative și cadre-cheie. Determinist, din pixeli:

- logo lipsă sau deformat: zona așteptată se compară cu logoul redimensionat (diferența medie pe canal);
- culori în afara paletei: culorile dominante (peste 5% din suprafață, în afara zonelor de fotografie) trebuie
  să fie aproape de o culoare a brandului;
- contrast slab: în fiecare cutie de text, cele două culori dominante au raportul WCAG ≥ 4,5 (≥ 3 la text
mare);
- text în afara zonei sigure: cutiile de text stau în marginile canalului.
"""

import io
from collections import Counter
from dataclasses import dataclass

from PIL import Image

from app import validare

VERSIUNE = "1"
DISTANTA_PALETA = 70.0  # [I] distanța RGB până la cea mai apropiată culoare a brandului
DIFERENTA_LOGO = 28.0  # [I] diferența medie pe canal (0–255)
CONTRAST_MIN, CONTRAST_MIN_MARE = 4.5, 3.0
COTA_DOMINANTA = 0.05

Cutie = tuple[int, int, int, int]


@dataclass(frozen=True)
class AsteptariVizuale:
    paleta: tuple[str, ...]
    texte: tuple[tuple[Cutie, int], ...] = ()  # (cutia, mărimea fontului)
    logo: bytes | None = None
    cutie_logo: Cutie | None = None
    zone_foto: tuple[Cutie, ...] = ()  # fotografii: culorile lor nu se judecă după paletă
    margini: tuple[int, int, int, int] = (0, 0, 0, 0)  # sus, jos, stânga, dreapta
    nume: str = "imagine"


def rgb(hex_: str) -> tuple[int, int, int]:
    return int(hex_[1:3], 16), int(hex_[3:5], 16), int(hex_[5:7], 16)


def luminanta(c: tuple[int, int, int]) -> float:
    def lin(v: int) -> float:
        x = v / 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(v) for v in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = sorted((luminanta(a), luminanta(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _dominante(img: Image.Image, n: int) -> list[tuple[float, tuple[int, int, int]]]:
    mic = img.convert("RGB").resize((max(1, img.width // 4), max(1, img.height // 4)))
    q = mic.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    pal: list[int] = [int(x) for x in (q.getpalette() or [])]
    total = mic.width * mic.height
    out = []
    for cnt, ix in sorted(q.getcolors() or [], reverse=True):
        idx = int(ix)  # type: ignore[call-overload]
        out.append((cnt / total, (pal[3 * idx], pal[3 * idx + 1], pal[3 * idx + 2])))
    return out


def contrast_text(zona: Image.Image) -> float | None:
    """Contrastul dintre fundalul cutiei (culoarea cea mai frecventă) și miezul literelor: cea mai
    contrastantă
    culoare care acoperă măcar 1% din pixelii diferiți de fundal (marginile netezite și zgomotul nu
    contează)."""
    date = zona.convert("RGB").tobytes()
    numar = Counter((date[i], date[i + 1], date[i + 2]) for i in range(0, len(date), 3))
    fundal = numar.most_common(1)[0][0]
    diferite = {c: n for c, n in numar.items() if contrast(c, fundal) > 1.15}
    if not diferite:
        return None
    prag = max(3, sum(diferite.values()) // 100)
    frecvente = [c for c, n in diferite.items() if n >= prag] or list(diferite)
    return max(contrast(c, fundal) for c in frecvente)


def _dist(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return float(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)) ** 0.5)


def probleme(imagine: bytes, a: AsteptariVizuale) -> list[str]:
    img = Image.open(io.BytesIO(imagine)).convert("RGB")
    w, h = img.size
    out: list[str] = []
    if a.logo is not None and a.cutie_logo is not None:
        x0, y0, x1, y1 = a.cutie_logo
        zona = img.crop(a.cutie_logo)
        ref = Image.open(io.BytesIO(a.logo)).convert("RGB").resize((x1 - x0, y1 - y0))
        dif = sum(abs(p - q) for p, q in zip(zona.tobytes(), ref.tobytes(), strict=True)) / max(
            1, len(ref.tobytes())
        )
        if dif > DIFERENTA_LOGO:
            out.append(f"logo lipsă sau deformat (diferență {dif:.0f})")
    masca = img.copy()
    for z in a.zone_foto:
        masca.paste((0, 0, 0), z)
    paleta = [rgb(x) for x in a.paleta]
    acoperit = sum((c[2] - c[0]) * (c[3] - c[1]) for c in a.zone_foto) / (w * h)
    for cota, c in _dominante(masca, 8):
        if a.zone_foto and _dist(c, (0, 0, 0)) < 1 and cota <= acoperit + 0.02:
            continue
        if cota >= COTA_DOMINANTA and min(_dist(c, p) for p in paleta) > DISTANTA_PALETA:
            out.append(
                f"culoare în afara paletei: #{c[0]:02X}{c[1]:02X}{c[2]:02X} ({cota:.0%} din suprafață)"
            )
    sus, jos, st, dr = a.margini
    for cutie, marime in a.texte:
        x0, y0, x1, y1 = cutie
        if x0 < st or y0 < sus or x1 > w - dr or y1 > h - jos:
            out.append(f"text în afara zonei sigure: {cutie}")
            continue
        r = contrast_text(img.crop(cutie))
        if r is None:
            out.append(f"text invizibil (o singură culoare) în {cutie}")
            continue
        if r < (CONTRAST_MIN_MARE if marime >= 48 else CONTRAST_MIN):
            out.append(f"contrast slab ({r:.1f}:1) în {cutie}")
    return out


def verdict(imagine: bytes, a: AsteptariVizuale) -> validare.Verdict:
    p = probleme(imagine, a)
    if not p:
        return validare.trece("G5", VERSIUNE, validare.Treapta.V0)
    return validare.esec(
        "G5", VERSIUNE, validare.Treapta.V0,
        dovezi=[validare.Dovada(fragment="", regula="G5", detalii=f"{a.nume}: {x}") for x in p],
        instructiune="Refă grafica: " + "; ".join(p[:3]),
    )  # fmt: skip
