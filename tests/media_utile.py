"""Ajutoare pentru testele media (F8): scriptul de probă al brandului FICTIV „Cafeneaua Zorilor”, regizorul
FALS
(# SIMULAT) și pregătirea materialelor licențiate."""

import json
import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.media import furnizori, normalizare, transcriere
from app.media.modele import Activ
from tests.furnizor_fals import CerereInregistrata
from tests.onboarding_utile import ModelFals, prompt_complet

SCRIPT: dict[str, Any] = {
    "hook": "Știi de ce cafeaua ta e amară?",
    "batai": [
        {"voce": "Boabele prăjite acum trei luni își pierd aroma.", "text_ecran": "Prăjire veche", "vizual": "boabe"},
        {"voce": "Noi prăjim în fiecare marți, în loturi mici, la Brașov.", "text_ecran": "Prăjim marțea",
         "vizual": "prăjitorie"},
        {"voce": "Etiopia Guji costă 49 lei și are note de afine.", "text_ecran": "Etiopia Guji",
         "vizual": "pachet"},
    ],
    "cta": "Comandă azi de pe site.",
}  # fmt: skip


def fraze(script: dict[str, Any] | None = None) -> list[str]:
    from app.media import regizor

    return [normalizare.normalizeaza(f) for f in regizor.fraze_din_script(script or SCRIPT)]


class RegizorFals:
    """Alege materialul `bataie % n` și alternează mișcările. `strica`: întoarce un material inexistent."""

    def __init__(self, strica: bool = False) -> None:
        self.strica = strica
        self.cereri = 0

    def __call__(self, c: CerereInregistrata) -> str:
        self.cereri += 1
        p = prompt_complet(c)
        batai = re.findall(r"^(\d+)\. ", p.split("Materiale disponibile")[0], re.M)
        n = len(re.findall(r"^\d+: ", p.split("Materiale disponibile")[1], re.M))
        miscari = ["zoom_in", "panoramare_dreapta", "zoom_out", "panoramare_stanga", "static"]
        scene = [{"bataie": int(b), "material": (99 if self.strica else int(b) % n),
                  "miscare": miscari[int(b) % len(miscari)]} for b in batai]  # fmt: skip
        return json.dumps(
            {"scene": scene, "coperta": "Cafea proaspătă", "dovezi": ["scriptat"], "incredere": 0.9}
        )


def model_regizor(modele: ModelFals, **kw: Any) -> RegizorFals:
    r = RegizorFals(**kw)
    modele.handlere["Ești regizorul video"] = r
    return r


def materiale(db: Session, tenant_id: uuid.UUID, tip: str = "video", n: int = 4) -> list[Activ]:
    rez = furnizori.cauta_stock("cafea de specialitate", tip=tip, n=n)
    return [furnizori.aduce_stock(db, tenant_id, r) for r in rez]


def naratiune(
    db: Session, tenant_id: uuid.UUID, script: dict[str, Any] | None = None
) -> transcriere.NaratiuneVerificata:
    return transcriere.naratiune_verificata(db, tenant_id, fraze(script))


def lista_simpla(db: Session, tenant_id: uuid.UUID, format: str = "A", **kw: Any) -> Any:
    """O listă construită determinist (fără model): rotația materialelor, mișcări alternate."""
    from app.media import regizor

    mat = materiale(db, tenant_id, "video" if format == "A" else "foto", 3)
    script = kw.pop("script", None)
    nv = naratiune(db, tenant_id, script)
    fr = fraze(script)
    miscari = ["zoom_in", "panoramare_dreapta", "zoom_out", "panoramare_stanga", "static"]
    alegeri = [regizor.AlegereScena(bataie=i, material=i % len(mat), miscare=miscari[i % 5])  # type: ignore[arg-type]
               for i in range(len(fr))]  # fmt: skip
    return regizor.construieste(format=format, canal="tiktok", fraze=fr, naratiune=nv, materiale=mat,
                                alegeri=alegeri, **kw)  # fmt: skip


SCRIPT_E: dict[str, Any] = {
    "hook": "Bună, sunt Ioana de la Cafeneaua Zorilor din Brașov.",
    "batai": [
        {"voce": "Vreau să-ți arăt cum alegem boabele pentru fiecare lot.", "text_ecran": "", "vizual": "eu"},
        {"voce": "Lucrăm direct cu ferme mici din Etiopia, Columbia și Guatemala.", "text_ecran": "", "vizual": "eu"},
        {"voce": "Gustăm fiecare lot înainte să-l cumpărăm, de mai multe ori.", "text_ecran": "", "vizual": "eu"},
        {"voce": "Apoi prăjim în loturi mici, în fiecare marți dimineața.", "text_ecran": "", "vizual": "eu"},
        {"voce": "Cafeaua ajunge la tine în cel mult zece zile de la prăjire.", "text_ecran": "", "vizual": "eu"},
        {"voce": "Așa își păstrează aroma de afine, miere și ciocolată.", "text_ecran": "", "vizual": "eu"},
    ],
    "cta": "Te așteptăm la degustarea gratuită din prima sâmbătă a lunii.",
}  # fmt: skip


def filmare_bruta(director: Any, fr: list[str], *, minim: float = 58.0) -> tuple[bytes, float]:
    """# SIMULAT: „filmarea” clientului: imagine în mișcare + vocea (simulată) cu pauze lungi de gândire."""
    from pathlib import Path

    from app.media import audio, ffmpeg, voce

    m = voce.MotorVoceSimulat()
    p = voce.profil()
    es = audio.liniste(voce.RATA_SIMULAT, 1.5)
    pauze = [3.5, 4.2, 3.8, 4.5, 3.6, 4.0, 4.4, 3.9]  # clientul se uită pe prompter, ezită, reia
    for k, f in enumerate(fr):
        es.extend(m.sintetizeaza(f, p).esantioane)
        es.extend(audio.liniste(voce.RATA_SIMULAT, pauze[k % len(pauze)]))
    if len(es) / voce.RATA_SIMULAT < minim:
        es.extend(audio.liniste(voce.RATA_SIMULAT, minim - len(es) / voce.RATA_SIMULAT))
    durata = len(es) / voce.RATA_SIMULAT
    d = Path(director)
    (d / "v.wav").write_bytes(audio.scrie(audio.Wav(voce.RATA_SIMULAT, es)))
    ffmpeg.ruleaza(["-f", "lavfi", "-i", f"testsrc2=s=720x1280:r=30:d={durata:.2f}", "-i", str(d / "v.wav"),
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "38", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-ar", "48000", "-shortest", str(d / "brut.mp4")], fir=4)  # fmt: skip
    return (d / "brut.mp4").read_bytes(), durata


def fotografie_procedurala(
    latime: int = 1600, inaltime: int = 1200, *, subiect: tuple[float, float] = (0.55, 0.62), samanta: int = 7
) -> bytes:
    """O „fotografie” de test (F-editorial): cer neted sus, podea cu zgomot fin, iar subiectul (un pinion cu
    lanț, mult contrast) în jurul punctului relativ `subiect`. Deterministă."""
    import io
    import math
    import random

    from PIL import Image, ImageDraw, ImageFilter

    rnd = random.Random(samanta)  # noqa: S311 (zgomot de test, determinist)
    img = Image.new("RGB", (latime, inaltime))
    d = ImageDraw.Draw(img)
    for y in range(inaltime):  # gradient: cer sus, atelier jos
        t = y / inaltime
        d.line((0, y, latime, y), fill=(round(150 - 90 * t), round(170 - 100 * t), round(190 - 120 * t)))
    for _ in range(1800):  # podeaua: zgomot fin, mai liniștit decât subiectul
        x, y = rnd.randrange(latime), rnd.randrange(inaltime // 2, inaltime)
        g = rnd.randrange(40, 90)
        d.point((x, y), fill=(g, g, g))
    cx, cy = subiect[0] * latime, subiect[1] * inaltime
    r = min(latime, inaltime) * 0.16
    for k in range(24):  # dinții pinionului
        u = 2 * math.pi * k / 24
        d.polygon([(cx + (r + 26) * math.cos(u + s), cy + (r + 26) * math.sin(u + s)) for s in (-0.08, 0.08)]
                  + [(cx + r * math.cos(u + s), cy + r * math.sin(u + s)) for s in (0.1, -0.1)],
                  fill=(225, 205, 120))  # fmt: skip
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(200, 180, 90), outline=(20, 20, 20), width=8)
    d.ellipse((cx - r * 0.35, cy - r * 0.35, cx + r * 0.35, cy + r * 0.35), fill=(30, 30, 30))
    for k in range(14):  # lanțul, spre stânga jos
        x0, y0 = cx - r - 40 - k * 34, cy + r * 0.4 + k * 9
        d.rounded_rectangle((x0, y0, x0 + 30, y0 + 18), radius=6, outline=(15, 15, 15), width=5)
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=92)
    return out.getvalue()
