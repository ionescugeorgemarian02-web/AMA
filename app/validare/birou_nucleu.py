"""Nucleul pur al biroului de aprobări (F5.9, docs/18 §18.3): ordinea cererilor, diferența dintre versiuni,
statistica
motivelor de respingere. Fără bază, fără ceas real (momentul vine ca parametru)."""

import datetime as dt
import difflib
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

URGENT = dt.timedelta(hours=2)  # [I] o cerere care expiră în mai puțin de atât urcă în capul listei
# Prioritatea pe tip de livrabil [I]: banii și imaginea publică întâi (reclame, pagini de vânzare), apoi
# restul.
PRIORITATE_TIP = {
    "reclama_text": 0,
    "pagina_captare": 0,
    "email": 1,
    "script_video_scurt": 1,
    "script_video_lung": 1,
    "postare": 2,
    "carusel": 2,
}
PRIORITATE_IMPLICITA = 2


@dataclass(frozen=True)
class Cheie:
    id: str
    termen_la: dt.datetime  # termenul cererii de aprobare
    tip: str
    slot_la: dt.datetime | None = None  # termenul livrabilului (slotul de publicare)


def prioritate(tip: str) -> int:
    return PRIORITATE_TIP.get(tip, PRIORITATE_IMPLICITA)


def ordoneaza(cereri: Iterable[Cheie], acum: dt.datetime) -> list[str]:
    """Întâi cererile urgente (termen în < 2 ore), apoi după termen, prioritatea tipului și slotul de
    publicare."""
    departe = dt.datetime.max.replace(tzinfo=dt.UTC)

    def cheie(c: Cheie) -> tuple[bool, dt.datetime, int, dt.datetime, str]:
        return (c.termen_la - acum >= URGENT, c.termen_la, prioritate(c.tip), c.slot_la or departe, c.id)

    return [c.id for c in sorted(cereri, key=cheie)]


@dataclass(frozen=True)
class Bucata:
    tip: str  # „egal”, „scos”, „adaugat”
    text: str


def diferenta(vechi: str, nou: str) -> list[Bucata]:
    """Diferența pe cuvinte între două versiuni (pentru afișare și pentru exemplul salvat la editare)."""
    a, b = vechi.split(), nou.split()
    iesire: list[Bucata] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            iesire.append(Bucata("egal", " ".join(a[i1:i2])))
            continue
        if i2 > i1:
            iesire.append(Bucata("scos", " ".join(a[i1:i2])))
        if j2 > j1:
            iesire.append(Bucata("adaugat", " ".join(b[j1:j2])))
    return iesire


def statistica_motive(motive: Iterable[str | None], etichete: dict[str, str]) -> list[tuple[str, str, int]]:
    """(cod, eticheta, număr) pentru respingeri, cele mai frecvente primele; fără cod → „altceva”."""
    c = Counter(m if m in etichete else "altceva" for m in motive)
    return sorted(((k, etichete.get(k, k), n) for k, n in c.items()), key=lambda x: (-x[2], x[0]))
