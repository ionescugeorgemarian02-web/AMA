"""Fișiere WAV PCM pe 16 biți, mono (nucleu pur, fără dependențe): scriere, citire, bucăți proprii, energie.

Bucata proprie `amaw` (JSON) poartă cuvintele rostite de motorul de voce SIMULAT; motoarele reale nu o
scriu, iar cititorii obișnuiți o ignoră (RIFF permite bucăți necunoscute)."""

import array
import json
import math
import struct
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

BUCATA_CUVINTE = b"amaw"


@dataclass
class Wav:
    rata: int
    esantioane: array.array  # type: ignore[type-arg]  # 'h', mono
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def durata(self) -> float:
        return len(self.esantioane) / self.rata


def scrie(w: Wav) -> bytes:
    date = w.esantioane
    if sys.byteorder != "little":
        date = array.array("h", date)
        date.byteswap()
    corp = date.tobytes()
    fmt = struct.pack("<HHIIHH", 1, 1, w.rata, w.rata * 2, 2, 16)
    bucati = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    if w.extra:
        j = json.dumps(w.extra, ensure_ascii=False, separators=(",", ":")).encode()
        if len(j) % 2:
            j += b" "
        bucati += BUCATA_CUVINTE + struct.pack("<I", len(j)) + j
    bucati += b"data" + struct.pack("<I", len(corp)) + corp
    return b"RIFF" + struct.pack("<I", 4 + len(bucati)) + b"WAVE" + bucati


def citeste(corp: bytes) -> Wav:
    if corp[:4] != b"RIFF" or corp[8:12] != b"WAVE":
        raise ValueError("nu este un fișier WAV")
    poz, rata, date, extra = 12, 0, b"", {}
    while poz + 8 <= len(corp):
        cod, lung = corp[poz : poz + 4], struct.unpack("<I", corp[poz + 4 : poz + 8])[0]
        bucata = corp[poz + 8 : poz + 8 + lung]
        if cod == b"fmt ":
            tip, canale, rata, _, _, biti = struct.unpack("<HHIIHH", bucata[:16])
            if (tip, canale, biti) != (1, 1, 16):
                raise ValueError("doar PCM mono pe 16 biți")
        elif cod == b"data":
            date = bucata
        elif cod == BUCATA_CUVINTE:
            extra = json.loads(bucata.decode().strip())
        poz += 8 + lung + (lung % 2)
    if not rata:
        raise ValueError("WAV fără bucata fmt")
    es = array.array("h")
    es.frombytes(date[: len(date) - len(date) % 2])
    if sys.byteorder != "little":
        es.byteswap()
    return Wav(rata, es, extra)


def liniste(rata: int, secunde: float) -> array.array:  # type: ignore[type-arg]
    return array.array("h", bytes(2 * round(rata * secunde)))


def ton(rata: int, secunde: float, frecventa: float, amplitudine: float = 0.3) -> array.array:  # type: ignore[type-arg]
    """Un ton cu armonici și anvelopă moale (seamănă, ca energie, cu o silabă rostită)."""
    a = array.array("h")
    a.frombytes(_ton(rata, secunde, frecventa, amplitudine))
    return a


@lru_cache(maxsize=1024)
def _ton(rata: int, secunde: float, frecventa: float, amplitudine: float) -> bytes:
    n = round(rata * secunde)
    rampa = max(1, min(n // 4, round(rata * 0.015)))
    a = array.array("h", bytes(2 * n))
    w = 2 * math.pi * frecventa / rata
    for i in range(n):
        env = min(1.0, i / rampa, (n - 1 - i) / rampa)
        v = math.sin(w * i) + 0.5 * math.sin(2 * w * i) + 0.25 * math.sin(3 * w * i)
        a[i] = int(32767 * amplitudine * env * v / 1.75)
    return a.tobytes()


def energii(w: Wav, cadru_sec: float = 0.01) -> list[float]:
    """Energia RMS (0..1) pe cadre de `cadru_sec`."""
    pas = max(1, round(w.rata * cadru_sec))
    es = w.esantioane
    out = []
    for i in range(0, len(es), pas):
        bloc = es[i : i + pas]
        out.append(math.sqrt(sum(x * x for x in bloc) / len(bloc)) / 32768 if bloc else 0.0)
    return out


def segmente(
    w: Wav, *, prag: float = 0.01, pauza_min: float = 0.03, durata_min: float = 0.05, cadru_sec: float = 0.01
) -> list[tuple[float, float]]:
    """Intervalele cu sunet (început, sfârșit, în secunde), despărțite de liniști de cel puțin `pauza_min`."""
    e = energii(w, cadru_sec)
    brut: list[list[float]] = []
    for i, v in enumerate(e):
        if v >= prag:
            t = i * cadru_sec
            if brut and t - brut[-1][1] < pauza_min + 1e-9:
                brut[-1][1] = t + cadru_sec
            else:
                brut.append([t, t + cadru_sec])
    return [(round(a, 3), round(min(b, w.durata), 3)) for a, b in brut if b - a >= durata_min]
