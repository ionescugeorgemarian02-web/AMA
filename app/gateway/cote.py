"""Nucleul pur al limitatoarelor de cotă (8.4): ferestrele, plafoanele cu rezerva pentru P0, estimarea
tokenilor.
Fără bază și fără rețea; contoarele persistente sunt în `limitator`.

Ferestre: „minut” (minutul calendaristic UTC) și „zi” (de la ora de resetare a furnizorului, în UTC). Un
contor
numără cererile și tokenii REZERVAȚI (apoi regularizați cu cei reali) în fereastra în care s-a făcut
rezervarea.
"""

import datetime as dt
import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.operare.motor import Prioritate

REZERVA_ZILNICA = 0.10  # 8.4: din fiecare limită zilnică, 10% rămâne pentru P0
MARJA_RESET_SEC = 1.0  # reluarea se face la puțin timp după resetare, nu exact pe ea
CARACTERE_PE_TOKEN = 3.0  # estimare prudentă pentru română (diacriticele sparg cuvintele în mai mulți tokeni)
PAUZA_IMPLICITA_429_SEC = 60.0  # un 429 fără nicio indicație de timp: așteptăm o fereastră de minut


class Fereastra(StrEnum):
    MINUT = "minut"
    ZI = "zi"


@dataclass(frozen=True)
class LimiteCota:
    """Limitele unei resurse (un model sau un cont de furnizor). `None` = fără limită pe acea axă."""

    cereri_minut: int | None = None
    cereri_zi: int | None = None
    tokeni_minut: int | None = None
    tokeni_zi: int | None = None

    @classmethod
    def din(cls, obiect: Any) -> "LimiteCota":
        return cls(obiect.cereri_minut, obiect.cereri_zi, obiect.tokeni_minut, obiect.tokeni_zi)

    def pe(self, fereastra: Fereastra) -> tuple[int | None, int | None]:
        """(cereri, tokeni) pentru fereastră."""
        if fereastra is Fereastra.MINUT:
            return self.cereri_minut, self.tokeni_minut
        return self.cereri_zi, self.tokeni_zi

    @property
    def goala(self) -> bool:
        return self == LimiteCota()


def inceput_fereastra(acum: dt.datetime, fereastra: Fereastra, reset_zi_ora: int = 0) -> dt.datetime:
    acum = acum.astimezone(dt.UTC)
    if fereastra is Fereastra.MINUT:
        return acum.replace(second=0, microsecond=0)
    inceput = acum.replace(hour=reset_zi_ora, minute=0, second=0, microsecond=0)
    return inceput if inceput <= acum else inceput - dt.timedelta(days=1)


def sfarsit_fereastra(acum: dt.datetime, fereastra: Fereastra, reset_zi_ora: int = 0) -> dt.datetime:
    inceput = inceput_fereastra(acum, fereastra, reset_zi_ora)
    return inceput + (dt.timedelta(minutes=1) if fereastra is Fereastra.MINUT else dt.timedelta(days=1))


def reluare_dupa(sfarsit: dt.datetime) -> dt.datetime:
    """Momentul de la care merită reluat un apel amânat până la sfârșitul unei ferestre."""
    return sfarsit + dt.timedelta(seconds=MARJA_RESET_SEC)


def plafon(limita: int | None, fereastra: Fereastra, prioritate: Prioritate) -> int | None:
    """Cât are voie să consume un apel de prioritatea dată dintr-o limită. Pe fereastra zilnică, tot ce nu
    e P0
    lasă 10% din limită în rezervă (rotunjit în jos); P0 poate folosi toată limita."""
    if limita is None:
        return None
    if fereastra is Fereastra.ZI and prioritate is not Prioritate.P0:
        return math.floor(limita * (1.0 - REZERVA_ZILNICA))
    return limita


def estimeaza_tokeni(caractere_prompt: int, max_tokeni_iesire: int) -> int:
    """Tokenii de rezervat înaintea apelului: promptul (estimat din lungime) plus plafonul ieșirii. Se
    regularizează
    după apel cu cei raportați de furnizor."""
    return math.ceil(max(0, caractere_prompt) / CARACTERE_PE_TOKEN) + max(0, max_tokeni_iesire)


def permite(
    cereri_folosite: int,
    tokeni_folositi: int,
    tokeni_ceruti: int,
    plafon_cereri: int | None,
    plafon_tokeni: int | None,
) -> bool:
    """Oglinda în Python a condiției aplicate atomic în bază (testată împotriva ei)."""
    if plafon_cereri is not None and cereri_folosite + 1 > plafon_cereri:
        return False
    return not (plafon_tokeni is not None and tokeni_folositi + tokeni_ceruti > plafon_tokeni)


def pana_la_dupa_429(retry_dupa_sec: float | None, acum: dt.datetime) -> dt.datetime:
    """Până când blocăm un model după un 429: indicația furnizorului, sau o fereastră de minut."""
    sec = PAUZA_IMPLICITA_429_SEC if retry_dupa_sec is None else max(0.0, retry_dupa_sec)
    return acum + dt.timedelta(seconds=sec)


def cheie_model(model_id: object) -> str:
    return f"model:{model_id}"


def cheie_furnizor(furnizor_id: object) -> str:
    return f"furnizor:{furnizor_id}"
