"""Subtitrările (F8.7, docs/14 §14.7): cuvânt cu cuvânt, 2–4 cuvinte pe ecran, cuvântul rostit evidențiat, în
zona sigură a platformei, cu fontul care are toate diacriticele. Se ard în imagine (ASS, libass); un SRT
separat
merge acolo unde platforma îl acceptă.

Fiecare ecran are cutia lui calculată (lățimea măsurată cu fontul real), așa că G6 poate verifica fără OCR
că nicio
subtitrare nu iese din zona sigură și niciun cuvânt nu e tăiat (OCR pe cadre: NEVERIFICAT, la migrare).
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from app.config import get_settings
from app.media import lista

PAUZA_ECRAN = 0.6  # [I] o pauză mai lungă de atât începe alt ecran
MAX_CUVINTE, MIN_CUVINTE = 4, 2
FONT_SUBTITRARI = "DejaVuSans-Bold.ttf"
NUME_FONT = "DejaVu Sans"
CONTUR = 4


@dataclass(frozen=True)
class Zona:
    """Marginile interzise textului, în pixeli, la 1080×1920 [I] (butoanele și descrierile aplicației)."""

    sus: int
    jos: int
    stanga: int
    dreapta: int

    def la(self, latime: int, inaltime: int) -> "Zona":
        fx, fy = latime / 1080, inaltime / 1920
        return Zona(
            round(self.sus * fy), round(self.jos * fy), round(self.stanga * fx), round(self.dreapta * fx)
        )


ZONE_SIGURE = {
    "tiktok": Zona(160, 480, 60, 150),
    "instagram": Zona(220, 420, 60, 120),
    "facebook": Zona(220, 420, 60, 120),
    "youtube": Zona(160, 380, 60, 140),
}


def zona(canal: str) -> Zona:
    return ZONE_SIGURE.get(canal, ZONE_SIGURE["tiktok"])


@dataclass(frozen=True)
class Ecran:
    cuvinte: tuple[lista.Text, ...]
    inceput: float
    sfarsit: float
    text: str
    cutie: tuple[int, int, int, int]  # x0, y0, x1, y1 în pixeli


def cale_font(nume: str = FONT_SUBTITRARI) -> Path:
    return Path(get_settings().media_fonturi) / nume


@lru_cache(maxsize=16)
def _font(marime: int) -> ImageFont.FreeTypeFont:
    """Fontul la mărimea folosită de libass: în ASS, `Fontsize` este înălțimea rândului (urcare +
    coborâre), nu
    em-ul, deci em = mărimea × 100 / (urcare + coborâre la 100)."""
    urcare, coborare = ImageFont.truetype(str(cale_font()), 100).getmetrics()
    return ImageFont.truetype(str(cale_font()), max(1, round(marime * 100 / (urcare + coborare))))


def latime_text(text: str, marime: int) -> int:
    return int(_font(marime).getlength(text)) + 2 * CONTUR


def _cutie(
    text: str, stil: lista.StilSubtitrari, z: Zona, latime: int, inaltime: int
) -> tuple[int, int, int, int]:
    w = latime_text(text, stil.marime)
    h = stil.marime + 2 * CONTUR
    x0 = z.stanga + (latime - z.stanga - z.dreapta - w) // 2
    y1 = inaltime - z.jos if stil.pozitie == "jos" else (inaltime + h) // 2
    return x0, y1 - h, x0 + w, y1


def grupeaza(lm: lista.ListaMontaj) -> list[Ecran]:
    """Cuvintele în ecrane de 2–4 (o frază nu se amestecă cu alta), cât încap pe lățimea zonei sigure."""
    z = zona(lm.canal).la(lm.latime, lm.inaltime)
    latime_max = lm.latime - z.stanga - z.dreapta
    grupe: list[list[lista.Text]] = []
    for t in lm.texte:
        g = grupe[-1] if grupe else None
        if (
            g is None
            or g[-1].fraza != t.fraza
            or len(g) >= MAX_CUVINTE
            or t.inceput - g[-1].sfarsit > PAUZA_ECRAN
            or latime_text(" ".join(x.cuvant for x in [*g, t]), lm.stil.marime) > latime_max
        ):
            grupe.append([t])
        else:
            g.append(t)
    # un cuvânt singur la capăt de frază trece la ecranul dinainte, dacă încape
    i = 1
    while i < len(grupe):
        g, prev = grupe[i], grupe[i - 1]
        unit = [*prev, *g]
        if (len(g) < MIN_CUVINTE and prev[-1].fraza == g[0].fraza and len(unit) <= MAX_CUVINTE
                and latime_text(" ".join(x.cuvant for x in unit), lm.stil.marime) <= latime_max):  # fmt: skip
            grupe[i - 1] = unit
            del grupe[i]
        else:
            i += 1
    out: list[Ecran] = []
    for k, g in enumerate(grupe):
        urm = grupe[k + 1][0].inceput if k + 1 < len(grupe) else lm.durata
        sfarsit = min(urm, g[-1].sfarsit + 0.4)
        text = " ".join(x.cuvant for x in g)
        out.append(Ecran(tuple(g), g[0].inceput, round(sfarsit, 3), text,
                         _cutie(text, lm.stil, z, lm.latime, lm.inaltime)))  # fmt: skip
    return out


def in_zona(e: Ecran, canal: str, latime: int, inaltime: int) -> bool:
    z = zona(canal).la(latime, inaltime)
    x0, y0, x1, y1 = e.cutie
    return x0 >= z.stanga and x1 <= latime - z.dreapta and y0 >= z.sus and y1 <= inaltime - z.jos


def _timp_ass(t: float) -> str:
    cs = round(t * 100)
    h, r = divmod(cs, 360000)
    m, r = divmod(r, 6000)
    s, c = divmod(r, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def _culoare_ass(hex_: str) -> str:
    r, g, b = hex_[1:3], hex_[3:5], hex_[5:7]
    return f"&H00{b}{g}{r}".upper()


def _scapa(t: str) -> str:
    return t.replace("\\", "").replace("{", "(").replace("}", ")")


def ass(lm: lista.ListaMontaj, ecrane: list[Ecran]) -> str:
    """Fișierul ASS: un eveniment pe cuvânt, cu tot ecranul afișat și cuvântul rostit în culoarea de
    evidențiere."""
    z = zona(lm.canal).la(lm.latime, lm.inaltime)
    st = lm.stil
    aliniere = 2 if st.pozitie == "jos" else 5
    rand_jos = z.jos if st.pozitie == "jos" else 0
    antet = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {lm.latime}", f"PlayResY: {lm.inaltime}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        f"Style: Sub,{NUME_FONT},{st.marime},{_culoare_ass(st.culoare)},{_culoare_ass(st.evidentiere)},"
        f"{_culoare_ass(st.contur)},&H00000000,-1,0,0,0,100,100,0,0,1,{CONTUR},0,{aliniere},"
        f"{z.stanga},{z.dreapta},{rand_jos},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]  # fmt: skip
    ev = _culoare_ass(st.evidentiere)
    linii = list(antet)
    for e in ecrane:
        for j, c in enumerate(e.cuvinte):
            t0 = e.inceput if j == 0 else c.inceput
            t1 = e.cuvinte[j + 1].inceput if j + 1 < len(e.cuvinte) else e.sfarsit
            parti = [
                f"{{\\c{ev}&}}{_scapa(x.cuvant)}{{\\r}}" if k == j else _scapa(x.cuvant)
                for k, x in enumerate(e.cuvinte)
            ]
            linii.append(f"Dialogue: 0,{_timp_ass(t0)},{_timp_ass(t1)},Sub,,0,0,0,,{' '.join(parti)}")
    return "\n".join(linii) + "\n"


def srt(ecrane: list[Ecran]) -> str:
    def ts(t: float) -> str:
        ms = round(t * 1000)
        h, r = divmod(ms, 3600000)
        m, r = divmod(r, 60000)
        s, r = divmod(r, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{r:03d}"

    return "\n".join(f"{i}\n{ts(e.inceput)} --> {ts(e.sfarsit)}\n{e.text}\n" for i, e in enumerate(ecrane, 1))
