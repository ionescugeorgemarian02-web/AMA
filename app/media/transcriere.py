"""Transcrierea inversă și timpii pe cuvânt (F8.3, docs/14 §14.4–14.5).

Narațiunea se transcrie înapoi și se potrivește cu scriptul (cuvintele normalizate): fiecare cuvânt din script
primește momentul lui în pistă (baza de timp a montajului și a subtitrărilor), iar fiecare frază primește
rata de
erori (WER). O frază peste prag se resintetizează o dată, apoi se semnalează.

Transcriptorul stă în spatele unui adaptor: whisper.cpp local (NEVERIFICAT, la migrare) și cel SIMULAT,
care măsoară
momentele din SEMNAL (segmente de energie) și ia cuvintele din bucata `amaw` a vocii simulate; fără ea
(filmări
reale, formatul E) face aliniere forțată pe textul așteptat.
"""

import difflib
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session

from app.config import get_settings
from app.media import audio, voce

PRAG_WER = 0.15  # [I] peste atât, fraza e citită greșit


@dataclass(frozen=True)
class CuvantTimp:
    cuvant: str
    inceput: float
    sfarsit: float


class Transcriptor(Protocol):
    def transcrie(self, wav: audio.Wav, *, asteptat: str = "") -> list[CuvantTimp]: ...


def jetoane(text: str) -> list[str]:
    return [t for t in re.split(r"[^\wăâîșțĂÂÎȘȚ-]+", text.lower()) if t.strip("-")]


def _forteaza(segmente: list[tuple[float, float]], cuvinte: list[str]) -> list[CuvantTimp]:
    """Aliniere forțată: cuvintele, în ordine, împărțite pe segmentele de vorbire proporțional cu silabele."""
    if not segmente or not cuvinte:
        return []
    total_t = sum(b - a for a, b in segmente)
    total_s = sum(voce.silabe(c) for c in cuvinte)
    out: list[CuvantTimp] = []
    i = 0
    for a, b in segmente:
        cota = round((b - a) / total_t * total_s) if total_t else 0
        bucata: list[str] = []
        while i < len(cuvinte) and (sum(voce.silabe(c) for c in bucata) < cota or not bucata):
            bucata.append(cuvinte[i])
            i += 1
        s = sum(voce.silabe(c) for c in bucata) or 1
        t = a
        for c in bucata:
            d = (b - a) * voce.silabe(c) / s
            out.append(CuvantTimp(c, round(t, 3), round(t + d, 3)))
            t += d
    for c in cuvinte[i:]:  # rest: pe ultimul segment
        out.append(CuvantTimp(c, out[-1].sfarsit, out[-1].sfarsit))
    return out


class TranscriptorSimulat:
    """# SIMULAT: momentele din semnal, cuvintele din bucata `amaw` (sau aliniere forțată pe `asteptat`)."""

    def transcrie(self, wav: audio.Wav, *, asteptat: str = "") -> list[CuvantTimp]:
        seg = audio.segmente(wav)
        rostite = wav.extra.get("cuvinte")
        if rostite:
            if len(seg) == len(rostite):
                return [CuvantTimp(r["w"], a, b) for r, (a, b) in zip(rostite, seg, strict=True)]
            return [CuvantTimp(r["w"], r["s"], r["e"]) for r in rostite]
        return _forteaza(seg, jetoane(asteptat))


class TranscriptorWhisper:
    """# NEVERIFICAT: whisper.cpp local (`AMA_WHISPER_BIN`, `AMA_WHISPER_MODEL`), cu timpi pe cuvânt
    (JSON)."""

    def transcrie(self, wav: audio.Wav, *, asteptat: str = "") -> list[CuvantTimp]:
        import json

        s = get_settings()
        binar = s.whisper_bin or shutil.which("whisper-cli")
        if not binar:
            raise RuntimeError("whisper.cpp nu este instalat (AMA_WHISPER_BIN)")
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "n.wav"
            f.write_bytes(audio.scrie(wav))
            subprocess.run(
                [
                    binar,
                    "-m",
                    s.whisper_model,
                    "-l",
                    "ro",
                    "-ml",
                    "1",
                    "-ojf",
                    "-of",
                    str(Path(d) / "o"),
                    str(f),
                ],
                check=True,
                capture_output=True,
                timeout=600,
            )
            date = json.loads((Path(d) / "o.json").read_text())
        return [
            CuvantTimp(x["text"].strip(), x["offsets"]["from"] / 1000, x["offsets"]["to"] / 1000)
            for x in date.get("transcription", [])
            if x["text"].strip()
        ]


_transcriptor_fortat: Transcriptor | None = None


def seteaza_transcriptor(t: Transcriptor | None) -> None:
    global _transcriptor_fortat
    _transcriptor_fortat = t


def transcriptor() -> Transcriptor:
    if _transcriptor_fortat is not None:
        return _transcriptor_fortat
    return TranscriptorWhisper() if get_settings().whisper_bin else TranscriptorSimulat()


@dataclass
class FrazaVerificata:
    text: str
    wer: float
    auzit: str

    @property
    def corecta(self) -> bool:
        return self.wer <= PRAG_WER


@dataclass
class Aliniere:
    cuvinte: list[CuvantTimp]  # cuvintele SCRIPTULUI, fiecare cu momentul lui
    fraze: list[FrazaVerificata]

    @property
    def semnalate(self) -> list[int]:
        return [i for i, f in enumerate(self.fraze) if not f.corecta]


def wer(asteptat: list[str], auzit: list[str]) -> float:
    if not asteptat:
        return 0.0 if not auzit else 1.0
    sm = difflib.SequenceMatcher(a=asteptat, b=auzit, autojunk=False)
    corecte = sum(b.size for b in sm.get_matching_blocks())
    return round((max(len(asteptat), len(auzit)) - corecte) / len(asteptat), 3)


def aliniaza(fraze: list[str], auzite: list[CuvantTimp]) -> Aliniere:
    """Potrivește cuvintele auzite cu scriptul; cuvintele din script fără pereche primesc momentul
    vecinilor."""
    script: list[tuple[int, str]] = [(i, c) for i, f in enumerate(fraze) for c in jetoane(f)]
    a = [c for _, c in script]
    b = [jetoane(x.cuvant)[0] if jetoane(x.cuvant) else "" for x in auzite]
    momente: list[tuple[float, float] | None] = [None] * len(a)
    perechi: list[int | None] = [None] * len(a)
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal" or (op == "replace" and i2 - i1 == j2 - j1):
            for k in range(i2 - i1):
                momente[i1 + k] = (auzite[j1 + k].inceput, auzite[j1 + k].sfarsit)
                perechi[i1 + k] = j1 + k
        elif op == "replace":
            t0, t1 = auzite[j1].inceput, auzite[j2 - 1].sfarsit
            pas = (t1 - t0) / (i2 - i1)
            for k in range(i2 - i1):
                momente[i1 + k] = (round(t0 + k * pas, 3), round(t0 + (k + 1) * pas, 3))
    for k, m in enumerate(momente):  # cuvinte nerostite: între vecini
        if m is None:
            prev = next((momente[x][1] for x in range(k - 1, -1, -1) if momente[x]), 0.0)  # type: ignore[index]
            momente[k] = (prev, prev)
    cuvinte = [CuvantTimp(c, *momente[k]) for k, (_, c) in enumerate(script)]  # type: ignore[misc]
    verificate: list[FrazaVerificata] = []
    for i, f in enumerate(fraze):
        idx = [k for k, (fi, _) in enumerate(script) if fi == i]
        if not idx:
            verificate.append(FrazaVerificata(f, 0.0, ""))
            continue
        t0, t1 = cuvinte[idx[0]].inceput, cuvinte[idx[-1]].sfarsit
        auz = [b[j] for j, x in enumerate(auzite) if x.inceput >= t0 - 0.01 and x.sfarsit <= t1 + 0.01]
        verificate.append(FrazaVerificata(f, wer([a[k] for k in idx], auz), " ".join(auz)))
    return Aliniere(cuvinte, verificate)


@dataclass
class NaratiuneVerificata:
    naratiune: voce.Naratiune
    aliniere: Aliniere
    resintetizata: bool = False
    semnalate: list[str] = field(default_factory=list)


def naratiune_verificata(
    db: Session,
    tenant_id: uuid.UUID,
    fraze: list[str],
    *,
    profil_cod: str | None = None,
    gresit: dict[str, str] | None = None,
) -> NaratiuneVerificata:
    """Sintetizează, transcrie înapoi, aliniază; frazele greșite se resintetizează o dată, apoi se
    semnalează."""
    t = transcriptor()
    n = voce.sintetizeaza(db, tenant_id, fraze, profil_cod=profil_cod, gresit=gresit)
    al = aliniaza(fraze, t.transcrie(n.wav, asteptat=" ".join(fraze)))
    resint = False
    if al.semnalate:
        resint = True
        n = voce.sintetizeaza(db, tenant_id, fraze, profil_cod=profil_cod, gresit=gresit)
        al = aliniaza(fraze, t.transcrie(n.wav, asteptat=" ".join(fraze)))
    return NaratiuneVerificata(n, al, resint, [al.fraze[i].text for i in al.semnalate])
