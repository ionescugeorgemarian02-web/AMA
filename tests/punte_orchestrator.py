"""Puntea orchestratorului (testul live): un „model” al cărui răspuns îl scrie un agent din afara procesului.

Fiecare cerere ajunsă la gateway (prin furnizorul de probă) se scrie în `<dir>/cereri/NNN.json` (sarcina, promptul complet,
schema cerută); handlerul așteaptă `<dir>/raspunsuri/NNN.json`. Agentul care ține locul modelului citește cererile cu
`python scripts/punte.py asteapta <dir>` și răspunde cu `python scripts/punte.py raspunde <dir> NNN <fișier>`.
Restul lanțului (gateway, validare, voce, montaj, control) rulează real."""

import json
import time
from collections.abc import Callable
from pathlib import Path

from tests.furnizor_fals import CerereInregistrata
from tests.onboarding_utile import prompt_complet


class Punte:
    def __init__(self, director: Path, *, timeout_sec: float = 1800.0) -> None:
        self.director = director
        self.timeout_sec = timeout_sec
        (director / "cereri").mkdir(parents=True, exist_ok=True)
        (director / "raspunsuri").mkdir(parents=True, exist_ok=True)
        self.n = len(list((director / "cereri").glob("*.json")))

    def handler(self, sarcina: str) -> Callable[[CerereInregistrata], str]:
        return lambda c: self.intreaba(sarcina, c)

    def intreaba(self, sarcina: str, c: CerereInregistrata) -> str:
        self.n += 1
        nr = f"{self.n:03d}"
        corp = {
            "id": nr,
            "sarcina": sarcina,
            "prompt": prompt_complet(c),
            "format": c.corp.get("response_format"),
        }
        tmp = self.director / "cereri" / f".{nr}.tmp"
        tmp.write_text(json.dumps(corp, ensure_ascii=False, indent=1))
        tmp.rename(self.director / "cereri" / f"{nr}.json")
        raspuns = self.director / "raspunsuri" / f"{nr}.json"
        limita = time.monotonic() + self.timeout_sec
        while not raspuns.exists():
            if time.monotonic() > limita:
                raise TimeoutError(f"puntea: niciun răspuns la cererea {nr} ({sarcina})")
            time.sleep(0.5)
        return raspuns.read_text()

    def inchide(self) -> None:
        (self.director / "GATA").write_text("gata")
