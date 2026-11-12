"""Registrul de prompturi (8.8): versiuni, stări, randarea șablonului și încărcarea din fișierele din repo.

Un prompt are nume, versiune, profil, șablon (și opțional un mesaj de sistem), schema de ieșire și stare:
`ciorna` (se poate edita), `activ` (în folosință; nu se mai modifică, impus în bază), `retras`. Pentru o
schimbare se
creează o versiune nouă, apoi se activează: cea veche se retrage în aceeași tranzacție. Un apel folosește
versiunea
activă (`nume`) sau una anume (`nume@3`, de exemplu pentru evaluarea unei ciorne).

Șabloanele au locuri `{{variabila}}`, completate într-o singură trecere: valoarea unei variabile nu se mai
interpretează (un text adus din exterior nu poate introduce alte locuri sau instrucțiuni de șablon).
Variabilele
lipsă și cele în plus sunt erori (greșelile de scris se văd, nu trec).

Fișierele din repo (`prompts/<nume>.v<versiune>.md`): un antet `---` cu `profil`, `schema`
(`modul.Clasa`, doar din
`app.`), `stare` și `descriere`, apoi secțiunile `@@sistem` și `@@utilizator`. `sincronizeaza` le aduce
în bază și
refuză orice schimbare a unei versiuni care nu mai e ciornă.
"""

import hashlib
import importlib
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.gateway import registru
from app.gateway.erori import ApelRefuzat, EroareGateway
from app.gateway.iesire import Iesire, cheie_schema, schema_json
from app.gateway.modele import PromptGateway
from app.gateway.tipuri import Mesaj
from app.ids import new_id
from app.operare import audit

PREFIXE_SCHEMA = ("app.",)  # testele adaugă `tests.`
NUME = re.compile(r"^[a-z][a-z0-9_.]{1,60}$")
LOC = re.compile(r"\{\{\s*([a-z][a-z0-9_]{0,40})\s*\}\}")
REFERINTA = re.compile(r"^([a-z][a-z0-9_.]{1,60})(?:@(\d{1,6}))?$")
STARI = ("ciorna", "activ", "retras")


class PromptInvalid(EroareGateway):
    """Un prompt nu poate fi creat, activat sau încărcat așa cum e cerut."""


@dataclass(frozen=True)
class Reperat:
    """Un prompt gata de folosit, fără legătură cu sesiunea."""

    id: uuid.UUID
    nume: str
    versiune: int
    stare: str
    profil: str
    sistem: str
    sablon: str
    schema_nume: str

    @property
    def referinta(self) -> str:
        return f"{self.nume}@{self.versiune}"


def amprenta(sistem: str, sablon: str, profil: str, schema_nume: str) -> str:
    return hashlib.sha256("\x1f".join((profil, schema_nume, sistem, sablon)).encode()).hexdigest()


def locuri(*texte: str) -> set[str]:
    return {m.group(1) for t in texte for m in LOC.finditer(t)}


def randeaza(text: str, variabile: Mapping[str, Any]) -> str:
    """Completează `{{loc}}`-urile într-o singură trecere; valorile nu se reinterpretează."""
    return LOC.sub(lambda m: str(variabile[m.group(1)]), text)


def mesaje_pentru(p: Reperat, variabile: Mapping[str, Any]) -> tuple[Mesaj, ...]:
    """Mesajele unui apel: `sistem` (dacă există) și `utilizator`, cu variabilele puse. Variabilele trebuie să
    se potrivească exact cu locurile din prompt."""
    cerute = locuri(p.sistem, p.sablon)
    date = set(variabile)
    if cerute - date:
        raise ApelRefuzat("variabile_lipsa", f"{p.referinta}: lipsesc {sorted(cerute - date)}")
    if date - cerute:
        raise ApelRefuzat("variabile_necunoscute", f"{p.referinta}: în plus {sorted(date - cerute)}")
    mesaje = [Mesaj("user", randeaza(p.sablon, variabile))]
    if p.sistem:
        mesaje.insert(0, Mesaj("system", randeaza(p.sistem, variabile)))
    return tuple(mesaje)


def _reperat(p: PromptGateway) -> Reperat:
    return Reperat(p.id, p.nume, p.versiune, p.stare, p.profil, p.sistem, p.sablon, p.schema_nume)


def rezolva(db: Session, referinta: str) -> Reperat | None:
    """`nume` → versiunea activă; `nume@3` → exact acea versiune (orice stare, pentru evaluări)."""
    m = REFERINTA.match(referinta)
    if m is None:
        return None
    nume, versiune = m.group(1), m.group(2)
    q = select(PromptGateway).where(PromptGateway.nume == nume)
    q = (
        q.where(PromptGateway.versiune == int(versiune))
        if versiune
        else q.where(PromptGateway.stare == "activ")
    )
    p = db.execute(q).scalar_one_or_none()
    return None if p is None else _reperat(p)


def lista(db: Session, *, nume: str | None = None) -> list[PromptGateway]:
    q = select(PromptGateway).order_by(PromptGateway.nume, PromptGateway.versiune.desc())
    if nume:
        q = q.where(PromptGateway.nume == nume)
    return list(db.execute(q).scalars())


def creeaza(
    db: Session,
    nume: str,
    *,
    profil: str,
    sablon: str,
    schema: type[Iesire],
    sistem: str = "",
    descriere: str = "",
    versiune: int | None = None,
    utilizator_id: uuid.UUID | None = None,
) -> PromptGateway:
    """O versiune nouă, în stare de ciornă (numerotată în continuare dacă nu se dă `versiune`)."""
    if not NUME.match(nume):
        raise PromptInvalid(f"nume de prompt nepermis: {nume!r}")
    if registru.profil(db, profil) is None:
        raise PromptInvalid(f"profil necunoscut: {profil!r}")
    if versiune is None:
        ultima = db.execute(
            select(func.max(PromptGateway.versiune)).where(PromptGateway.nume == nume)
        ).scalar_one()
        versiune = (ultima or 0) + 1
    p = PromptGateway(
        id=new_id(), nume=nume, versiune=versiune, stare="ciorna", profil=profil, sistem=sistem,
        sablon=sablon,
        schema_nume=cheie_schema(schema), schema_json=schema_json(schema), descriere=descriere,
        amprenta=amprenta(sistem, sablon, profil, cheie_schema(schema)), creat_de=utilizator_id,
    )  # fmt: skip
    db.add(p)
    db.flush()
    audit.record(
        db, "gateway.prompt_creat", obiect_tip="prompt", obiect_id=f"{nume}@{versiune}",
        utilizator_id=utilizator_id,
        tenant_id=None, detalii={"prompt": nume, "versiune": versiune, "profil": profil},
    )  # fmt: skip
    return p


def _gaseste(db: Session, nume: str, versiune: int) -> PromptGateway:
    p = db.execute(
        select(PromptGateway).where(PromptGateway.nume == nume, PromptGateway.versiune == versiune)
    ).scalar_one_or_none()
    if p is None:
        raise PromptInvalid(f"promptul {nume}@{versiune} nu există")
    return p


def modifica_ciorna(
    db: Session, nume: str, versiune: int, *, sablon: str | None = None, sistem: str | None = None
) -> None:
    """Doar o ciornă se poate edita (baza refuză orice altceva)."""
    p = _gaseste(db, nume, versiune)
    if p.stare != "ciorna":
        raise PromptInvalid(f"{nume}@{versiune} nu mai e ciornă: creează o versiune nouă")
    p.sablon = sablon if sablon is not None else p.sablon
    p.sistem = sistem if sistem is not None else p.sistem
    p.amprenta = amprenta(p.sistem, p.sablon, p.profil, p.schema_nume)
    db.flush()


def activeaza(
    db: Session, nume: str, versiune: int, *, utilizator_id: uuid.UUID | None = None
) -> PromptGateway:
    """Activează o ciornă; versiunea activă de până acum se retrage în aceeași tranzacție."""
    p = _gaseste(db, nume, versiune)
    if p.stare != "ciorna":
        raise PromptInvalid(f"{nume}@{versiune} este {p.stare}: se activează doar o ciornă")
    anterioara = db.execute(
        select(PromptGateway).where(PromptGateway.nume == nume, PromptGateway.stare == "activ")
    ).scalar_one_or_none()
    if anterioara is not None:
        anterioara.stare, anterioara.retras_la = "retras", func.now()
        db.flush()
    p.stare, p.activat_la = "activ", func.now()
    db.flush()
    audit.record(
        db, "gateway.prompt_activat", obiect_tip="prompt", obiect_id=f"{nume}@{versiune}",
        utilizator_id=utilizator_id,
        tenant_id=None, detalii={"prompt": nume, "versiune": versiune,
                                  "retrasa": anterioara.versiune if anterioara else None},
    )  # fmt: skip
    return p


def retrage(
    db: Session, nume: str, versiune: int, *, utilizator_id: uuid.UUID | None = None
) -> PromptGateway:
    p = _gaseste(db, nume, versiune)
    if p.stare == "retras":
        return p
    p.stare, p.retras_la = "retras", func.now()
    db.flush()
    audit.record(
        db, "gateway.prompt_retras", obiect_tip="prompt", obiect_id=f"{nume}@{versiune}",
        utilizator_id=utilizator_id,
        tenant_id=None, detalii={"prompt": nume, "versiune": versiune},
    )  # fmt: skip
    return p


# --- fișierele din repo


@dataclass(frozen=True)
class FisierPrompt:
    nume: str
    versiune: int
    profil: str
    schema: str
    stare: str
    descriere: str
    sistem: str
    sablon: str


NUME_FISIER = re.compile(r"^([a-z][a-z0-9_.]{1,60})\.v(\d{1,6})\.md$")


def citeste_fisier(cale: Path) -> FisierPrompt:
    m = NUME_FISIER.match(cale.name)
    if m is None:
        raise PromptInvalid(f"{cale.name}: numele trebuie să fie <nume>.v<versiune>.md")
    text = cale.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise PromptInvalid(f"{cale.name}: lipsește antetul `---`")
    antet, corp = text[4:].split("\n---\n", 1)
    camp: dict[str, str] = {}
    for linie in antet.splitlines():
        if linie.strip():
            cheie, _, valoare = linie.partition(":")
            camp[cheie.strip()] = valoare.strip()
    sectiuni: dict[str, list[str]] = {}
    curenta: str | None = None
    for linie in corp.splitlines():
        if linie.startswith("@@"):
            curenta = linie[2:].strip()
            sectiuni[curenta] = []
        elif curenta is not None:
            sectiuni[curenta].append(linie)
    if "utilizator" not in sectiuni or set(sectiuni) - {"sistem", "utilizator"}:
        raise PromptInvalid(f"{cale.name}: secțiunile permise sunt @@sistem (opțional) și @@utilizator")
    for obligatoriu in ("profil", "schema"):
        if not camp.get(obligatoriu):
            raise PromptInvalid(f"{cale.name}: lipsește `{obligatoriu}` din antet")
    stare = camp.get("stare", "ciorna")
    if stare not in ("ciorna", "activ"):
        raise PromptInvalid(f"{cale.name}: starea dintr-un fișier este `ciorna` sau `activ`")
    return FisierPrompt(
        nume=m.group(1), versiune=int(m.group(2)), profil=camp["profil"], schema=camp["schema"], stare=stare,
        descriere=camp.get("descriere", ""),
        sistem="\n".join(sectiuni.get("sistem", [])).strip("\n"),
        sablon="\n".join(sectiuni["utilizator"]).strip("\n"),
    )  # fmt: skip


def _schema(cale: str) -> type[Iesire]:
    if not cale.startswith(PREFIXE_SCHEMA) or "." not in cale:
        raise PromptInvalid(f"schema {cale!r}: doar clase din `app.`")
    modul, _, clasa = cale.rpartition(".")
    try:
        obiect = getattr(importlib.import_module(modul), clasa)
    except (ImportError, AttributeError):
        raise PromptInvalid(f"schema {cale!r} nu există") from None
    if not (isinstance(obiect, type) and issubclass(obiect, Iesire)):
        raise PromptInvalid(f"schema {cale!r} nu moștenește Iesire")
    return obiect


def sincronizeaza(db: Session, director: Path, *, utilizator_id: uuid.UUID | None = None) -> list[str]:
    """Aduce fișierele din `director` în bază. Întoarce referințele create sau actualizate (ciorne).

    O versiune existentă care nu mai e ciornă și al cărei conținut diferă de fișier este o EROARE
    (versiunile active
    nu se modifică): fișierul trebuie să devină o versiune nouă."""
    schimbate: list[str] = []
    for cale in sorted(director.glob("*.md")):
        f = citeste_fisier(cale)
        schema = _schema(f.schema)
        nou = amprenta(f.sistem, f.sablon, f.profil, cheie_schema(schema))
        existent = db.execute(
            select(PromptGateway).where(PromptGateway.nume == f.nume, PromptGateway.versiune == f.versiune)
        ).scalar_one_or_none()
        if existent is None:
            creeaza(
                db, f.nume, profil=f.profil, sablon=f.sablon, schema=schema, sistem=f.sistem,
                descriere=f.descriere, versiune=f.versiune, utilizator_id=utilizator_id,
            )  # fmt: skip
            if f.stare == "activ":
                activeaza(db, f.nume, f.versiune, utilizator_id=utilizator_id)
            schimbate.append(f"{f.nume}@{f.versiune}")
        elif existent.amprenta != nou:
            if existent.stare != "ciorna":
                raise PromptInvalid(
                    f"{cale.name}: conținutul diferă de {f.nume}@{f.versiune}, care este {existent.stare}; "
                    "versiunile nu se modifică, creează fișierul unei versiuni noi"
                )
            modifica_ciorna(db, f.nume, f.versiune, sablon=f.sablon, sistem=f.sistem)
            schimbate.append(f"{f.nume}@{f.versiune}")
        elif f.stare == "activ" and existent.stare == "ciorna":
            activeaza(db, f.nume, f.versiune, utilizator_id=utilizator_id)
            schimbate.append(f"{f.nume}@{f.versiune}")
    return schimbate
