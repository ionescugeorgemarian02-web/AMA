"""Un model gata de folosit, așa cum îl văd rutarea și limitatorul: o copie înghețată a rândurilor din
registru.

Nu poartă cheia: aceasta se citește la trimitere (`registru.citeste_cheie`)."""

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.gateway.cote import LimiteCota
from app.gateway.modele import Furnizor, ModelLlm
from app.gateway.tipuri import Destinatie

RANG_NIVEL = {"local": 1, "T1": 1, "T2": 2, "T3": 3, "T4": 4}  # „local” e de nivelul lui T1 (docs/05)


@dataclass(frozen=True)
class Candidat:
    model_id: uuid.UUID
    furnizor_id: uuid.UUID
    furnizor: str  # cod
    tip_api: str
    url_baza: str
    parametri: dict[str, Any]
    cheie_env: str
    identificator: str
    nivel: str
    capabilitati: frozenset[str]
    limite_model: LimiteCota
    limite_furnizor: LimiteCota
    reset_zi_ora: int
    stare_furnizor: str
    model_activ: bool
    platit: bool
    uz_comercial: bool | None
    antrenare_pe_date: bool | None
    scor: dict[str, float] = field(default_factory=dict)
    pret_umbra_intrare: float = 0.0
    pret_umbra_iesire: float = 0.0
    context_tokeni: int = 0
    erori_consecutive: int = 0
    intrerupt_pana_la: dt.datetime | None = None  # întrerupătorul furnizorului (F3.4)
    tokeni_pe_secunda: float | None = None  # viteza măsurată (modele locale, F3.5)
    dimensiune_vector: int | None = None  # modelele de vectori (F3.5)

    @property
    def fara_cheie(self) -> bool:
        """Serverul local (llama.cpp / Ollama) rulează în rețeaua internă și nu cere cheie."""
        return self.tip_api == "local"

    @property
    def cod(self) -> str:
        """Identificatorul modelului în lanțuri și în jurnal: `furnizor/identificator`."""
        return f"{self.furnizor}/{self.identificator}"

    @property
    def rang(self) -> int:
        return RANG_NIVEL[self.nivel]

    @property
    def destinatie(self) -> Destinatie:
        return Destinatie(
            furnizor=self.furnizor,
            tip_api=self.tip_api,
            url_baza=self.url_baza,
            model=self.identificator,
            parametri=self.parametri,
            capabilitati=self.capabilitati,
        )


def din_randuri(f: Furnizor, m: ModelLlm) -> Candidat:
    return Candidat(
        model_id=m.id,
        furnizor_id=f.id,
        furnizor=f.cod,
        tip_api=f.tip_api,
        url_baza=f.url_baza,
        parametri=dict(f.parametri or {}),
        cheie_env=f.cheie_env,
        identificator=m.identificator,
        nivel=m.nivel,
        capabilitati=frozenset(m.capabilitati or ()),
        limite_model=LimiteCota.din(m),
        limite_furnizor=LimiteCota.din(f),
        reset_zi_ora=f.reset_zi_ora,
        stare_furnizor=f.stare,
        model_activ=m.activ,
        platit=f.platit,
        uz_comercial=f.uz_comercial,
        antrenare_pe_date=f.antrenare_pe_date,
        scor={k: float(v) for k, v in (m.scor or {}).items() if isinstance(v, int | float)},
        pret_umbra_intrare=float(m.pret_umbra_intrare),
        pret_umbra_iesire=float(m.pret_umbra_iesire),
        context_tokeni=m.context_tokeni,
        erori_consecutive=f.erori_consecutive,
        intrerupt_pana_la=f.intrerupt_pana_la,
        tokeni_pe_secunda=None if m.tokeni_pe_secunda is None else float(m.tokeni_pe_secunda),
        dimensiune_vector=m.dimensiune_vector,
    )
