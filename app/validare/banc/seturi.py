"""Seturile de aur ca DATE versionate în depozit (`evaluare/aur/`), citite doar ca octeți (garda din F5.7:
niciun cod
automat nu le scrie; le schimbă un om printr-un commit).

Formatul (JSON Lines, un exemplu pe rând, în română, inventat, fără date personale reale):

- `<G>.jsonl` (G1, G2, G3, G4, G7, G8, G9, G10): exemple de aur ale unui validator: `id`, `ctx` (profilul de
context),
  `tip`, `canal`, `text`, `campuri`, `active`, `asteptat` (`trece` / `esec`), `severitate` (`majora` /
  `critica`, doar la
  `esec`), `motiv`.
- `rele.jsonl`: materiale intenționat greșite: `id`, `ctx`, `tip`, `canal`, `text`, `campuri`, `active`,
`validator`
  (cel care trebuie să-l prindă), `defect`.
- `bune.jsonl`: materiale bune: `id`, `ctx`, `tip`, `canal`, `text`, `campuri`, `active`, `motiv`.
- `contexte.toml`: profilurile de context (fapte, oferte, ghid, surse) la care trimit exemplele.
- `INGHETAT.toml`: amprentele fișierelor de bază, puse de un om la înghețare (vezi `docs/specs/F5.7.md`).
"""

import datetime as dt
import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DIRECTOR = Path(__file__).resolve().parents[3] / "evaluare" / "aur"
VALIDATORI = ("G1", "G2", "G3", "G4", "G7", "G8", "G9", "G10")
FISIERE_BAZA = (*(f"{g}.jsonl" for g in VALIDATORI), "rele.jsonl", "bune.jsonl", "contexte.toml")
TIPURI_SET = ("aur", "rele", "bune", "promovat")


class SetInvalid(ValueError):
    """Un fișier din seturi nu respectă formatul."""


@dataclass(frozen=True)
class Exemplu:
    id: str
    set: str  # „aur:G2”, „rele”, „bune” sau „promovat:G2”
    ctx: str
    tip: str
    canal: str
    text: str
    campuri: dict[str, Any] = field(default_factory=dict)
    active: tuple[dict[str, Any], ...] = ()
    asteptat: str = ""  # doar aur / promovat: „trece” sau „esec”
    severitate: str | None = None
    motiv: str = ""  # aur, bune, promovat
    validator: str = ""  # rele: cine trebuie să-l prindă; aur / promovat: al cui e exemplul
    defect: str = ""  # rele

    @property
    def tip_set(self) -> str:
        return self.set.split(":", 1)[0]


@dataclass(frozen=True)
class ProfilContext:
    id: str
    nume: str = ""
    ghid: dict[str, Any] | None = None
    fapte: tuple[dict[str, Any], ...] = ()
    oferte: tuple[dict[str, Any], ...] = ()
    surse: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class Seturi:
    la: dt.datetime
    contexte: dict[str, ProfilContext]
    aur: dict[str, tuple[Exemplu, ...]]
    rele: tuple[Exemplu, ...]
    bune: tuple[Exemplu, ...]
    promovate: tuple[Exemplu, ...] = ()
    amprenta: str = ""

    def numar(self) -> int:
        return sum(len(v) for v in self.aur.values()) + len(self.rele) + len(self.bune) + len(self.promovate)

    def toate_aur(self, validator: str) -> tuple[Exemplu, ...]:
        """Exemplele de aur ale unui validator: cele din depozit și cele promovate de un om."""
        return self.aur.get(validator, ()) + tuple(e for e in self.promovate if e.validator == validator)


def citeste_octeti(cale: Path) -> bytes:
    return cale.read_bytes()


def amprenta_fisier(cale: Path) -> str:
    return hashlib.sha256(citeste_octeti(cale)).hexdigest()


def amprente_baza(director: Path = DIRECTOR) -> dict[str, str]:
    return {f: amprenta_fisier(director / f) for f in FISIERE_BAZA if (director / f).exists()}


def amprenta_seturi(director: Path = DIRECTOR) -> str:
    """O amprentă a tuturor fișierelor de bază (se salvează la fiecare rulare, ca scorurile să rămână legate
    de
    setul cu care s-au măsurat)."""
    h = hashlib.sha256()
    for nume, a in sorted(amprente_baza(director).items()):
        h.update(f"{nume}={a}\n".encode())
    return h.hexdigest()


def inghetat(director: Path = DIRECTOR) -> dict[str, str]:
    cale = director / "INGHETAT.toml"
    if not cale.exists():
        return {}
    return {
        str(k): str(v) for k, v in tomllib.loads(citeste_octeti(cale).decode()).get("fisiere", {}).items()
    }


def _rand(cale: Path, nr: int, linie: str) -> dict[str, Any]:
    try:
        d = json.loads(linie)
    except json.JSONDecodeError as exc:
        raise SetInvalid(f"{cale.name}:{nr}: JSON invalid ({exc.msg})") from None
    if not isinstance(d, dict):
        raise SetInvalid(f"{cale.name}:{nr}: un rând trebuie să fie un obiect")
    return d


def _exemplu(d: dict[str, Any], set_: str, sursa: str, *, contexte: set[str] | None) -> Exemplu:
    tip_set = set_.split(":", 1)[0]
    cerute = ["id", "ctx", "tip", "canal", "text"]
    cerute += {
        "aur": ["asteptat", "motiv"],
        "promovat": ["asteptat", "motiv"],
        "rele": ["validator", "defect"],
    }.get(tip_set, ["motiv"])
    lipsa = [c for c in cerute if not str(d.get(c, "")).strip()]
    if lipsa:
        raise SetInvalid(f"{sursa}: {d.get('id', '?')}: lipsesc câmpurile {lipsa}")
    asteptat = str(d.get("asteptat", ""))
    severitate = d.get("severitate")
    if tip_set in ("aur", "promovat"):
        if asteptat not in ("trece", "esec"):
            raise SetInvalid(f"{sursa}: {d['id']}: `asteptat` este „trece” sau „esec”")
        if (asteptat == "esec") != (severitate in ("majora", "critica")):
            raise SetInvalid(f"{sursa}: {d['id']}: un eșec cere severitate (majora / critica), o trecere nu")
    if contexte is not None and d["ctx"] not in contexte:
        raise SetInvalid(f"{sursa}: {d['id']}: contextul „{d['ctx']}” nu există în contexte.toml")
    campuri = d.get("campuri") or {}
    active = d.get("active") or []
    if not isinstance(campuri, dict) or not isinstance(active, list):
        raise SetInvalid(f"{sursa}: {d['id']}: `campuri` este obiect, `active` este listă")
    return Exemplu(
        id=str(d["id"]),
        set=set_,
        ctx=str(d["ctx"]),
        tip=str(d["tip"]),
        canal=str(d["canal"]),
        text=str(d["text"]),
        campuri=campuri,
        active=tuple(active),
        asteptat=asteptat,
        severitate=severitate if asteptat == "esec" else None,
        motiv=str(d.get("motiv", "")),
        validator=str(d.get("validator", "")),
        defect=str(d.get("defect", "")),
    )


def citeste_jsonl(
    cale: Path, set_: str, *, contexte: set[str] | None, validator: str = ""
) -> tuple[Exemplu, ...]:
    iesire: list[Exemplu] = []
    for nr, linie in enumerate(citeste_octeti(cale).decode().splitlines(), 1):
        if not linie.strip() or linie.lstrip().startswith("#"):
            continue
        d = _rand(cale, nr, linie)
        if validator:
            d.setdefault("validator", validator)
        iesire.append(_exemplu(d, set_, cale.name, contexte=contexte))
    ids = [e.id for e in iesire]
    if len(set(ids)) != len(ids):
        raise SetInvalid(f"{cale.name}: identificatori repetați")
    return tuple(iesire)


def citeste_contexte(director: Path = DIRECTOR) -> tuple[dt.datetime, dict[str, ProfilContext]]:
    brut = tomllib.loads(citeste_octeti(director / "contexte.toml").decode())
    la = dt.datetime.fromisoformat(str(brut["meta"]["la"]).replace("Z", "+00:00"))
    if la.tzinfo is None:
        la = la.replace(tzinfo=dt.UTC)
    profiluri = {
        pid: ProfilContext(
            id=pid,
            nume=str(p.get("nume", "")),
            ghid=p.get("ghid"),
            fapte=tuple(p.get("fapte", [])),
            oferte=tuple(p.get("oferte", [])),
            surse=tuple(p.get("surse", [])),
        )
        for pid, p in brut.get("contexte", {}).items()
    }
    if "gol" not in profiluri:
        raise SetInvalid("contexte.toml: lipsește profilul „gol”")
    return la, profiluri


def incarca(director: Path = DIRECTOR, *, promovate: tuple[Exemplu, ...] = ()) -> Seturi:
    la, contexte = citeste_contexte(director)
    ids = set(contexte)
    aur = {
        g: citeste_jsonl(director / f"{g}.jsonl", f"aur:{g}", contexte=ids, validator=g)
        for g in VALIDATORI
        if (director / f"{g}.jsonl").exists()
    }
    return Seturi(
        la=la,
        contexte=contexte,
        aur=aur,
        rele=citeste_jsonl(director / "rele.jsonl", "rele", contexte=ids),
        bune=citeste_jsonl(director / "bune.jsonl", "bune", contexte=ids),
        promovate=promovate,
        amprenta=amprenta_seturi(director),
    )
