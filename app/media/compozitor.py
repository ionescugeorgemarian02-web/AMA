"""Compozitorul (F8.10, docs/14 §14.10, F4): completează un șablon cu textul aprobat și îl transformă în
imagine.

Randatorul de referință desenează direct cu Pillow (fontul cu toate diacriticele, ș și ț cu virgulă).
Șabloanele
HTML randate cu Chromium (HyperFrames, formatul C) sunt adaptorul de la migrare (NEVERIFICAT). Textul se
încadrează
în cutie micșorând fontul și rupând rândurile după lățimea măsurată; ieșirea are geometria ei (cutii de text,
logo, fotografii), pe care G5 o verifică din pixeli.
"""

import io
import uuid
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

from app.media import biblioteca, licente, normalizare, provenienta, vizual
from app.media.modele import Activ, SablonGrafic
from app.media.subtitrari import cale_font

MARIME_MIN = 28


class TextPreaLung(ValueError):
    pass


@dataclass(frozen=True)
class Compozitie:
    png: bytes
    texte: tuple[tuple[tuple[int, int, int, int], int], ...]  # (cutia ocupată, mărimea fontului)
    asteptari: vizual.AsteptariVizuale


def _culoare(ident: dict[str, Any], rol: str) -> str:
    c = ident["culori"]
    if rol == "accent_text":  # accentul ca text pe fundal: cel mai contrastant dintre accent și principală
        return str(max((c["accent"], c["primara"]),
                       key=lambda x: vizual.contrast(vizual.rgb(x), vizual.rgb(c["fundal"]))))  # fmt: skip
    return str(c[rol])


def _rupe(text: str, font: ImageFont.FreeTypeFont, latime: int) -> list[str]:
    linii: list[str] = []
    for paragraf in text.split("\n"):
        curenta = ""
        for cuv in paragraf.split():
            proba = f"{curenta} {cuv}".strip()
            if font.getlength(proba) <= latime or not curenta:
                curenta = proba
            else:
                linii.append(curenta)
                curenta = cuv
        linii.append(curenta)
    return linii


def _incadreaza(
    text: str, cutie: list[int], marime: int, nume_font: str
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    x0, y0, x1, y1 = cutie
    m = marime
    while m >= MARIME_MIN:
        f = ImageFont.truetype(str(cale_font(nume_font)), m)
        linii = _rupe(text, f, x1 - x0)
        if all(f.getlength(li) <= x1 - x0 for li in linii) and len(linii) * round(m * 1.2) <= y1 - y0:
            return f, linii
        m -= 4
    raise TextPreaLung(f"textul nu încape în cutia {cutie}: {text[:40]!r}")


def compune(
    sablon: SablonGrafic,
    texte: dict[str, str],
    *,
    foto: bytes | None = None,
    logo: bytes | None = None,
) -> Compozitie:
    """Nucleul: șablon + texte (+ fotografie, logo) -> PNG și geometria lui."""
    d = sablon.definitie
    ident = d["identitate"]
    w, h = d["latime"], d["inaltime"]
    img = Image.new("RGB", (w, h), _culoare(ident, d["fundal"]))
    zone_foto: list[tuple[int, int, int, int]] = []
    if foto is not None and d.get("foto"):
        fx0, fy0, fx1, fy1 = d["foto"]
        poza = Image.open(io.BytesIO(foto)).convert("RGB")
        scara = max((fx1 - fx0) / poza.width, (fy1 - fy0) / poza.height)
        poza = poza.resize((round(poza.width * scara) + 1, round(poza.height * scara) + 1))
        ox, oy = (poza.width - (fx1 - fx0)) // 2, (poza.height - (fy1 - fy0)) // 2
        img.paste(poza.crop((ox, oy, ox + fx1 - fx0, oy + fy1 - fy0)), (fx0, fy0))
        if d.get("voal"):  # fotografia de fundal sub text: voal în culoarea principală, pentru contrast
            voal = Image.new("RGB", (fx1 - fx0, fy1 - fy0), _culoare(ident, d["voal"]))
            img.paste(Image.blend(img.crop((fx0, fy0, fx1, fy1)), voal, 0.78), (fx0, fy0))
        else:
            zone_foto.append((fx0, fy0, fx1, fy1))
    desen = ImageDraw.Draw(img)
    if d.get("banda"):
        desen.rectangle(d["banda"]["cutie"], fill=_culoare(ident, d["banda"]["culoare"]))
    ocupate: list[tuple[tuple[int, int, int, int], int]] = []
    for z in d["texte"]:
        t = texte.get(z["rol"], "").strip()
        if not t:
            continue
        t = t.translate(normalizare.SEDILA)
        f, linii = _incadreaza(t, z["cutie"], z["marime"], "DejaVuSans-Bold.ttf")
        x0, y0 = z["cutie"][0], z["cutie"][1]
        pas = round(f.size * 1.2)
        for k, li in enumerate(linii):
            desen.text((x0, y0 + k * pas), li, font=f, fill=_culoare(ident, z["culoare"]))
        lat = max(round(f.getlength(li)) for li in linii)
        ocupate.append(((x0 - 6, y0 - 6, x0 + lat + 6, y0 + len(linii) * pas + 6), int(f.size)))
    if logo is not None and d.get("logo"):
        lx0, ly0, lx1, ly1 = d["logo"]
        lg = Image.open(io.BytesIO(logo)).convert("RGBA").resize((lx1 - lx0, ly1 - ly0))
        img.paste(lg, (lx0, ly0), lg)
    out = io.BytesIO()
    img.save(out, "PNG")
    png = out.getvalue()
    referinta_logo = None
    if logo is not None and d.get("logo"):  # logoul așa cum trebuie să apară (pe fundalul șablonului)
        lx0, ly0, lx1, ly1 = d["logo"]
        ref = Image.open(io.BytesIO(png)).crop((lx0, ly0, lx1, ly1))
        b = io.BytesIO()
        ref.save(b, "PNG")
        referinta_logo = b.getvalue()
    pal = tuple(v for k, v in ident["culori"].items())
    sus, jos, st, dr = d["margini"]
    return Compozitie(
        png,
        tuple(ocupate),
        vizual.AsteptariVizuale(
            paleta=pal, texte=tuple(ocupate), logo=referinta_logo,
            cutie_logo=(lx0, ly0, lx1, ly1) if referinta_logo else None,
            zone_foto=tuple(zone_foto), margini=(sus, jos, st, dr), nume=sablon.tip,
        ),
    )  # fmt: skip


def creeaza(
    db: Session,
    tenant_id: uuid.UUID,
    sablon: SablonGrafic,
    texte: dict[str, str],
    *,
    foto: Activ | None = None,
) -> tuple[Activ, Compozitie]:
    """Compune, verifică G5 și înregistrează imaginea (licența: producție proprie, cu componentele ei)."""
    comp_ids = []
    foto_corp = None
    if foto is not None:
        licente.foloseste(db, foto.id, scop="compozitie", obiect_id=sablon.id)
        foto_corp = biblioteca.citeste_fisier(foto)
        comp_ids.append(foto)
    logo_activ = (
        db.get(Activ, uuid.UUID(sablon.definitie["logo_activ"]))
        if sablon.definitie.get("logo_activ")
        else None
    )
    logo_corp = None
    if logo_activ is not None:
        licente.foloseste(db, logo_activ.id, scop="compozitie", obiect_id=sablon.id)
        logo_corp = biblioteca.citeste_fisier(logo_activ)
        comp_ids.append(logo_activ)
    c = compune(sablon, texte, foto=foto_corp, logo=logo_corp)
    componente = [{"activ_id": str(a.id), "licenta": (a.licenta or {}).get("tip")} for a in comp_ids] or [
        {"descriere": f"șablonul {sablon.tip} v{sablon.versiune}"}
    ]
    a = biblioteca.incarca(
        db, tenant_id, c.png, nume_original=f"{sablon.tip}.png", sursa="compozitor", utilizator_id=None,
        descriere=f"{sablon.tip}: {' / '.join(texte.values())[:200]}",
        licenta={"tip": "productie_proprie", "statut": licente.STATUT_OK, "componente": componente},
        generare={"sablon": sablon.tip, "versiune": sablon.versiune, "texte": texte},
    )  # fmt: skip
    v = vizual.verdict(c.png, c.asteptari)
    provenienta.emite(db, a, validari={"G5": {"rezultat": v.rezultat.value,
                                              "dovezi": [d.detalii for d in v.dovezi]}})  # fmt: skip
    return a, c
