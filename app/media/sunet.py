"""Sunetul (F8.7, docs/14 §14.8, docs/09 §9.5): vocea în față, muzica atenuată automat sub voce, nivelul final
în țintă (−14 LUFS integrat, vârf adevărat sub −1 dBTP).

Mixul se face în doi pași: (1) vocea + muzica (nivelul ei și compresia condusă de voce, `sidechaincompress`),
măsurat cu `ebur128`; (2) câștigul care aduce mixul la țintă, cu limitator. „Fără muzică” e o variantă validă.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from app.media import ffmpeg

TINTA_LUFS = -14.0
TOLERANTA_LU = 1.0  # [I]
VARF_MAX_DBTP = -1.0
LIMITA_LINIARA = 0.79  # ≈ −2 dBFS, cu loc pentru vârfurile dintre eșantioane


@dataclass(frozen=True)
class Nivel:
    lufs: float
    varf_dbtp: float

    @property
    def in_tinta(self) -> bool:
        return abs(self.lufs - TINTA_LUFS) <= TOLERANTA_LU and self.varf_dbtp <= VARF_MAX_DBTP


def masoara(cale: Path, *, de_la: float | None = None, pana_la: float | None = None) -> Nivel:
    """Nivelul integrat și vârful adevărat (EBU R128) al pistei audio, pe tot fișierul sau pe un interval."""
    args = []
    if de_la is not None:
        args += ["-ss", f"{de_la:.3f}"]
    if pana_la is not None:
        args += ["-to", f"{pana_la:.3f}"]
    r = ffmpeg.ruleaza([*args, "-i", str(cale), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
    rezumat = r.stderr[r.stderr.rfind("Summary:") :]
    i = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", rezumat)
    p = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", rezumat)
    lufs = float(i.group(1)) if i and i.group(1) != "-inf" else -99.0
    varf = float(p.group(1)) if p and p.group(1) != "-inf" else -99.0
    return Nivel(lufs, varf)


def _mix(
    voce: Path, durata: float, muzica: Path | None, nivel_db: float, atenuare: bool, iesire: Path
) -> None:
    v = f"[0:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:{durata:.3f}"
    if muzica is None:
        ffmpeg.ruleaza(["-i", str(voce), "-filter_complex", v + "[out]", "-map", "[out]", "-c:a", "pcm_s16le",
                        str(iesire)])  # fmt: skip
        return
    m = (f"[1:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{durata:.3f},"
         f"afade=t=out:st={max(0.0, durata - 1.0):.3f}:d=1,volume={nivel_db}dB")  # fmt: skip
    if atenuare:
        graf = (f"{v},asplit=2[v1][v2];{m}[m];[m][v2]sidechaincompress=threshold=0.015:ratio=12:attack=15:"
                f"release=350:makeup=1[md];[v1][md]amix=inputs=2:duration=first:"
                f"normalize=0[out]")  # fmt: skip
    else:
        graf = f"{v}[v1];{m}[md];[v1][md]amix=inputs=2:duration=first:normalize=0[out]"
    ffmpeg.ruleaza(["-i", str(voce), "-stream_loop", "-1", "-i", str(muzica), "-filter_complex", graf,
                    "-map", "[out]", "-t", f"{durata:.3f}", "-c:a", "pcm_s16le", str(iesire)])  # fmt: skip


def mixeaza(
    voce: Path, durata: float, *, muzica: Path | None = None, nivel_db: float = -16.0, atenuare: bool = True,
    director: Path,
) -> tuple[Path, Nivel]:  # fmt: skip
    """Pista finală (WAV 48 kHz stereo) adusă la țintă, cu nivelul măsurat."""
    brut, final = director / "mix_brut.wav", director / "mix.wav"
    _mix(voce, durata, muzica, nivel_db, atenuare, brut)
    n0 = masoara(brut)
    castig = TINTA_LUFS - n0.lufs
    sursa = brut
    for _ in range(2):
        filtru = f"volume={castig:.2f}dB,alimiter=limit={LIMITA_LINIARA}:level=0"
        ffmpeg.ruleaza(["-i", str(sursa), "-af", filtru,
                        "-c:a", "pcm_s16le", str(final)])  # fmt: skip
        n = masoara(final)
        if n.in_tinta:
            return final, n
        castig += TINTA_LUFS - n.lufs
    return final, n
