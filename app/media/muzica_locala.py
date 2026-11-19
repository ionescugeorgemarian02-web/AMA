"""Muzică de fundal compusă local (fără furnizor, fără licență externă): un pat lo-fi cald, determinist.

Progresie de patru acorduri (după „stare”), pian electric moale (armonici cu stingere), bas rotund
și un shaker discret pe optimi; totul trecut printr-un filtru trece-jos și normalizat de FFmpeg. Pur Python
(`array` + `math`), randat la 24 kHz și convertit la 48 kHz. Licența: producție proprie a agenției.

    corp, licenta = MuzicaLocala().piesa("calm", 40.0)   # interfața `BibliotecaMuzica`
"""

import array
import math
import random
import tempfile
from pathlib import Path

from app.media import ffmpeg

RATA = 24000
# acordurile (semitonuri față de tonică) și tempo-ul fiecărei stări
PROGRESII: dict[str, tuple[tuple[tuple[int, ...], ...], int]] = {
    "calm": (((0, 4, 7, 11), (9, 12, 16, 19), (5, 9, 12, 16), (7, 11, 14, 17)), 78),
    "energic": (((0, 4, 7, 12), (7, 11, 14, 19), (9, 12, 16, 21), (5, 9, 12, 17)), 104),
    "cald": (((0, 3, 7, 10), (5, 8, 12, 15), (10, 14, 17, 21), (3, 7, 10, 14)), 84),
}
TONICA = 220.0 * 2 ** (-2 / 12)  # sol, sub la4


def _f(semiton: float) -> float:
    return TONICA * 2 ** (semiton / 12)


def _adauga(buf: array.array, start: int, frecv: float, durata: float, amp: float, stingere: float) -> None:  # type: ignore[type-arg]
    """O notă de pian electric: fundamentala + două armonici, atac scurt, stingere exponențială."""
    n = min(int(durata * RATA), len(buf) - start)
    w = 2 * math.pi * frecv / RATA
    for i in range(n):
        t = i / RATA
        env = min(1.0, t / 0.012) * math.exp(-t * stingere)
        buf[start + i] += (
            amp * env * (math.sin(w * i) + 0.35 * math.sin(2 * w * i) + 0.12 * math.sin(3 * w * i))
        )


def compune(stare: str, durata: float) -> array.array:  # type: ignore[type-arg]
    progresie, bpm = PROGRESII.get(stare, PROGRESII["calm"])
    rnd = random.Random(stare)  # noqa: S311 (muzică, nu criptografie)
    total = int((durata + 1.0) * RATA)
    buf = array.array("d", bytes(8 * total))
    bataie = 60.0 / bpm
    masura = 4 * bataie
    m = 0
    while m * masura < durata + 1.0:
        acord = progresie[m % len(progresie)]
        s0 = int(m * masura * RATA)
        for k, semi in enumerate(acord):  # acordul, ușor arpegiat
            _adauga(buf, s0 + int(k * 0.025 * RATA), _f(semi), masura * 1.1, 0.10, 1.1)
        for b in (0, 2.5):  # basul: pe 1 și pe „și”-ul lui 3
            _adauga(buf, s0 + int(b * bataie * RATA), _f(acord[0] - 24), bataie * 1.4, 0.22, 2.2)
        for o in range(8):  # shaker: zgomot scurt, accent pe contratimp
            st = s0 + int(o * bataie / 2 * RATA)
            amp = 0.025 if o % 2 else 0.012
            for i in range(min(int(0.04 * RATA), total - st)):
                buf[st + i] += amp * (rnd.random() * 2 - 1) * math.exp(-i / (0.008 * RATA))
        if m % 2 == 1:  # o notă de melodie, rar
            _adauga(buf, s0 + int(1.5 * bataie * RATA), _f(rnd.choice(acord) + 12), bataie * 2, 0.06, 1.6)
        m += 1
    return buf


def wav(stare: str, durata: float) -> bytes:
    buf = compune(stare, durata)
    varf = max(1e-9, max(abs(x) for x in buf))
    pcm = array.array("h", (int(32767 * 0.8 * x / varf) for x in buf))
    with tempfile.TemporaryDirectory() as d:
        brut, iesire = Path(d) / "m.raw", Path(d) / "m.wav"
        brut.write_bytes(pcm.tobytes())
        ffmpeg.ruleaza(["-f", "s16le", "-ar", str(RATA), "-ac", "1", "-i", str(brut),
                        "-af", f"lowpass=f=5200,afade=t=in:d=0.8,afade=t=out:st={max(0.0, durata - 1.5):.2f}:d=1.5",  # noqa: E501
                        "-t", f"{durata:.2f}", "-ar", "48000", "-c:a", "pcm_s16le", str(iesire)])  # fmt: skip
        return iesire.read_bytes()


class MuzicaLocala:
    """`BibliotecaMuzica` reală, locală: piesa compusă aici, cu licența de producție proprie."""

    nume = "muzica-locala"

    def piesa(self, stare: str, durata: float) -> tuple[bytes, dict[str, str]]:
        return wav(stare, durata), {
            "identificator": f"lofi-{stare}-{durata:.0f}s",
            "autor": "AMA (compoziție procedurală internă)",
            "copie": "Producție proprie a agenției: folosire comercială pe orice platformă, "
            "fără drepturi terțe.",
        }
