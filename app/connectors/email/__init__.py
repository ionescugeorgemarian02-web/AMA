"""Conectorul de email tranzacțional (F7.2): adaptor. Se cheamă DOAR din executorul de efecte de sistem.

`CutiePostalaSimulata` (# SIMULAT): mesajele rămân în proces, cu cheia de idempotență (același efect nu se
trimite de două ori). Furnizorul real (SMTP / API cu domeniu verificat, SPF, DKIM) e o resursă externă: se
adaugă aici la migrare, ales prin `AMA_EMAIL_FURNIZOR`."""

from dataclasses import dataclass, field

from app.connectors.contract import EfectSistem, RezultatPlatforma
from app.operare.motor import EroareDefinitiva

TIP = "email"


@dataclass
class Mesaj:
    catre: str
    subiect: str
    text: str
    idem: str


@dataclass
class CutiePostalaSimulata:
    """# SIMULAT: furnizorul de email al mediului de probă."""

    mesaje: list[Mesaj] = field(default_factory=list)
    esueaza: int = 0  # câte trimiteri următoare eșuează temporar (teste)

    def trimite(self, efect: EfectSistem) -> RezultatPlatforma:
        for i, m in enumerate(self.mesaje):
            if m.idem == efect.idem:
                return RezultatPlatforma(id_extern=f"sim-{i}")
        p = efect.payload
        if not {"catre", "subiect", "text"} <= set(p):
            raise EroareDefinitiva("mesaj incomplet")
        if self.esueaza > 0:
            self.esueaza -= 1
            raise ConnectionError("furnizorul de email nu răspunde (simulat)")
        self.mesaje.append(Mesaj(str(p["catre"]), str(p["subiect"]), str(p["text"]), efect.idem))
        return RezultatPlatforma(id_extern=f"sim-{len(self.mesaje) - 1}")

    def catre(self, adresa: str) -> list[Mesaj]:
        return [m for m in self.mesaje if m.catre == adresa]


CUTIE = CutiePostalaSimulata()
