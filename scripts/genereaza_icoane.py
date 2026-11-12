#!/usr/bin/env python3
"""Generează pictogramele PWA (PNG) doar cu biblioteca standard: zlib + struct, fără dependențe.

    python scripts/genereaza_icoane.py [director-ieșire]

Implicit scrie în app/web/static/icons/. Desenul: fundal de culoarea brandului și o literă „A” albă din trei
poligoane, cu margini netezite prin supraeșantionare 3×3. Varianta `maskable` ține litera în zona sigură.
"""

import struct
import sys
import zlib
from pathlib import Path

FUNDAL = (0x0B, 0x5D, 0x6B, 255)
ALB = (255, 255, 255, 255)
SUPRA = 3

Poligon = list[tuple[float, float]]


def litera_a(scala: float) -> list[Poligon]:
    """Coordonate în [0,1]; `scala` micșorează litera față de centru (zona sigură)."""

    def t(p: tuple[float, float]) -> tuple[float, float]:
        return 0.5 + (p[0] - 0.5) * scala, 0.5 + (p[1] - 0.5) * scala

    stanga: Poligon = [(0.20, 0.82), (0.42, 0.18), (0.54, 0.18), (0.32, 0.82)]
    dreapta: Poligon = [(0.80, 0.82), (0.58, 0.18), (0.46, 0.18), (0.68, 0.82)]
    bara: Poligon = [(0.31, 0.62), (0.69, 0.62), (0.65, 0.72), (0.35, 0.72)]
    return [[t(p) for p in poly] for poly in (stanga, dreapta, bara)]


def in_poligon(x: float, y: float, poly: Poligon) -> bool:
    inauntru = False
    j = len(poly) - 1
    for i, (xi, yi) in enumerate(poly):
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inauntru = not inauntru
        j = i
    return inauntru


def deseneaza(dim: int, *, scala: float, colturi: float) -> bytes:
    """RGBA brut. `colturi` = raza colțurilor rotunjite ca fracțiune din latură (0 = pătrat plin)."""
    poligoane = litera_a(scala)
    randuri = bytearray()
    for y in range(dim):
        randuri.append(0)  # filtru „None”
        for x in range(dim):
            acoperire = 0
            transparent = 0
            for sy in range(SUPRA):
                for sx in range(SUPRA):
                    px, py = (x + (sx + 0.5) / SUPRA) / dim, (y + (sy + 0.5) / SUPRA) / dim
                    if colturi and not _in_rotunjit(px, py, colturi):
                        transparent += 1
                    elif any(in_poligon(px, py, p) for p in poligoane):
                        acoperire += 1
            n = SUPRA * SUPRA
            vazute = n - transparent
            if vazute == 0:
                randuri += bytes((0, 0, 0, 0))
                continue
            mix = acoperire / vazute
            rgb = tuple(round(FUNDAL[i] * (1 - mix) + ALB[i] * mix) for i in range(3))
            randuri += bytes((*rgb, round(255 * vazute / n)))
    return bytes(randuri)


def _in_rotunjit(x: float, y: float, r: float) -> bool:
    cx = min(max(x, r), 1 - r)
    cy = min(max(y, r), 1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def png(dim: int, brut: bytes) -> bytes:
    def bloc(tip: bytes, date: bytes) -> bytes:
        return struct.pack(">I", len(date)) + tip + date + struct.pack(">I", zlib.crc32(tip + date))

    antet = struct.pack(">IIBBBBB", dim, dim, 8, 6, 0, 0, 0)  # 8 biți, RGBA
    return (
        b"\x89PNG\r\n\x1a\n"
        + bloc(b"IHDR", antet)
        + bloc(b"IDAT", zlib.compress(brut, 9))
        + bloc(b"IEND", b"")
    )


ICOANE = {
    # nume: (dimensiune, scala literei, colțuri rotunjite)
    "icon-192.png": (192, 1.0, 0.18),
    "icon-512.png": (512, 1.0, 0.18),
    "icon-maskable-512.png": (512, 0.72, 0.0),  # fundal pe toată suprafața; litera în zona sigură
    "apple-touch-icon.png": (180, 1.0, 0.0),  # iOS rotunjește singur colțurile
}


def main() -> None:
    iesire = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parents[1] / "app/web/static/icons"
    )
    iesire.mkdir(parents=True, exist_ok=True)
    for nume, (dim, scala, colturi) in ICOANE.items():
        (iesire / nume).write_bytes(png(dim, deseneaza(dim, scala=scala, colturi=colturi)))
        print(f"scris {iesire / nume}")


if __name__ == "__main__":
    main()
