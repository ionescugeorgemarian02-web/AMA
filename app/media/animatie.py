"""Clipuri animate în identitatea brandului (grafică în mișcare, randată în Chromium).

Când nu există filmări (stock sau ale clientului), fiecare bătaie a scriptului primește un clip propriu:
fundal în culorile brandului, iconița potrivită subiectului, textul de pe ecran animat cuvânt cu cuvânt.
Pagina HTML din `animatie_active/randeaza.mjs` e „înghețată” cadru cu cadru (Playwright), apoi FFmpeg
codează H.264. Determinist: aceleași date dau același fișier. Componente cu licență deschisă, păstrate în
repo: fontul Montserrat (SIL OFL) și iconițele Lucide (ISC). Textul ocupă zona de sus: subtitrările stau jos.

    animatie.disponibil()                                      # node + Playwright + FFmpeg
    animatie.clip(db, tenant_id, "Prăjim marțea", durata=5.0, varianta=1)
    animatie.clipuri_script(db, tenant_id, campuri, durate)    # câte un clip pe bătaie
"""

import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.media import biblioteca, ffmpeg, licente
from app.media.modele import Activ

ACTIVE = Path(__file__).parent / "animatie_active"
FPS = 30
CULORI_IMPLICITE = {"fundal": "#2B1810", "fundal2": "#6B3E26", "accent": "#D9822B", "text": "#F7EDE2"}
# cuvânt-cheie (fără diacritice, prefix) -> iconiță; primul găsit câștigă
ICONITE: tuple[tuple[str, str], ...] = (
    ("prajit", "flame"), ("prajim", "flame"), ("boab", "bean"), ("macin", "bean"), ("lei", "shopping-bag"),
    ("pret", "shopping-bag"), ("comand", "shopping-bag"), ("cumpar", "shopping-bag"), ("livr", "truck"),
    ("acasa", "truck"), ("curier", "truck"), ("proaspat", "leaf"), ("arom", "sparkles"), ("gust", "sparkles"),
    ("note", "sparkles"), ("minut", "timer"), ("ora", "clock"), ("zile", "calendar"), ("sambata", "calendar"),
    ("duminica", "calendar"), ("degust", "calendar"), ("marti", "calendar"), ("apa", "droplet"),
    ("temperatur", "thermometer"), ("cadou", "gift"), ("magazin", "store"), ("cafenea", "store"),
    ("adresa", "map-pin"), ("brasov", "map-pin"), ("fermier", "hand-heart"), ("iubi", "heart"),
    ("calitat", "star"), ("pachet", "package"), ("cafe", "coffee"), ("espresso", "coffee"),
    ("filtru", "coffee"), ("program", "calendar"), ("revizi", "calendar"),
)  # fmt: skip


def _fara_diacritice(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def comparatie_macinare(titlu: str, indicatie: str) -> bool:
    text = _fara_diacritice(f"{titlu} {indicatie}")
    return "macin" in text and any(c in text for c in ("cafe", "filtru", "fin", "medie"))


def iconita(text: str) -> str:
    cuvinte = _fara_diacritice(text).split()
    for cheie, nume in ICONITE:
        if any(c.strip(".,;:!?„”\"'()").startswith(cheie) for c in cuvinte):
            return nume
    return "sparkles"


def _binar(nume: str) -> str:
    cale = shutil.which(nume)
    if cale is None:
        raise RuntimeError(f"{nume} nu este instalat")
    return cale


def disponibil() -> bool:
    if shutil.which("node") is None or not ffmpeg.disponibil():
        return False
    r = subprocess.run(
        [_binar("node"), "-e", "require.resolve(process.env.AMA_PLAYWRIGHT || 'playwright')"],
        capture_output=True,
        timeout=30,
    )
    return r.returncode == 0


def randeaza(
    titlu: str,
    *,
    durata: float,
    varianta: int = 0,
    indicatie: str = "",
    samanta: int = 0,
    eticheta: str = "",
    culori: dict[str, str] | None = None,
    latime: int = 1080,
    inaltime: int = 1920,
) -> bytes:
    """MP4-ul (H.264, fără sunet) al unui clip. Ridică `RuntimeError` dacă randarea pică."""
    with tempfile.TemporaryDirectory() as d:
        cadre = Path(d) / "cadre"
        cadre.mkdir()
        simbol = iconita(f"{titlu} {indicatie}")
        svg = (ACTIVE / "iconite" / f"{simbol}.svg").read_text()
        paleta = CULORI_IMPLICITE if culori is None else culori
        if not all(re.fullmatch(r"#[0-9A-Fa-f]{6}", paleta.get(rol, "")) for rol in CULORI_IMPLICITE):
            raise ValueError("Paleta animației cere patru culori hexazecimale.")
        intrare = {
            "latime": latime, "inaltime": inaltime, "fps": FPS, "durata": durata, "titlu": titlu.strip(),
            "eticheta": eticheta, "icon": svg,
            "particula": svg, "culori": {rol: paleta[rol] for rol in CULORI_IMPLICITE},
            "fonturi": str(ACTIVE / "fonturi"), "varianta": varianta, "samanta": samanta,
            "iesire": str(cadre), "comparatie_macinare": comparatie_macinare(titlu, indicatie),
        }  # fmt: skip
        r = subprocess.run(
            [_binar("node"), str(ACTIVE / "randeaza.mjs")],
            input=json.dumps(intrare).encode(),
            capture_output=True,
            timeout=600,
        )
        if r.returncode != 0:
            raise RuntimeError("randarea animației a eșuat: " + r.stderr.decode(errors="replace")[-300:])
        iesire = Path(d) / "clip.mp4"
        subprocess.run(
            [_binar("ffmpeg"), "-v", "error", "-y", "-framerate", str(FPS), "-i", str(cadre / "f%05d.jpg"),
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", str(iesire)],
            check=True, capture_output=True, timeout=600,
        )  # fmt: skip
        return iesire.read_bytes()


def clip(
    db: Session,
    tenant_id: uuid.UUID,
    titlu: str,
    *,
    durata: float,
    varianta: int = 0,
    indicatie: str = "",
    eticheta: str = "",
    culori: dict[str, str] | None = None,
) -> Activ:
    """Randează și înregistrează clipul (categoria `video`, licență `productie_proprie`)."""
    corp = randeaza(
        titlu,
        durata=durata,
        varianta=varianta,
        indicatie=indicatie,
        samanta=varianta + 1,
        eticheta=eticheta,
        culori=culori,
    )
    return biblioteca.incarca(
        db,
        tenant_id,
        corp,
        nume_original="animatie.mp4",
        sursa="animatie",
        rol_vizual="ilustratie",
        utilizator_id=None,
        descriere=f"grafică animată: {titlu.strip()[:200]}",
        licenta={
            "tip": "productie_proprie",
            "statut": licente.STATUT_OK,
            "componente": [
                {"font": "Montserrat", "licenta": "SIL Open Font License 1.1"},
                {"iconita": iconita(f"{titlu} {indicatie}"), "set": "Lucide", "licenta": "ISC"},
                {"randator": "animatie_interna", "identitate": eticheta},
            ],
        },
        generare={
            "motor": "chromium_playwright_ffmpeg",
            "titlu": titlu,
            "varianta": varianta,
            "durata": durata,
        },
    )


MAX_CUVINTE_ECRAN = 6  # [I] F-editorial: textul de pe ecran e scurt; vocea spune restul


def scurt(text: str, n: int = MAX_CUVINTE_ECRAN) -> str:
    """Cel mult `n` cuvinte pe ecran (cu „…” când textul e tăiat)."""
    c = text.split()
    return text.strip() if len(c) <= n else " ".join(c[:n]).rstrip(",;:") + "…"


def texte_batai(campuri: dict[str, Any]) -> list[str]:
    """Textul de pe ecran al fiecărei bătăi, în ordinea frazelor regizorului: hook, bătăile, CTA."""
    batai = campuri.get("batai") or []
    out = [str(campuri.get("hook") or "")]
    out += [scurt(str(b.get("text_ecran") or b.get("voce") or "")) for b in batai]
    out.append(str(campuri.get("cta") or ""))
    return [t for t in out if t.strip()]


def clipuri_script(
    db: Session,
    tenant_id: uuid.UUID,
    campuri: dict[str, Any],
    durate: list[float],
    *,
    eticheta: str = "",
    culori: dict[str, str] | None = None,
) -> list[Activ]:
    """Un clip pe bătaie, puțin mai lung decât bătaia (montajul taie)."""
    texte = texte_batai(campuri)
    indicatii = (
        ([""] if campuri.get("hook") else [])
        + [str(b.get("vizual", "")) for b in campuri.get("batai", []) if b.get("text_ecran") or b.get("voce")]
        + ([""] if campuri.get("cta") else [])
    )

    return [
        clip(
            db,
            tenant_id,
            t,
            durata=round(max(d, 1.0) + 1.0, 2),
            varianta=i,
            indicatie=indicatii[i],
            eticheta=eticheta,
            culori=culori,
        )
        for i, (t, d) in enumerate(zip(texte, durate, strict=False))
    ]


def clipuri_scene(
    db: Session,
    tenant_id: uuid.UUID,
    campuri: dict[str, Any],
    durate: dict[int, float],
    *,
    eticheta: str = "",
    culori: dict[str, str] | None = None,
) -> dict[int, Activ]:
    """Clipurile doar pentru scenele cerute (F-editorial: ilustrația unei scene educative fără material)."""
    texte = texte_batai(campuri)
    indicatii = (
        ([""] if campuri.get("hook") else [])
        + [str(b.get("vizual", "")) for b in campuri.get("batai", []) if b.get("text_ecran") or b.get("voce")]
        + ([""] if campuri.get("cta") else [])
    )
    return {
        i: clip(
            db,
            tenant_id,
            texte[i],
            durata=round(max(d, 1.0) + 1.0, 2),
            varianta=i,
            indicatie=indicatii[i] if i < len(indicatii) else "",
            eticheta=eticheta,
            culori=culori,
        )
        for i, d in sorted(durate.items())
        if i < len(texte)
    }
