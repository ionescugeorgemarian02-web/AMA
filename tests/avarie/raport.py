"""Raportul pe scenarii al testelor de avarie (F15.1): citește JUnit-ul lui pytest și spune, pentru fiecare
scenariu din docs/25 §25.3, dacă toate testele lui au trecut. Folosire:
`python -m tests.avarie.raport junit.xml [raport.json]` -> cod 0 doar dacă toate scenariile au trecut."""

import datetime as dt
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from tests.avarie.catalog import SCENARII


def _rezultate(junit: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for tc in ET.parse(junit).getroot().iter("testcase"):  # noqa: S314 (JUnit scris de pytest-ul local)
        fisier = tc.get("file") or tc.get("classname", "").replace(".", "/") + ".py"
        nume = tc.get("name", "").split("[")[0]
        if tc.find("failure") is not None or tc.find("error") is not None:
            stare = "picat"
        elif tc.find("skipped") is not None:
            stare = "sarit"
        else:
            stare = "trecut"
        cheie = f"{fisier}::{nume}"
        out[cheie] = "picat" if "picat" in (out.get(cheie), stare) else stare
    return out


def raport(junit: Path) -> dict[str, object]:
    rez = _rezultate(junit)
    scenarii = []
    for s in SCENARII:
        stari = {t: rez.get(t, "nerulat") for t in s.teste}
        trecut = all(v == "trecut" for v in stari.values())
        scenarii.append({"cod": s.cod, "titlu": s.titlu, "trecut": trecut, "teste": stari})
    return {
        "schema": "ama.avarie/1",
        "la": dt.datetime.now(dt.UTC).isoformat(),
        "trecute": sum(1 for s in scenarii if s["trecut"]),
        "total": len(scenarii),
        "scenarii": scenarii,
    }


def main(argv: list[str]) -> int:
    r = raport(Path(argv[0]))
    text = json.dumps(r, ensure_ascii=False, indent=1)
    if len(argv) > 1:
        Path(argv[1]).write_text(text)
    for s in r["scenarii"]:  # type: ignore[attr-defined]
        print(("TRECE " if s["trecut"] else "PICĂ  ") + f"{s['cod']} {s['titlu']}")
    print(f"{r['trecute']}/{r['total']} scenarii trecute")
    return 0 if r["trecute"] == r["total"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
