"""Comanda lansării (F15.6): `python -m app.lansare.cli avarie <raport.json> --mediu staging` înregistrează
rezultatul testelor de avarie (scris de `scripts/avarie.sh`) pentru punctul T1 al listei de go-live."""

import argparse
import json
import sys
from pathlib import Path

from app.db import sesiune_agentie
from app.lansare import golive


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Înregistrează rezultatul testelor de avarie (F15.6).")
    sub = p.add_subparsers(dest="comanda", required=True)
    a = sub.add_parser("avarie")
    a.add_argument("raport", type=Path)
    a.add_argument("--mediu", choices=("local", "staging", "productie"), required=True)
    args = p.parse_args(argv)
    raport = json.loads(args.raport.read_text(encoding="utf-8"))
    with sesiune_agentie() as db:
        r = golive.inregistreaza_avarie(db, raport, mediu=args.mediu)
        print(f"înregistrat: {args.mediu} {r.trecute}/{r.total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
