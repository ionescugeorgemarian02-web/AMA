"""Lista de decizii de montaj (F8.5, docs/14 §14.6): contractul dintre model și program.

Modelul nu scrie comenzi FFmpeg: alege, pe bătăi, ce cadru și ce mișcare; programul pune momentele (din vocea
reală) și randează. Fiind date, lista se validează (G1 media), se compară și se re-randează identic.
"""

import uuid
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FORMATE = ("A", "B", "E")
CADRU = 1 / 30
TOLERANTA_VOCE = 0.05  # [I] secunde între durata listei și vocea + coada
COADA_MAX = 1.5  # [I] secunde după ultimul cuvânt (apelul la acțiune rămâne pe ecran)
SCENA_MIN = 0.5  # [I]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Scena(Model):
    activ_id: uuid.UUID
    inceput: float = Field(ge=0)
    sfarsit: float = Field(gt=0)
    sursa_de_la: float = Field(default=0.0, ge=0)  # pentru video: de unde se taie din sursă
    incadrare: Literal["umple", "centrat"] = "umple"
    miscare: Literal["static", "zoom_in", "zoom_out", "panoramare_stanga", "panoramare_dreapta"] = "static"
    bataie: int = Field(ge=0)


class Text(Model):
    cuvant: str = Field(min_length=1, max_length=40)
    inceput: float = Field(ge=0)
    sfarsit: float = Field(gt=0)
    fraza: int = Field(ge=0)


class Pista(Model):
    activ_id: uuid.UUID
    durata: float = Field(gt=0)


class Muzica(Model):
    activ_id: uuid.UUID
    nivel_db: float = Field(default=-16.0, le=0, ge=-40)  # nivelul muzicii față de voce, înainte de atenuare
    atenuare_sub_voce: bool = True


class StilSubtitrari(Model):
    culoare: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$")
    evidentiere: str = Field(default="#FFD400", pattern=r"^#[0-9A-Fa-f]{6}$")
    contur: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    pozitie: Literal["jos", "mijloc"] = "jos"
    marime: int = Field(default=68, ge=36, le=110)


class Coperta(Model):
    text: str = Field(min_length=1, max_length=60)
    moment: float = Field(default=0.0, ge=0)


class ListaMontaj(Model):
    versiune: int = 1
    format: Literal["A", "B", "E"]
    canal: str = "tiktok"
    latime: int = 1080
    inaltime: int = 1920
    cadre_pe_secunda: int = 30
    durata: float = Field(gt=0)
    voce: Pista
    muzica: Muzica | None = None
    scene: list[Scena] = Field(min_length=1)
    texte: list[Text] = Field(default_factory=list)
    stil: StilSubtitrari = Field(default_factory=StilSubtitrari)
    coperta: Coperta | None = None


@dataclass(frozen=True)
class InfoActiv:
    categorie: str
    licentiat: bool
    durata: float | None = None  # pentru video / audio


def probleme(lista: ListaMontaj, active: dict[uuid.UUID, InfoActiv]) -> list[str]:
    """Validarea listei (14.5 pasul 6, G1 media): durate, acoperire, fișiere existente, licențe, texte."""
    out: list[str] = []
    eps = CADRU + 1e-6
    coada = lista.durata - lista.voce.durata
    if coada < -TOLERANTA_VOCE or coada > COADA_MAX + TOLERANTA_VOCE:
        out.append(
            f"durata listei ({lista.durata:.2f} s) nu se potrivește cu vocea ({lista.voce.durata:.2f} s)"
        )
    t = 0.0
    for i, s in enumerate(lista.scene):
        if abs(s.inceput - t) > eps:
            out.append(f"scena {i}: începe la {s.inceput:.2f} s, nu la {t:.2f} s (gol sau suprapunere)")
        if s.sfarsit - s.inceput < SCENA_MIN - 1e-6:
            out.append(f"scena {i}: mai scurtă de {SCENA_MIN} s")
        t = s.sfarsit
        info = active.get(s.activ_id)
        if info is None:
            out.append(f"scena {i}: activul {s.activ_id} nu există")
            continue
        if not info.licentiat:
            out.append(f"scena {i}: activul {s.activ_id} nu are licență înregistrată")
        asteptat = {"A": ("video",), "B": ("foto",), "E": ("video", "foto")}[lista.format]
        if info.categorie not in asteptat:
            out.append(f"scena {i}: formatul {lista.format} nu folosește {info.categorie}")
        lunga = info.durata is not None and s.sursa_de_la + (s.sfarsit - s.inceput) > info.durata + eps
        if info.categorie == "video" and lunga:
            out.append(f"scena {i}: sursa video e mai scurtă decât scena")
    if abs(t - lista.durata) > eps:
        out.append(f"scenele se termină la {t:.2f} s, lista durează {lista.durata:.2f} s")
    voce = active.get(lista.voce.activ_id)
    if voce is None or voce.categorie != "audio":
        out.append("pista de voce lipsește")
    elif not voce.licentiat:
        out.append("vocea nu are licență înregistrată")
    elif voce.durata is not None and abs(voce.durata - lista.voce.durata) > TOLERANTA_VOCE:
        out.append("durata pistei de voce diferă de fișier")
    if lista.muzica is not None:
        m = active.get(lista.muzica.activ_id)
        if m is None or m.categorie != "audio" or not m.licentiat:
            out.append("muzica lipsește sau nu are licență")
    anterior = 0.0
    for k, x in enumerate(lista.texte):
        if x.sfarsit <= x.inceput or x.sfarsit > lista.durata + eps:
            out.append(f"textul {k} ({x.cuvant!r}) are momente greșite")
        if x.inceput + eps < anterior:
            out.append(f"textul {k} ({x.cuvant!r}) nu e în ordine")
        anterior = x.inceput
    if lista.coperta is not None and lista.coperta.moment > lista.durata:
        out.append("coperta e după sfârșitul videoului")
    return out
