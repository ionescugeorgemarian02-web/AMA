"""Plan SEO dintr-un CSV, fără cont extern sau model."""

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

from app.seo import cuvinte


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fisier", type=Path)
    parser.add_argument("--produs", default="", help="Produsul comun, dacă lipsește coloana.")
    parser.add_argument("--pagina", default="", help="Pagina pe care ai filtrat exportul.")
    args = parser.parse_args()
    try:
        with args.fisier.open(encoding="utf-8-sig", newline="") as f:
            grupuri = cuvinte.din_csv(f, produs=args.produs, pagina=args.pagina)
    except (OSError, ValueError, csv.Error) as exc:
        parser.error(str(exc))
    print(
        json.dumps([{**asdict(g), "principal": g.principal} for g in grupuri], ensure_ascii=False, indent=2)
    )


if __name__ == "__main__":
    main()
