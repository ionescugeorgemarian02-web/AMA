"""Capătul agentului din puntea orchestratorului (vezi tests/punte_orchestrator.py).

python scripts/punte.py asteapta <dir> [--timeout 900]   # tipărește următoarea cerere fără răspuns sau GATA
python scripts/punte.py raspunde <dir> <nr> <fișier.json> # validează JSON-ul și îl predă testului
"""

import argparse
import json
import sys
import time
from pathlib import Path


def fara_raspuns(d: Path) -> list[Path]:
    return sorted(p for p in (d / "cereri").glob("*.json") if not (d / "raspunsuri" / p.name).exists())


def asteapta(d: Path, timeout: float) -> int:
    limita = time.monotonic() + timeout
    while time.monotonic() < limita:
        libere = fara_raspuns(d)
        if libere:
            print(libere[0].read_text())
            return 0
        if (d / "GATA").exists():
            print("GATA")
            return 0
        time.sleep(1)
    print("NIMIC (timeout)")
    return 3


def raspunde(d: Path, nr: str, fisier: Path) -> int:
    text = fisier.read_text()
    json.loads(text)  # ridică dacă nu e JSON valid
    tmp = d / "raspunsuri" / f".{nr}.tmp"
    tmp.write_text(text)
    tmp.rename(d / "raspunsuri" / f"{nr}.json")
    print(f"predat {nr}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("asteapta")
    a.add_argument("dir", type=Path)
    a.add_argument("--timeout", type=float, default=900)
    r = sub.add_parser("raspunde")
    r.add_argument("dir", type=Path)
    r.add_argument("nr")
    r.add_argument("fisier", type=Path)
    x = ap.parse_args()
    return asteapta(x.dir, x.timeout) if x.cmd == "asteapta" else raspunde(x.dir, x.nr, x.fisier)


if __name__ == "__main__":
    sys.exit(main())
