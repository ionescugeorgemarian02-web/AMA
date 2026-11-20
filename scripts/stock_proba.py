"""Proba furnizorilor de stock reali (F-idee, „Imagini reale”): caută, descarcă și raportează licențele.

Rulează doar manual sau într-un job CI cu rețea, niciodată în testele obișnuite.

    uv run python scripts/stock_proba.py commons "bicycle chain rotating" --tip video -n 2 --dir out/

Scrie fișierele și `LICENTE.json` (furnizor, identificator, autor, licență, url, sha256) în director.
Codul de ieșire: 0 dacă s-a descărcat cel puțin un fișier, 1 altfel.
"""

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # rulat ca script din rădăcina proiectului

if TYPE_CHECKING:
    from app.media.furnizori import FurnizorStock


def furnizor(nume: str) -> "FurnizorStock":
    if nume == "commons":
        from app.media.stock_commons import StockCommons

        return StockCommons()
    if nume == "pexels":
        from app.media.stock_pexels import StockPexels

        return StockPexels()
    if nume == "pixabay":
        from app.media.stock_pixabay import StockPixabay

        return StockPixabay()
    raise SystemExit(f"furnizor necunoscut: {nume}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("furnizor", choices=("commons", "pexels", "pixabay"))
    p.add_argument("interogare")
    p.add_argument("--tip", choices=("foto", "video"), default="foto")
    p.add_argument("-n", type=int, default=2)
    p.add_argument("--dir", type=Path, default=Path("out"))
    a = p.parse_args(argv)
    f = furnizor(a.furnizor)
    a.dir.mkdir(parents=True, exist_ok=True)
    try:
        rezultate = f.cauta(a.interogare, tip=a.tip, n=a.n)
    except OSError as e:
        print(f"căutarea a eșuat: {e}", file=sys.stderr)
        return 1
    for titlu, motiv in getattr(f, "refuzate", []):
        print(f"refuzat {titlu}: {motiv}", file=sys.stderr)
    licente = []
    for i, r in enumerate(rezultate):
        try:
            corp = f.descarca(r)
        except Exception as e:
            print(f"eșuat {r.identificator}: {e}", file=sys.stderr)
            continue
        baza = re.sub(r"[^A-Za-z0-9._-]+", "_", r.identificator)[:60]
        nume = f"{i:02d}-{baza}.{'mp4' if r.tip == 'video' else 'jpg'}"
        (a.dir / nume).write_bytes(corp)
        licente.append({"fisier": nume, "sha256": hashlib.sha256(corp).hexdigest(), **asdict(r)})
        print(f"{nume}: {r.licenta or '?'} — {r.autor} — {r.url}")
    (a.dir / "LICENTE.json").write_text(json.dumps(licente, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(licente)}/{len(rezultate)} descărcate în {a.dir}")
    return 0 if licente else 1


if __name__ == "__main__":
    raise SystemExit(main())
