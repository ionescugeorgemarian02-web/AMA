"""Conectorul inboxului social (F12.7–F12.8): citirea mesajelor și a comentariilor de pe canalele agenției și
trimiterea răspunsurilor. Se cheamă DOAR din `app/operare/efecte` (garda `check_efecte`).

`InboxSimulat` (# SIMULAT): mesajele primite se pun din teste sau din modul demo; răspunsurile rămân în
proces, idempotente pe cheia efectului. Conectorii reali (Graph API pentru Instagram și Facebook: conversații
și comentarii, cu permisiunile aprobate de Meta) se adaugă aici la migrare (ADR-07: doar API-uri oficiale)."""

import datetime as dt
from dataclasses import dataclass, field

from app.connectors.contract import EfectSistem, RezultatPlatforma
from app.operare.motor import EroareDefinitiva

CANALE = ("instagram", "facebook")
TIPURI = ("mesaj", "comentariu")


@dataclass(frozen=True)
class MesajPrimit:
    canal: str
    id_extern: str
    tip: str  # mesaj privat sau comentariu public
    fir: str  # conversația (mesaj) sau postarea (comentariu)
    autor: str  # identificatorul public al persoanei pe rețea
    text: str
    primit_la: dt.datetime


@dataclass
class InboxSimulat:
    """# SIMULAT: inboxul canalelor agenției în mediul de probă."""

    primite: list[MesajPrimit] = field(default_factory=list)
    trimise: list[dict[str, str]] = field(default_factory=list)
    ascunse: list[str] = field(default_factory=list)

    def citeste(self, canal: str, de_la: dt.datetime | None) -> list[MesajPrimit]:
        return [m for m in self.primite if m.canal == canal and (de_la is None or m.primit_la > de_la)]

    def trimite(self, efect: EfectSistem) -> RezultatPlatforma:
        p = efect.payload
        for i, t in enumerate(self.trimise):
            if t["idem"] == efect.idem:
                return RezultatPlatforma(id_extern=f"sim-inbox-{i}")
        if p.get("actiune") == "ascunde":
            self.ascunse.append(str(p["id_extern"]))
            self.trimise.append({"idem": efect.idem, "actiune": "ascunde", "id_extern": str(p["id_extern"])})
            return RezultatPlatforma(id_extern=f"sim-inbox-{len(self.trimise) - 1}")
        if not {"canal", "fir", "catre", "text"} <= set(p):
            raise EroareDefinitiva("răspuns incomplet")
        expira = p.get("fereastra_pana_la")
        if expira and dt.datetime.fromisoformat(str(expira)) < dt.datetime.now(dt.UTC):
            raise EroareDefinitiva("fereastra de mesagerie s-a închis")  # ca platforma reală: refuz definitiv
        trimis = {k: str(p[k]) for k in ("canal", "fir", "catre", "text")}
        self.trimise.append(
            {"idem": efect.idem, "actiune": "raspunde", **trimis, "eticheta": str(p.get("eticheta", ""))}
        )
        return RezultatPlatforma(id_extern=f"sim-inbox-{len(self.trimise) - 1}")


INBOX = InboxSimulat()


def cititor_pentru(canal: str) -> InboxSimulat | None:
    return INBOX if canal in CANALE else None
