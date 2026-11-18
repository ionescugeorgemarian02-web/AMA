"""Formatul C, grafică animată (F16.1, docs/14 §14.1, §14.6): scene animate în culorile brandului,
(din șabloane).

O scenă e date (`ScenaC`: tipul — ofertă, cifră, anunț —, titlul, valoarea, detaliul); fiecare frază
a narațiunii
are scena ei. Animația e deterministă (aceleași date -> același fișier): fundalul intră dinspre stânga, titlul
alunecă și apare, cifra numără până la valoare, banda de accent crește. Se randează LOCAL, pe CPU: cadrele cu
Pillow, clipul cu FFmpeg; apoi montajul obișnuit (subtitrări, voce, G6, pașaport), ca formatele A, B, E.

`html_scene` dă aceeași animație ca scenă HTML cu CSS (contractul pentru HyperFrames, motorul din §14.6).
# SIMULAT: HyperFrames nu e instalat; randarea locală Pillow + FFmpeg ține locul lui (D-026). La migrare se
compară cele două randări pe aceleași date.
"""

import html
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

from app.media import biblioteca, ffmpeg, licente, lista, montaj, regizor, sabloane, transcriere
from app.media.modele import Randare
from app.media.subtitrari import cale_font
from app.operare import urme

TIPURI_C = ("oferta", "cifra", "anunt")
CPS = 15  # [I] cadre pe secundă desenate; FFmpeg le duce la 30
LATIME, INALTIME = 540, 960  # [I] desenat la jumătate, scalat la 1080×1920
INTRARE = 0.6  # [I] secunde de animație de intrare pe scenă
COADA = 0.8  # [I] secunde după ultimul cuvânt


@dataclass(frozen=True)
class ScenaC:
    tip: Literal["oferta", "cifra", "anunt"]
    titlu: str
    valoare: str = ""  # „-20%”, „1200”, „49 lei”; la `cifra`, partea numerică numără
    detaliu: str = ""


class ScenaInvalida(ValueError):
    pass


def probleme_scene(scene: list[ScenaC], fraze: list[str]) -> list[str]:
    """Nucleu pur: o scenă pe frază, tipuri cunoscute, texte care încap în șablon."""
    out = []
    if not scene or len(scene) != len(fraze):
        out.append(f"{len(scene)} scene pentru {len(fraze)} fraze: trebuie una pe frază")
    for i, s in enumerate(scene):
        if s.tip not in TIPURI_C:
            out.append(f"scena {i}: tip necunoscut {s.tip!r}")
        if not 1 <= len(s.titlu) <= 40:
            out.append(f"scena {i}: titlul are {len(s.titlu)} caractere (1–40)")
        if len(s.valoare) > 12 or len(s.detaliu) > 60:
            out.append(f"scena {i}: valoarea (≤12) sau detaliul (≤60) e prea lung")
        if s.tip == "cifra" and not any(c.isdigit() for c in s.valoare):
            out.append(f"scena {i}: scena de tip cifră cere o valoare numerică")
    return out


def _usor(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def valoare_la(valoare: str, p: float) -> str:
    """Nucleu pur: cifra numără de la 0 la valoare (păstrează prefixul și sufixul: „-20%”, „49 lei”)."""
    cifre = [i for i, c in enumerate(valoare) if c.isdigit()]
    if not cifre:
        return valoare
    a, b = cifre[0], cifre[-1] + 1
    n = int(valoare[a:b].replace(".", "") or 0) if valoare[a:b].replace(".", "").isdigit() else 0
    if not n:
        return valoare
    return f"{valoare[:a]}{round(n * _usor(p))}{valoare[b:]}"


def _font(marime: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(cale_font("DejaVuSans-Bold.ttf")), marime)


def cadru(
    s: ScenaC, t: float, culori: dict[str, str], latime: int = LATIME, inaltime: int = INALTIME
) -> Image.Image:
    """Nucleu pur: imaginea scenei la momentul `t` (secunde de la începutul ei)."""
    p = _usor(t / INTRARE)
    img = Image.new("RGB", (latime, inaltime), culori["fundal"])
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, round(latime * p), inaltime), fill=culori["primara"])  # fundalul intră
    cx = latime / 2 - (1 - p) * latime * 0.3
    d.text((cx, inaltime * 0.36), s.titlu, font=_font(44), fill=culori["alb"], anchor="mm")
    if s.valoare:
        v = valoare_la(s.valoare, t / (INTRARE * 2)) if s.tip == "cifra" else s.valoare
        d.text((latime / 2, inaltime * 0.5), v, font=_font(110 if s.tip != "anunt" else 72),
               fill=culori["accent"], anchor="mm")  # fmt: skip
    banda = round(latime * 0.7 * _usor((t - INTRARE / 2) / INTRARE))
    if banda > 0:
        y = round(inaltime * 0.6)
        d.rectangle(
            (round((latime - banda) / 2), y, round((latime + banda) / 2), y + 10), fill=culori["accent"]
        )
    if s.detaliu:
        d.text((latime / 2, inaltime * 0.66), s.detaliu, font=_font(26), fill=culori["alb"], anchor="mm")
    return img


def html_scene(scene: list[ScenaC], durate: list[float], culori: dict[str, str]) -> str:
    """Aceleași scene ca HTML cu CSS (contractul motorului HyperFrames, §14.6). Textele sunt escapate."""
    c = {k: html.escape(v) for k, v in culori.items()}
    parti = []
    inceput = 0.0
    for s, dur in zip(scene, durate, strict=True):
        parti.append(
            f'<section class="scena {s.tip}" data-start="{inceput:.3f}" data-durata="{dur:.3f}">'
            f"<h1>{html.escape(s.titlu)}</h1><strong>{html.escape(s.valoare)}</strong>"
            f"<p>{html.escape(s.detaliu)}</p></section>"
        )
        inceput += dur
    stil = (
        f".scena{{background:{c['primara']};color:{c['alb']};animation:intra {INTRARE}s ease-out both}}"
        f"strong{{color:{c['accent']}}}@keyframes intra{{from{{transform:translateX(-30%);opacity:0}}}}"
    )
    return f'<!doctype html><meta charset="utf-8"><style>{stil}</style>{"".join(parti)}'


def randeaza_clip(scene: list[ScenaC], durate: list[float], culori: dict[str, str], d: Path) -> Path:
    """Cadrele (Pillow) -> clip H.264 1080×1920, 30 fps, yuv420p (FFmpeg). Local, fără rețea."""
    k = 0
    for s, dur in zip(scene, durate, strict=True):
        for i in range(max(1, round(dur * CPS))):
            cadru(s, i / CPS, culori).save(d / f"c{k:05d}.png", compress_level=1)
            k += 1
    iesire = d / "format-c.mp4"
    ffmpeg.ruleaza(
        ["-framerate", str(CPS), "-i", str(d / "c%05d.png"), "-vf", "scale=1080:1920:flags=lanczos",
         "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-an", str(iesire)]
    )  # fmt: skip
    return iesire


def proceseaza(
    db: Session,
    tenant_id: uuid.UUID,
    scene: list[ScenaC],
    fraze: list[str],
    *,
    nume_brand: str,
    canal: str = "tiktok",
    profil_voce: str | None = None,
) -> Randare:
    """Scenele + frazele -> video publicabil format C (randare `gata` sau `respinsa`, cu G6 și pașaportul)."""
    pr = probleme_scene(scene, fraze)
    if pr:
        raise ScenaInvalida("; ".join(pr))
    with urme.span("media", "formatul_c", obiect_tip="randare", intrari={"scene": len(scene)}) as sp:
        ident, _ = sabloane.identitate(db, tenant_id, nume_brand)
        culori = dict(ident["culori"])
        v = transcriere.naratiune_verificata(db, tenant_id, fraze, profil_cod=profil_voce)
        n = v.naratiune
        durata = round(n.durata + COADA, 3)
        margini = [f.inceput for f in n.fraze[1:]] + [durata]
        durate, t0 = [], 0.0
        for m in margini:
            durate.append(round(m - t0, 3))
            t0 = m
        with tempfile.TemporaryDirectory() as tmp:
            clip = randeaza_clip(scene, durate, culori, Path(tmp))
            activ = biblioteca.incarca(
                db,
                tenant_id,
                clip.read_bytes(),
                nume_original="format-c.mp4",
                sursa="format_c",
                utilizator_id=None,
                descriere="grafică animată din șabloane, în culorile brandului",
                licenta={
                    "tip": "productie_proprie",
                    "statut": licente.STATUT_OK,
                    "componente": [{"sablon": f"format_c/{s.tip}", "identitate": nume_brand} for s in scene],
                },
                generare={
                    "format": "C",
                    "motor": "local_pillow_ffmpeg",
                    "scene": [s.__dict__ for s in scene],
                },
            )
        durata = round(min(durata, ffmpeg.durata(regizor.cale(activ))), 3)
        lm = lista.ListaMontaj(
            format="C",
            canal=canal,
            durata=durata,
            voce=lista.Pista(activ_id=n.activ.id, durata=n.durata),
            scene=[lista.Scena(activ_id=activ.id, inceput=0, sfarsit=durata, bataie=0)],
            texte=regizor.texte(fraze, v.aliniere),
        )
        r = montaj.produ(db, tenant_id, lm)
        extra: dict[str, Any] = {"scene_c": len(scene), "html_c": len(html_scene(scene, durate, culori))}
        r.masuratori = {**(r.masuratori or {}), **extra}
        sp.iesiri, sp.rezultat = {"stare": r.stare}, "ok" if r.stare == "gata" else "respins"
        return r
