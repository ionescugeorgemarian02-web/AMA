"""Identitatea vizuală și șabloanele grafice (F8.10, docs/14 §14.10, docs/10 „Identitate vizuală”).

- Identitatea se citește din Creier (compartimentul „Identitate vizuală”, cheia `identitate`): versiunea
aprobată
  sau, până la aprobare, propunerea. Unde lipsește, se PROPUNE una deterministă din numele brandului
  (nuanța din
  nume, contrastele verificate: text pe fundal ≥ 7:1, principala pe fundal ≥ 5:1) și un logo din inițiale;
  propunerea așteaptă aprobarea clientului în Creier.
- Fiecare brand are șase șabloane (`TIPURI`): citat, ofertă, sfat, rezultat, anunț, copertă video. Un șablon e
  date (zone de text cu rol, mărime maximă și culoare, zona logoului, zona de fotografie), versionat în
  `sabloane_grafice`; Compozitorul (`compozitor`) îl completează cu textul aprobat.
"""

import colorsys
import hashlib
import io
import uuid
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import creier
from app.media import biblioteca, licente, vizual
from app.media.modele import Activ, SablonGrafic
from app.media.subtitrari import cale_font

CHEIE = "identitate"
TIPURI = ("citat", "oferta", "sfat", "rezultat", "anunt", "coperta_video")
DIACRITICE = "ăâîșțĂÂÎȘȚ"


def _hex(r: float, g: float, b: float) -> str:
    return f"#{round(r * 255):02X}{round(g * 255):02X}{round(b * 255):02X}"


def _hls(h: float, lum: float, sat: float) -> str:
    return _hex(*colorsys.hls_to_rgb(h % 1.0, lum, sat))


def propune_identitate(nume: str) -> dict[str, Any]:
    """Nucleu pur: o identitate din nume, cu contrastele verificate."""
    h = int(hashlib.sha256(nume.encode()).hexdigest()[:6], 16) / 0xFFFFFF
    lum = 0.34
    fundal = _hls(h, 0.96, 0.25)
    primara = _hls(h, lum, 0.55)
    while vizual.contrast(vizual.rgb(primara), vizual.rgb(fundal)) < 5.0 and lum > 0.05:  # [I] cu marjă
        lum -= 0.02
        primara = _hls(h, lum, 0.55)
    culori = {
        "primara": primara,
        "secundara": _hls(h, 0.86, 0.35),
        "fundal": fundal,
        "text": _hls(h, 0.12, 0.2),
        "accent": _hls(h + 0.42, 0.5, 0.7),
        "alb": "#FFFFFF",
    }
    assert vizual.contrast(vizual.rgb(culori["text"]), vizual.rgb(culori["fundal"])) >= 7  # noqa: S101
    initiale = "".join(p[0] for p in nume.split()[:2]).upper() or "A"
    return {"nume": nume, "culori": culori, "font": "DejaVuSans", "initiale": initiale, "propusa_de": "F8.10"}


def logo(identitate: dict[str, Any], marime: int = 240) -> bytes:
    """Logoul propus: inițialele, albe, într-un cerc în culoarea principală (PNG, fundal transparent)."""
    img = Image.new("RGBA", (marime, marime), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, marime - 1, marime - 1), fill=identitate["culori"]["primara"])
    f = ImageFont.truetype(str(cale_font("DejaVuSans-Bold.ttf")), marime // 3)
    d.text((marime / 2, marime / 2), identitate["initiale"], font=f, fill="#FFFFFF", anchor="mm")
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def identitate(db: Session, tenant_id: uuid.UUID, nume_brand: str) -> tuple[dict[str, Any], bool]:
    """(identitatea, `propusa_acum`). Aprobată > propunere existentă > propunere nouă (în Creier)."""
    intr = creier.gaseste_intrare(
        db, tenant_id=tenant_id, compartiment=creier.Compartiment.IDENTITATE_VIZUALA, cheie=CHEIE
    )
    if intr is not None:
        v = creier.versiune_aprobata(db, intr.id) or creier.istoric(db, intr.id)[-1]
        return dict(v.continut), False
    ident = propune_identitate(nume_brand)
    creier.creeaza_intrare(
        db,
        tenant_id=tenant_id,
        compartiment=creier.Compartiment.IDENTITATE_VIZUALA,
        cheie=CHEIE,
        continut=ident,
        sursa=creier.Sursa(creier.SursaTip.SISTEM),
        motiv="identitate vizuală propusă (lipsea); așteaptă aprobarea clientului",
    )
    return ident, True


# --- șabloanele: date, nu cod

Zona = dict[str, Any]


def _sablon(tip: str) -> dict[str, Any]:
    """Definiția unui tip de șablon (1080×1350 pentru feed, 1080×1920 pentru copertă). Cutii în pixeli."""
    if tip == "coperta_video":
        return {
            "latime": 1080, "inaltime": 1920, "fundal": "primara",
            "margini": [160, 480, 60, 150],
            "foto": [0, 0, 1080, 1920],
            "voal": "primara",
            "banda": {"cutie": [60, 640, 1020, 660], "culoare": "accent"},
            "texte": [{"rol": "titlu", "cutie": [80, 700, 920, 1240], "marime": 104, "culoare": "alb"}],
            "logo": [80, 200, 240, 360],
        }  # fmt: skip
    baza: dict[str, Any] = {
        "latime": 1080, "inaltime": 1350, "fundal": "fundal", "margini": [60, 60, 60, 60],
        "logo": [880, 1150, 1020, 1290],
    }  # fmt: skip
    texte = {
        "citat": [
            {"rol": "titlu", "cutie": [100, 260, 980, 860], "marime": 78, "culoare": "text"},
            {"rol": "semnatura", "cutie": [100, 900, 820, 1000], "marime": 44, "culoare": "primara"},
        ],
        "oferta": [
            {"rol": "titlu", "cutie": [100, 120, 980, 420], "marime": 84, "culoare": "text"},
            {"rol": "pret", "cutie": [100, 1020, 820, 1140], "marime": 76, "culoare": "primara"},
            {"rol": "corp", "cutie": [100, 1150, 820, 1290], "marime": 40, "culoare": "text"},
        ],
        "sfat": [
            {"rol": "eticheta", "cutie": [100, 120, 600, 200], "marime": 44, "culoare": "primara"},
            {"rol": "titlu", "cutie": [100, 240, 980, 700], "marime": 80, "culoare": "text"},
            {"rol": "corp", "cutie": [100, 740, 980, 1120], "marime": 46, "culoare": "text"},
        ],
        "rezultat": [
            {"rol": "cifra", "cutie": [100, 160, 980, 460], "marime": 160, "culoare": "primara"},
            {"rol": "titlu", "cutie": [100, 500, 980, 900], "marime": 70, "culoare": "text"},
            {"rol": "corp", "cutie": [100, 940, 820, 1120], "marime": 42, "culoare": "text"},
        ],
        "anunt": [
            {"rol": "eticheta", "cutie": [100, 120, 700, 200], "marime": 44, "culoare": "accent_text"},
            {"rol": "titlu", "cutie": [100, 260, 980, 760], "marime": 90, "culoare": "text"},
            {"rol": "corp", "cutie": [100, 800, 980, 1100], "marime": 48, "culoare": "text"},
        ],
    }[tip]
    baza["texte"] = texte
    if tip == "oferta":
        baza["foto"] = [100, 460, 980, 980]
    if tip in ("sfat", "anunt"):
        baza["banda"] = {"cutie": [60, 60, 1020, 84], "culoare": "primara"}
    return baza


def asigura_sabloane(db: Session, tenant_id: uuid.UUID, nume_brand: str) -> list[SablonGrafic]:
    """Cele șase șabloane ale brandului (create la prima cerere, cu identitatea curentă)."""
    ident, _ = identitate(db, tenant_id, nume_brand)
    existente = {
        s.tip: s
        for s in db.execute(select(SablonGrafic).where(SablonGrafic.tenant_id == tenant_id)).scalars()
    }
    logo_activ = _logo_activ(db, tenant_id, ident)
    out = []
    for tip in TIPURI:
        s = existente.get(tip)
        if s is None:
            definitie = {**_sablon(tip), "identitate": ident, "logo_activ": str(logo_activ.id)}
            s = SablonGrafic(tenant_id=tenant_id, tip=tip, versiune=1, definitie=definitie)
            db.add(s)
            db.flush()
        out.append(s)
    return out


def _logo_activ(db: Session, tenant_id: uuid.UUID, ident: dict[str, Any]) -> Activ:
    return biblioteca.incarca(
        db, tenant_id, logo(ident), nume_original="logo.png", sursa="identitate", utilizator_id=None,
        descriere=f"logo propus pentru {ident['nume']}",
        licenta={"tip": "productie_proprie", "statut": licente.STATUT_OK,
                 "componente": [{"descriere": "logo propus din inițialele brandului (F8.10)"}]},
    )  # fmt: skip


def are_glif(caracter: str, marime: int = 64, font: str = "DejaVuSans-Bold.ttf") -> bool:
    """Fontul desenează caracterul (nu cade pe glifa de rezervă `.notdef`)."""
    f = ImageFont.truetype(str(cale_font(font)), marime)

    def deseneaza(c: str) -> bytes:
        img = Image.new("L", (marime * 2, marime * 2))
        ImageDraw.Draw(img).text((marime // 2, marime // 2), c, font=f, fill=255)
        return img.tobytes()

    return deseneaza(caracter) != deseneaza(chr(0xE000))  # U+E000: zonă privată, sigur fără glifă
