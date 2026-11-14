"""FFmpeg și ffprobe (F8, docs/14): rulare cu limită de timp, fără shell, cu memoria de vârf măsurată (F8.9).

Programul determinist execută lista de montaj; modelul nu scrie niciodată comenzi FFmpeg (14.6)."""

import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FONT_IMPLICIT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


class EroareFfmpeg(RuntimeError):
    pass


@dataclass(frozen=True)
class Rulare:
    stderr: str
    secunde: float
    memorie_mb: float  # vârful de memorie rezidentă al procesului (ru_maxrss)


_rulari: ContextVar[list[Rulare] | None] = ContextVar("ffmpeg_rulari", default=None)


@contextmanager
def masurare() -> Iterator[list[Rulare]]:
    """Strânge rulările ffmpeg din bloc (timp, memorie de vârf), pentru măsurătorile unei randări (F8.9)."""
    lista: list[Rulare] = []
    jeton = _rulari.set(lista)
    try:
        yield lista
    finally:
        _rulari.reset(jeton)


def disponibil() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def ruleaza(args: list[str], *, timp_maxim: float = 900.0, fir: int | None = None) -> Rulare:
    """Rulează `ffmpeg <args>` și întoarce stderr, durata și memoria de vârf (din `wait4`)."""
    binar = shutil.which("ffmpeg")
    if not binar:
        raise EroareFfmpeg("ffmpeg nu este instalat")
    cmd = [binar, "-hide_banner", "-nostdin", "-y"]
    if fir:
        cmd += ["-threads", str(fir)]
    with tempfile.TemporaryFile() as err:
        t0 = time.monotonic()
        p = subprocess.Popen([*cmd, *args], stdout=subprocess.DEVNULL, stderr=err)
        oprit = threading.Timer(timp_maxim, lambda: os.kill(p.pid, signal.SIGKILL))
        oprit.start()
        try:
            _, stare, ru = os.wait4(p.pid, 0)
        finally:
            oprit.cancel()
        p.returncode = os.waitstatus_to_exitcode(stare)
        err.seek(0)
        text = err.read().decode(errors="replace")
    if p.returncode != 0:
        raise EroareFfmpeg(f"ffmpeg a eșuat ({p.returncode}): {text[-800:]}")
    rez = Rulare(text, time.monotonic() - t0, ru.ru_maxrss / 1024)
    colector = _rulari.get()
    if colector is not None:
        colector.append(rez)
    return rez


def probe(cale: str | Path) -> dict[str, Any]:
    binar = shutil.which("ffprobe")
    if not binar:
        raise EroareFfmpeg("ffprobe nu este instalat")
    r = subprocess.run(
        [binar, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(cale)],
        capture_output=True,
        timeout=60,
        check=False,
    )
    if r.returncode != 0:
        raise EroareFfmpeg(f"ffprobe a eșuat: {r.stderr.decode(errors='replace')[-400:]}")
    return json.loads(r.stdout)  # type: ignore[no-any-return]


def durata(cale: str | Path) -> float:
    return float(probe(cale)["format"]["duration"])


def clip_sintetic(cheie: str, *, durata: float = 6.0, latime: int = 1080, inaltime: int = 1920) -> bytes:
    """# SIMULAT: un clip vertical MP4 determinist (imagine în mișcare, fără sunet), în locul unui clip de
    stock."""
    nuanta = sum(cheie.encode()) % 360
    with tempfile.TemporaryDirectory() as d:
        iesire = Path(d) / "c.mp4"
        ruleaza(
            [
                "-f", "lavfi", "-i", f"testsrc2=s={latime}x{inaltime}:r=30:d={durata}",
                "-vf", f"hue=h={nuanta}:s=0.6,format=yuv420p",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-an", "-movflags", "+faststart",
                "-fflags", "+bitexact", "-flags:v", "+bitexact", str(iesire),
            ],
            fir=2,
        )  # fmt: skip
        return iesire.read_bytes()
