"""Testul de capacitate (F8.9, docs/14 §14.11): timpul per video și memoria de vârf, față de buget.

Bugetele [I] pornesc de la ținta din 14.11 („un video de 45 de secunde gata în mai puțin de 10 minute”, la
două
culoare grele pe 8 nuclee): cel mult 600/45 ≈ 13,3 secunde de randare pentru fiecare secundă de video și
cel mult
1,5 GB de memorie rezidentă pe randare. Măsurătorile vin din `randari.masuratori` (timpul și `ru_maxrss` al
procesului ffmpeg, din `wait4`) și din momentele de început și sfârșit, pentru paralelismul real pe culoare.
"""

import datetime as dt
from dataclasses import dataclass

from app.media.modele import Randare

BUGET_SEC_PE_SEC_VIDEO = 600 / 45  # [I]
BUGET_MEMORIE_MB = 1536.0  # [I]


@dataclass(frozen=True)
class Raport:
    videouri: int
    sec_per_video_max: float
    sec_per_video_medie: float
    sec_pe_sec_video_max: float
    memorie_mb_max: float
    paralel_max: int
    durata_totala_sec: float

    @property
    def in_buget(self) -> bool:
        return self.sec_pe_sec_video_max <= BUGET_SEC_PE_SEC_VIDEO and self.memorie_mb_max <= BUGET_MEMORIE_MB

    def text(self) -> str:
        return (
            f"{self.videouri} video: max {self.sec_per_video_max:.1f} s / video "
            f"(medie {self.sec_per_video_medie:.1f} s), {self.sec_pe_sec_video_max:.2f} s de randare "
            f"pe secundă de video (buget {BUGET_SEC_PE_SEC_VIDEO:.1f}), "
            f"memorie max {self.memorie_mb_max:.0f} MB "
            f"(buget {BUGET_MEMORIE_MB:.0f}), {self.paralel_max} în paralel, "
            f"total {self.durata_totala_sec:.1f} s"
        )


def _paralel(intervale: list[tuple[dt.datetime, dt.datetime]]) -> int:
    evenimente = sorted([(a, 1) for a, _ in intervale] + [(b, -1) for _, b in intervale])
    curent = maxim = 0
    for _, d in evenimente:
        curent += d
        maxim = max(maxim, curent)
    return maxim


def raport(randari: list[Randare]) -> Raport:
    gata = [r for r in randari if r.masuratori.get("secunde")]
    if not gata:
        raise ValueError("nicio randare măsurată")
    sec = [float(r.masuratori["total_sec"]) for r in gata]
    pe_sec = [float(r.masuratori["total_sec"]) / float(r.masuratori["durata_video"]) for r in gata]
    intervale = [(dt.datetime.fromisoformat(r.masuratori["inceput_la"]), dt.datetime.fromisoformat(
        r.masuratori["sfarsit_la"])) for r in gata]  # fmt: skip
    return Raport(
        videouri=len(gata),
        sec_per_video_max=max(sec),
        sec_per_video_medie=sum(sec) / len(sec),
        sec_pe_sec_video_max=max(pe_sec),
        memorie_mb_max=max(float(r.masuratori["memorie_mb"]) for r in gata),
        paralel_max=_paralel(intervale),
        durata_totala_sec=(max(b for _, b in intervale) - min(a for a, _ in intervale)).total_seconds(),
    )
