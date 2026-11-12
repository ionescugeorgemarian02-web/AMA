"""# SIMULAT: conectorul fals al platformei (F2.5). Nu există niciun conector real în F2 și nicio rețea în teste.

„Platforma” e un director de fișiere (merge între procese: workerul real și testul): `postari.log` primește câte o linie
pentru FIECARE postare creată la „platformă” (și o dublă ar apărea ca a doua linie), iar `apeluri.log` câte o linie
pentru fiecare apel (`trimite` / `verifica`). Comportamentul se scriptează cu `scenariu.json`:

    {"trimite": ["temporar", "ok"], "verifica": []}

Fiecare apel consumă următorul cuvânt din lista lui (lista goală = `ok`). Cuvinte pentru `trimite`:
- `ok`: postează și răspunde;
- `temporar`: eroare temporară, fără să posteze; `definitiv`: refuz; `autentificare`: token expirat;
- `expira`: timeout, fără să posteze;
- `reuseste_dar_eroare`: postează, apoi răspunde cu eroare temporară (răspunsul s-a pierdut);
- `reuseste_dar_moare`: postează, apoi procesul se oprește brusc (`os._exit`);
- `blocheaza_inainte` / `blocheaza_dupa`: notează un marcaj (`inainte.marcaj` / `dupa.marcaj`) și așteaptă cât timp
  există fișierul `blocheaza` (testul omoară workerul în acest interval); `dupa` postează ÎNAINTE de marcaj.
Pentru `verifica`: `ok` (răspunde cu ce există), `temporar`, `autentificare`.
"""

import json
import os
import time
from pathlib import Path

from app.connectors.contract import EfectDeTrimis, RezultatPlatforma
from app.operare import motor


class ConectorFals:
    def __init__(self, director: Path) -> None:
        self.dir = director / "platforma"
        self.dir.mkdir(parents=True, exist_ok=True)

    # --- scenariu ---------------------------------------------------------------------------------------------

    def scenariu(self, **liste: list[str]) -> None:
        """Pune scenariul (suprascrie și repornește numărătoarea)."""
        (self.dir / "scenariu.json").write_text(json.dumps(liste))
        for f in self.dir.glob("consumat.*"):
            f.unlink()

    def _urmatorul(self, ce: str) -> str:
        cale = self.dir / "scenariu.json"
        lista = json.loads(cale.read_text()).get(ce, []) if cale.exists() else []
        contor = self.dir / f"consumat.{ce}"
        i = len(contor.read_text().splitlines()) if contor.exists() else 0
        with contor.open("a") as f:
            f.write("x\n")
        return str(lista[i]) if i < len(lista) else "ok"

    # --- ce s-a întâmplat „la platformă” ----------------------------------------------------------------------

    def postari(self, idem: str | None = None) -> list[dict[str, str]]:
        cale = self.dir / "postari.log"
        toate = [json.loads(linie) for linie in cale.read_text().splitlines()] if cale.exists() else []
        return [p for p in toate if idem is None or p["idem"] == idem]

    def apeluri(self, ce: str | None = None) -> list[str]:
        cale = self.dir / "apeluri.log"
        linii = cale.read_text().splitlines() if cale.exists() else []
        return [x for x in linii if ce is None or x.split()[0] == ce]

    def _scrie(self, nume: str, linie: str) -> None:
        with (self.dir / nume).open("a", encoding="utf-8") as f:
            f.write(linie + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _posteaza(self, efect: EfectDeTrimis) -> RezultatPlatforma:
        n = len(self.postari()) + 1
        rez = RezultatPlatforma(id_extern=f"fals-{n}", link=f"https://platforma.exemplu.test/post/{n}")
        self._scrie("postari.log", json.dumps({"idem": efect.idem, "id": rez.id_extern, "link": rez.link}))
        return rez

    def _asteapta_deblocarea(self) -> None:
        while (self.dir / "blocheaza").exists():
            time.sleep(0.02)

    # --- contractul conectorului ---------------------------------------------------------------------------------

    def trimite(self, efect: EfectDeTrimis) -> RezultatPlatforma:
        comportament = self._urmatorul("trimite")
        self._scrie("apeluri.log", f"trimite {efect.idem} {comportament}")
        if comportament == "temporar":
            raise motor.EroareTemporara("platforma: eroare de server")
        if comportament == "definitiv":
            raise motor.EroareDefinitiva("platforma a refuzat conținutul")
        if comportament == "autentificare":
            raise motor.EroareAutentificare("token expirat")
        if comportament == "expira":
            raise motor.EroareTemporara("timeout")
        if comportament == "blocheaza_inainte":
            (self.dir / "inainte.marcaj").touch()
            self._asteapta_deblocarea()
        rez = self._posteaza(efect)
        if comportament == "reuseste_dar_eroare":
            raise motor.EroareTemporara("răspunsul s-a pierdut")
        if comportament == "reuseste_dar_moare":
            os._exit(9)
        if comportament == "blocheaza_dupa":
            (self.dir / "dupa.marcaj").touch()
            self._asteapta_deblocarea()
        return rez

    def verifica(self, efect: EfectDeTrimis) -> RezultatPlatforma | None:
        comportament = self._urmatorul("verifica")
        self._scrie("apeluri.log", f"verifica {efect.idem} {comportament}")
        if comportament == "temporar":
            raise motor.EroareTemporara("platforma nu răspunde")
        if comportament == "autentificare":
            raise motor.EroareAutentificare("token expirat")
        gasite = self.postari(efect.idem)
        return RezultatPlatforma(gasite[0]["id"], gasite[0]["link"]) if gasite else None
