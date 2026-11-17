"""# SIMULAT: cititorul de metrici al platformei false (F10.1). Cifrele se pun în test (`pune`), pe
identificatorul postării; defectele se injectează pe rând, ca la conectorul fals de publicare."""

import datetime as dt
import uuid
from dataclasses import dataclass, field

from app.connectors.contract import Metrici
from app.connectors.publicare.baza import DepozitTokenuri, token_sau_autentificare
from app.operare.motor import EroareAutentificare, EroareDefinitiva, EroareTemporara


@dataclass
class MetriciFalse:
    """Ce „știe” platforma falsă despre rezultatele postărilor."""

    valori: dict[str, Metrici] = field(default_factory=dict)
    defecte: list[str] = field(default_factory=list)
    citiri: list[str] = field(default_factory=list)

    def pune(self, id_extern: str, **cifre: int) -> None:
        self.valori[id_extern] = Metrici(**cifre)

    def injecteaza(self, *defecte: str) -> None:
        self.defecte.extend(defecte)


class CititorFals:
    def __init__(self, date: MetriciFalse, depozit: DepozitTokenuri, canal: str = "fals_api") -> None:
        self.date, self.depozit, self.canal = date, depozit, canal

    def metrici(self, tenant_id: uuid.UUID, id_extern: str) -> Metrici:
        token_sau_autentificare(self.depozit, tenant_id, self.canal)
        defect = self.date.defecte.pop(0) if self.date.defecte else "ok"
        if defect == "temporar":
            raise EroareTemporara("503: platforma indisponibilă")
        if defect == "autentificare":
            raise EroareAutentificare("401: token respins de platformă")
        self.date.citiri.append(id_extern)
        if defect == "definitiv" or id_extern not in self.date.valori:
            raise EroareDefinitiva("404: postarea nu există")
        return self.date.valori[id_extern]


@dataclass
class RetentieFalsa:
    """# SIMULAT: curbele de retenție pe care le „știe” platforma falsă, pe identificatorul clipului."""

    curbe: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    defecte: list[str] = field(default_factory=list)
    citiri: list[str] = field(default_factory=list)


class CititorRetentieFals:
    def __init__(self, date: RetentieFalsa, depozit: DepozitTokenuri, canal: str = "youtube") -> None:
        self.date, self.depozit, self.canal = date, depozit, canal

    def retentie(
        self, tenant_id: uuid.UUID, id_extern: str, de_la: dt.date, pana_la: dt.date
    ) -> list[tuple[float, float]]:
        token_sau_autentificare(self.depozit, tenant_id, self.canal)
        defect = self.date.defecte.pop(0) if self.date.defecte else "ok"
        if defect == "temporar":
            raise EroareTemporara("503: platforma indisponibilă")
        if defect == "definitiv":
            raise EroareDefinitiva("403: fără permisiunea de analiză")
        self.date.citiri.append(id_extern)
        return list(self.date.curbe.get(id_extern, []))
