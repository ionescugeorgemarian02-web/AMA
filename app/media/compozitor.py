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
from dataclasses import dataclass, replace
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat
from sqlalchemy.orm import Session

from app.media import biblioteca, licente, normalizare, provenienta, sabloane, selectie, vizual
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
    text: str, cutie: list[int], marime: int, nume_font: str, minim: int = MARIME_MIN
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    x0, y0, x1, y1 = cutie
    m = marime
    while m >= minim:
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


def _dimensiuni(png: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(png)).size


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
        rol_vizual="coperta",
        descriere=f"{sablon.tip}: {' / '.join(texte.values())[:200]}",
        licenta={"tip": "productie_proprie", "statut": licente.STATUT_OK, "componente": componente},
        generare={"sablon": sablon.tip, "versiune": sablon.versiune, "texte": texte,
                  "cutii_text": [list(t[0]) for t in c.texte], "dimensiuni": list(_dimensiuni(c.png))},
    )  # fmt: skip
    v = vizual.verdict(c.png, c.asteptari)
    provenienta.emite(db, a, validari={"G5": {"rezultat": v.rezultat.value,
                                              "dovezi": [d.detalii for d in v.dovezi]}})  # fmt: skip
    return a, c


# --- machetele editoriale (F-editorial, decizia 5): foto_dominanta, detaliu_explicat, carusel ---

Cutie = tuple[int, int, int, int]
MARGINE = 60  # [I] marginea sigură a machetelor
PAD = 28  # [I] aerul dintre text și voal / subiect
LOGO_SEMNATURA = 88  # [I] sigla discretă, în colțul liber
VOAL = 0.74  # [I] opacitatea voalului de contrast sub titlu
ESTOMPARE = 110  # [I] px în care voalul se stinge spre interiorul fotografiei
BANDA_LEGENDA = 330  # [I] înălțimea benzii de sub fotografie (detaliu fără punct)
FONT = "DejaVuSans-Bold.ttf"


class MachetaIlizibila(ValueError):
    """Exportul nu trece verificarea la 360 px (literă prea mică sau text peste subiect)."""

    def __init__(self, probleme: list[str]) -> None:
        super().__init__("; ".join(probleme))
        self.probleme = probleme


@dataclass(frozen=True)
class Macheta:
    nume: str
    png: bytes
    latime: int
    inaltime: int
    titlu_marime: int  # mărimea fontului titlului, în px la lățimea machetei
    texte: tuple[Cutie, ...]  # cutiile ocupate de text (titlu, etichetă, legendă)
    subiect: Cutie | None  # zona subiectului în pixelii machetei (protejată)
    asteptari: vizual.AsteptariVizuale
    pozitie_titlu: str = ""  # sus / mijloc / jos (zona cea mai liniștită) sau „banda”
    nota: str = ""


def _font(m: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(cale_font(FONT)), m)


def _atinge(a: Cutie, b: Cutie) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def zona_subiect(img: Image.Image, generare: dict[str, Any] | None = None) -> Cutie:
    """Zona subiectului, în pixelii imaginii: `generare["zona_subiect"]` (relativă, x0 y0 x1 y1 în 0–1) dacă
    activul o are, altfel centrul de energie (muchiile, ponderate cu pătratul) ± 1,5 abateri."""
    w, h = img.size
    z = (generare or {}).get("zona_subiect")
    if isinstance(z, list | tuple) and len(z) == 4:
        x0, y0, x1, y1 = (float(v) for v in z)
        return round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h)
    mw = 64
    mh = max(3, round(mw * h / w))
    e = img.convert("L").resize((mw, mh)).filter(ImageFilter.FIND_EDGES)
    date = e.tobytes()
    tot = sx = sy = sxx = syy = 0.0
    for y in range(1, mh - 1):  # bordura e artefact al filtrului
        for x in range(1, mw - 1):
            v = float(date[y * mw + x]) ** 2
            tot += v
            sx, sy, sxx, syy = sx + v * x, sy + v * y, sxx + v * x * x, syy + v * y * y
    if tot <= 0:
        return w // 4, h // 4, 3 * w // 4, 3 * h // 4
    cx, cy = sx / tot, sy / tot
    dx = max((sxx / tot - cx * cx) ** 0.5 * 1.5, mw * 0.15)
    dy = max((syy / tot - cy * cy) ** 0.5 * 1.5, mh * 0.15)
    fx, fy = w / mw, h / mh
    return (
        max(0, round((cx - dx) * fx)),
        max(0, round((cy - dy) * fy)),
        min(w, round((cx + dx) * fx)),
        min(h, round((cy + dy) * fy)),
    )


def zona_relativa(a: Activ) -> tuple[float, float, float, float] | None:
    """Zona subiectului unui activ, relativă (0–1): din `generare`, altfel, pentru o fotografie, din energie.
    Pentru video fără zonă declarată: necunoscută (`None`)."""
    z = (a.generare or {}).get("zona_subiect")
    if isinstance(z, list | tuple) and len(z) == 4:
        x0, y0, x1, y1 = (float(v) for v in z)
        return x0, y0, x1, y1
    if a.categorie != "foto":
        return None
    img = Image.open(io.BytesIO(biblioteca.citeste_fisier(a)))
    x0, y0, x1, y1 = zona_subiect(img)
    return x0 / img.width, y0 / img.height, x1 / img.width, y1 / img.height


def decupeaza(
    img: Image.Image,
    w: int,
    h: int,
    subiect: Cutie,
    *,
    zoom: float = 1.0,
    centru: tuple[float, float] | None = None,
) -> tuple[Image.Image, Cutie, tuple[float, float, float]]:
    """Umple w×h din imagine, cu fereastra centrată pe subiect (sau pe `centru`), fără ieșire din sursă.
    Întoarce (imaginea, subiectul în pixelii noi, transformarea x0, y0, scara)."""
    scara = max(w / img.width, h / img.height) * max(1.0, zoom)
    lw, lh = w / scara, h / scara
    cx, cy = centru or ((subiect[0] + subiect[2]) / 2, (subiect[1] + subiect[3]) / 2)
    x0 = min(max(cx - lw / 2, 0.0), img.width - lw)
    y0 = min(max(cy - lh / 2, 0.0), img.height - lh)
    out = img.crop((round(x0), round(y0), round(x0 + lw), round(y0 + lh))).resize(
        (w, h), Image.Resampling.LANCZOS
    )

    def tr(x: float, y: float) -> tuple[int, int]:
        return min(w, max(0, round((x - x0) * scara))), min(h, max(0, round((y - y0) * scara)))

    a, b = tr(subiect[0], subiect[1])
    c, d = tr(subiect[2], subiect[3])
    return out, (a, b, c, d), (x0, y0, scara)


def zona_linistita(img: Image.Image, subiect: Cutie | None, necesar: int) -> tuple[str, Cutie]:
    """Zona titlului: dintre treimile sus / mijloc / jos, partea liberă de subiect cu varianța luminozității
    cea mai mică și destul de înaltă (`necesar` px). Fără una destul de înaltă: cea mai înaltă liberă."""
    w, h = img.size
    gri = img.convert("L")
    m = MARGINE
    variante: list[tuple[float, str, Cutie]] = []
    for nume, (a, b) in {
        "sus": (m, h // 3),
        "mijloc": (h // 3, 2 * h // 3),
        "jos": (2 * h // 3, h - m),
    }.items():
        if subiect is not None and subiect[1] < b and subiect[3] > a:
            if nume == "sus":
                b = subiect[1] - PAD
            elif nume == "jos":
                a = subiect[3] + PAD
            else:
                continue
        if b - a < 40:
            continue
        variante.append((ImageStat.Stat(gri.crop((0, a, w, b))).var[0], nume, (m, a, w - m, b)))
    if not variante:  # subiectul acoperă tot: jos, iar verificarea la 360 px va refuza exportul
        return "jos", (m, 2 * h // 3, w - m, h - m)
    inalte = [v for v in variante if v[2][3] - v[2][1] >= necesar]
    _, nume, cutie = min(inalte) if inalte else max(variante, key=lambda v: v[2][3] - v[2][1])
    return nume, cutie


def _bloc_titlu(text: str, latime: int, inaltime: int) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """Titlul în rolul `titlu` (88 px), coborât cel mult până la `TITLU_MIN`; (font, rânduri, înălțimea)."""
    f, linii = _incadreaza(
        text.translate(normalizare.SEDILA),
        [0, 0, latime, inaltime],
        sabloane.TIPOGRAFIE["titlu"],
        FONT,
        minim=sabloane.TITLU_MIN,
    )
    return f, linii, len(linii) * round(f.size * 1.2)


def _necesar_titlu(text: str, latime: int) -> int:
    f = _font(sabloane.TIPOGRAFIE["titlu"])
    return len(_rupe(text.translate(normalizare.SEDILA), f, latime)) * round(f.size * 1.2) + 2 * PAD


def _scrie(
    desen: ImageDraw.ImageDraw, x: int, y: int, linii: list[str], f: ImageFont.FreeTypeFont, culoare: str
) -> Cutie:
    pas = round(f.size * 1.2)
    for k, li in enumerate(linii):
        desen.text((x, y + k * pas), li, font=f, fill=culoare)
    lat = max(round(f.getlength(li)) for li in linii)
    return x - 6, y - 6, x + lat + 6, y + len(linii) * pas + 6


def _voal(img: Image.Image, y0: int, y1: int, pozitie: str, culoare: str) -> Image.Image:
    """Voalul de contrast: opac `VOAL` pe bloc, stins pe `ESTOMPARE` px spre interiorul fotografiei."""
    w, h = img.size
    masca = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(masca)
    plin = round(255 * VOAL)
    if pozitie == "sus":  # voalul pornește de la marginea cadrului, nu lasă o fâșie de fotografie deasupra
        y0 = 0
    elif pozitie == "jos":
        y1 = h
    d.rectangle((0, y0, w, y1), fill=plin)
    for k in range(ESTOMPARE):
        v = round(plin * (1 - k / ESTOMPARE))
        if pozitie in ("sus", "mijloc"):
            d.line((0, y1 + k, w, y1 + k), fill=v)
        if pozitie in ("jos", "mijloc"):
            d.line((0, y0 - k, w, y0 - k), fill=v)
    return Image.composite(Image.new("RGB", (w, h), culoare), img, masca)


def _sigla(img: Image.Image, logo: bytes | None, ocupate: list[Cutie]) -> Cutie | None:
    """Semnătura: sigla mică în primul colț liber (dreapta jos, dreapta sus, stânga jos, stânga sus)."""
    if logo is None:
        return None
    w, h, m, s = img.width, img.height, MARGINE, LOGO_SEMNATURA
    colturi = [(w - m - s, h - m - s), (w - m - s, m), (m, h - m - s), (m, m)]
    for x, y in colturi:
        c = (x, y, x + s, y + s)
        larg = (x - PAD, y - PAD, x + s + PAD, y + s + PAD)
        if not any(_atinge(larg, o) for o in ocupate):
            lg = Image.open(io.BytesIO(logo)).convert("RGBA").resize((s, s))
            img.paste(lg, (x, y), lg)
            return c
    return None


def _png(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def _asteptari(
    nume: str,
    png: bytes,
    ident: dict[str, Any],
    texte: list[tuple[Cutie, int]],
    zone_foto: list[Cutie],
    cutie_logo: Cutie | None,
) -> vizual.AsteptariVizuale:
    ref = _png(Image.open(io.BytesIO(png)).crop(cutie_logo)) if cutie_logo else None
    return vizual.AsteptariVizuale(
        paleta=tuple(ident["culori"].values()),
        texte=tuple(texte),
        logo=ref,
        cutie_logo=cutie_logo,
        zone_foto=tuple(zone_foto),
        margini=(MARGINE,) * 4,
        nume=nume,
    )


def foto_dominanta(
    foto: bytes,
    titlu: str,
    ident: dict[str, Any],
    *,
    logo: bytes | None = None,
    generare: dict[str, Any] | None = None,
    latime: int = 1080,
    inaltime: int = 1350,
) -> Macheta:
    """Fotografia umple cadrul, decupată pe subiect; titlul scurt stă în zona cea mai liniștită, pe un voal
    de contrast; sigla mică, în colțul liber."""
    sursa = Image.open(io.BytesIO(foto)).convert("RGB")
    img, subiect, _ = decupeaza(sursa, latime, inaltime, zona_subiect(sursa, generare))
    lat_text = latime - 2 * (MARGINE + PAD)
    pozitie, zona = zona_linistita(img, subiect, _necesar_titlu(titlu, lat_text))
    f, linii, hb = _bloc_titlu(
        titlu, lat_text, max(zona[3] - zona[1] - 2 * PAD, round(sabloane.TITLU_MIN * 1.2))
    )
    y = {"sus": zona[1] + PAD, "jos": zona[3] - PAD - hb}.get(pozitie, (zona[1] + zona[3] - hb) // 2)
    img = _voal(img, y - PAD, y + hb + PAD, pozitie, ident["culori"]["text"])
    cutie = _scrie(ImageDraw.Draw(img), MARGINE + PAD, y, linii, f, "#FFFFFF")
    c_logo = _sigla(img, logo, [subiect, cutie])
    png = _png(img)
    return Macheta(
        "foto_dominanta",
        png,
        latime,
        inaltime,
        int(f.size),
        (cutie,),
        subiect,
        _asteptari("foto_dominanta", png, ident, [(cutie, int(f.size))], [(0, 0, latime, inaltime)], c_logo),
        pozitie,
    )


def detaliu_explicat(
    foto: bytes,
    eticheta: str,
    ident: dict[str, Any],
    *,
    punct: tuple[float, float] | None = None,
    logo: bytes | None = None,
    generare: dict[str, Any] | None = None,
    legenda: str = "",
    randuri_legenda: int = 1,
    latime: int = 1080,
    inaltime: int = 1350,
) -> Macheta:
    """Fotografie apropiată + o singură adnotare: cu `punct` (x, y relative la fotografie) o linie spre piesă
    și eticheta în zona liniștită; fără punct, eticheta (și legenda) sub fotografie."""
    sursa = Image.open(io.BytesIO(foto)).convert("RGB")
    c = ident["culori"]
    if punct is None:
        hf = inaltime - BANDA_LEGENDA
        poza, subiect, _ = decupeaza(sursa, latime, hf, zona_subiect(sursa, generare), zoom=1.15)
        img = Image.new("RGB", (latime, inaltime), c["fundal"])
        img.paste(poza, (0, 0))
        desen = ImageDraw.Draw(img)
        x, y = MARGINE + PAD, hf + PAD + 6
        loc = (
            BANDA_LEGENDA
            - 2 * PAD
            - MARGINE
            - (round(sabloane.TIPOGRAFIE["legenda"] * 1.3) * randuri_legenda if legenda else 0)
        )
        f, linii, hb = _bloc_titlu(eticheta, latime - 2 * x - LOGO_SEMNATURA - PAD, loc)
        texte = [_scrie(desen, x, y, linii, f, c["text"])]
        marimi = [int(f.size)]
        if legenda:
            fl = _font(sabloane.TIPOGRAFIE["legenda"])
            rand = _rupe(legenda.translate(normalizare.SEDILA), fl, latime - 2 * x - LOGO_SEMNATURA - PAD)
            rand = rand[:randuri_legenda]
            texte.append(_scrie(desen, x, y + hb + 10, rand, fl, c["text"]))
            marimi.append(int(fl.size))
        c_logo = _sigla(img, logo, [subiect, *texte, (0, 0, latime, hf)])
        png = _png(img)
        return Macheta(
            "detaliu_explicat",
            png,
            latime,
            inaltime,
            marimi[0],
            tuple(texte),
            subiect,
            _asteptari(
                "detaliu_explicat",
                png,
                ident,
                list(zip(texte, marimi, strict=True)),
                [(0, 0, latime, hf)],
                c_logo,
            ),
            "banda",
        )
    centru = (punct[0] * sursa.width, punct[1] * sursa.height)
    r = 110  # [I] raza zonei piesei, protejată de text
    img, _, (x0, y0, scara) = decupeaza(
        sursa, latime, inaltime, zona_subiect(sursa, generare), zoom=1.35, centru=centru
    )
    px, py = round((centru[0] - x0) * scara), round((centru[1] - y0) * scara)
    subiect = (max(0, px - r), max(0, py - r), min(latime, px + r), min(inaltime, py + r))
    lat_text = min(600, latime - 2 * (MARGINE + PAD))
    pozitie, zona = zona_linistita(img, subiect, _necesar_titlu(eticheta, lat_text) + PAD)
    f, linii, hb = _bloc_titlu(
        eticheta, lat_text, max(zona[3] - zona[1] - 3 * PAD, round(sabloane.TITLU_MIN * 1.2))
    )
    lat = max(round(f.getlength(li)) for li in linii)
    x = MARGINE + PAD if px > latime // 2 else latime - MARGINE - PAD - lat
    y = {"sus": zona[1] + PAD, "jos": zona[3] - PAD - hb}.get(pozitie, (zona[1] + zona[3] - hb) // 2)
    desen = ImageDraw.Draw(img)
    eticheta_cutie = (x - PAD, y - PAD // 2, x + lat + PAD, y + hb + PAD // 2)
    capat = ((eticheta_cutie[0] + eticheta_cutie[2]) // 2, eticheta_cutie[3] if py > y else eticheta_cutie[1])
    dist = max(1.0, ((capat[0] - px) ** 2 + (capat[1] - py) ** 2) ** 0.5)
    margine_inel = (round(px + (capat[0] - px) * 40 / dist), round(py + (capat[1] - py) * 40 / dist))
    for gros, cul in ((12, c["text"]), (6, "#FFFFFF")):  # linia: contur închis, miez alb; se oprește la inel
        desen.line((capat, margine_inel), fill=cul, width=gros)
    desen.ellipse((px - 34, py - 34, px + 34, py + 34), outline=c["text"], width=14)
    desen.ellipse((px - 34, py - 34, px + 34, py + 34), outline="#FFFFFF", width=7)
    desen.rounded_rectangle(eticheta_cutie, radius=18, fill=c["fundal"])
    cutie = _scrie(desen, x, y, linii, f, c["text"])
    c_logo = _sigla(img, logo, [subiect, eticheta_cutie])
    png = _png(img)
    return Macheta(
        "detaliu_explicat",
        png,
        latime,
        inaltime,
        int(f.size),
        (cutie,),
        subiect,
        _asteptari(
            "detaliu_explicat", png, ident, [(cutie, int(f.size))], [(0, 0, latime, inaltime)], c_logo
        ),
        pozitie,
    )


def carusel_cadre(
    intrebare: str,
    idei: list[str],
    pas_urmator: str,
    ident: dict[str, Any],
    *,
    logo: bytes | None = None,
    fotografii: list[tuple[bytes, dict[str, Any]] | None] | None = None,
    latime: int = 1080,
    inaltime: int = 1350,
) -> list[Macheta]:
    """N cadre cu aceeași grilă, tipografie și paletă: întâi întrebarea, apoi câte o idee pe cadru, la urmă
    pasul următor. O idee „titlu\\ncorp” are și un rând de corp sub titlu. `fotografii` (aliniate cu
    `idei`, `(corp, generare)` sau `None`): cadrul intermediar cu fotografie potrivită e o fotografie
    apropiată cu eticheta și legenda în bandă (stilul `detaliu_explicat`); doar fără fotografie rămâne
    tipografic."""
    c = ident["culori"]
    cadre = [intrebare, *idei, pas_urmator]
    n = len(cadre)
    x, sus = 100, 300  # grila: coloana de text și linia titlului
    out = []
    for k, text in enumerate(cadre):
        prima, ultima = k == 0, k == n - 1
        foto = None
        if fotografii and not prima and not ultima and k - 1 < len(fotografii):
            foto = fotografii[k - 1]
        if foto is not None:
            titlu, _, corp = text.partition("\n")
            m = detaliu_explicat(foto[0], titlu, ident, logo=logo, generare=foto[1], legenda=corp.strip(),
                                 randuri_legenda=2, latime=latime, inaltime=inaltime)  # fmt: skip
            out.append(replace(m, nume="carusel"))
            continue
        fundal, cul = (c["primara"], c["alb"]) if prima else (c["fundal"], c["text"])
        img = Image.new("RGB", (latime, inaltime), fundal)
        desen = ImageDraw.Draw(img)
        if not prima:
            desen.rectangle((MARGINE, MARGINE, latime - MARGINE, MARGINE + 24), fill=c["primara"])
        fl = _font(sabloane.TIPOGRAFIE["legenda"])
        reper = "Pasul următor" if ultima else f"{k + 1} / {n}"
        texte = [_scrie(desen, x, 150, [reper], fl, c["alb"] if prima else _culoare(ident, "accent_text"))]
        marimi = [int(fl.size)]
        titlu, _, corp = text.partition("\n")
        f, linii, hb = _bloc_titlu(titlu, latime - 2 * x, 620)
        texte.insert(0, _scrie(desen, x, sus, linii, f, cul))
        marimi.insert(0, int(f.size))
        if corp.strip():
            fc = _font(sabloane.TIPOGRAFIE["corp"])
            rand = _rupe(corp.strip().translate(normalizare.SEDILA), fc, latime - 2 * x)[:4]
            texte.append(_scrie(desen, x, sus + hb + 50, rand, fc, cul))
            marimi.append(int(fc.size))
        c_logo = None
        if logo is not None:
            s = LOGO_SEMNATURA
            c_logo = (
                latime - MARGINE - s - 40,
                inaltime - MARGINE - s - 40,
                latime - MARGINE - 40,
                inaltime - MARGINE - 40,
            )
            lg = Image.open(io.BytesIO(logo)).convert("RGBA").resize((s, s))
            img.paste(lg, c_logo[:2], lg)
        png = _png(img)
        out.append(
            Macheta(
                "carusel",
                png,
                latime,
                inaltime,
                marimi[0],
                tuple(texte),
                None,
                _asteptari(
                    f"carusel {k + 1}/{n}", png, ident, list(zip(texte, marimi, strict=True)), [], c_logo
                ),
                "sus",
            )
        )
    return out


def carusel(
    intrebare: str, idei: list[str], pas_urmator: str, ident: dict[str, Any], *, logo: bytes | None = None
) -> list[bytes]:
    """Caruselul ca listă de PNG-uri, în ordine."""
    return [m.png for m in carusel_cadre(intrebare, idei, pas_urmator, ident, logo=logo)]


def inaltime_litera(marime: int, latime: int, latime_export: int = sabloane.LATIME_VERIFICARE) -> float:
    """Înălțimea literei mari (H) a titlului la exportul de `latime_export` px, măsurată pe glifa reală."""
    b = _font(marime * latime_export / latime).getbbox("H")
    return float(b[3] - b[1])


def verifica_export(m: Macheta) -> list[str]:
    """Verificarea la 360 px lățime: litera titlului ≥ 14 px și subiectul vizibil, neacoperit de text."""
    out = []
    litera = inaltime_litera(m.titlu_marime, m.latime)
    if litera < sabloane.LITERA_TITLU_MIN:
        out.append(
            f"{m.nume}: litera titlului are {litera:.1f} px la {sabloane.LATIME_VERIFICARE} px "
            f"(minimum {sabloane.LITERA_TITLU_MIN})"
        )
    if m.subiect is not None:
        s = m.subiect
        if (s[2] - s[0]) * (s[3] - s[1]) <= 0:
            out.append(f"{m.nume}: subiectul nu se vede în cadru")
        for t in m.texte:
            if _atinge(t, s):
                out.append(f"{m.nume}: textul {t} acoperă subiectul {s}")
    return out


# --- exportul în bibliotecă


@dataclass(frozen=True)
class Export:
    macheta: str
    nota: str
    active: list[Activ]
    imagini: list[bytes]


def fotografii_potrivite(active: list[Activ], ce_vede: str) -> list[Activ]:
    """Fotografiile clientului cu licență, cea mai potrivită cu „ce vede publicul” întâi."""
    foto = [
        a
        for a in active
        if a.rol_vizual == "fotografie" and a.categorie == "foto" and not licente.probleme(a.licenta)
    ]
    return sorted(
        foto,
        key=lambda a: (-selectie.potrivire(ce_vede, f"{a.subiect or ''} {a.descriere or ''}")[0], str(a.id)),
    )


def fotografii_pe_idei(idei: list[str], fotografii: list[Activ]) -> list[Activ | None]:
    """Fotografia potrivită fiecărei idei din carusel (`selectie.potrivire` pe subiect + descriere), întâi
    una nefolosită încă; `None` când nicio fotografie nu se potrivește (cadrul rămâne tipografic)."""
    folosite: set[uuid.UUID] = set()
    out: list[Activ | None] = []
    for idee in idei:
        notate = [
            (-scor, a.id in folosite, str(a.id), a)
            for a in fotografii
            if (scor := selectie.potrivire(idee, f"{a.subiect or ''} {a.descriere or ''}")[0]) > 0
        ]
        ales = min(notate, key=lambda t: t[:3])[3] if notate else None
        if ales is not None:
            folosite.add(ales.id)
        out.append(ales)
    return out


def _salveaza(
    db: Session, tenant_id: uuid.UUID, m: Macheta, k: int, componente: list[Activ], generare: dict[str, Any]
) -> Activ:
    a = biblioteca.incarca(
        db,
        tenant_id,
        m.png,
        nume_original=f"{m.nume}-{k + 1}.png",
        sursa="compozitor",
        utilizator_id=None,
        rol_vizual="coperta",
        descriere=f"{m.nume}: {generare.get('titlu', '')}"[:200],
        licenta={
            "tip": "productie_proprie",
            "statut": licente.STATUT_OK,
            "componente": [
                {"activ_id": str(x.id), "licenta": (x.licenta or {}).get("tip")} for x in componente
            ]
            or [{"descriere": f"macheta {m.nume}"}],
        },
        generare={
            **generare,
            "macheta": m.nume,
            "cadru": k + 1,
            "pozitie_titlu": m.pozitie_titlu,
            "zona_subiect": list(m.subiect) if m.subiect else None,
            "cutii_text": [list(t) for t in m.texte],
            "dimensiuni": [m.latime, m.inaltime],
        },
    )
    v = vizual.verdict(m.png, m.asteptari)
    provenienta.emite(
        db, a, validari={"G5": {"rezultat": v.rezultat.value, "dovezi": [d.detalii for d in v.dovezi]}}
    )
    return a


def exporta(
    db: Session,
    tenant_id: uuid.UUID,
    nume_brand: str,
    brief: dict[str, Any],
    texte: dict[str, Any],
    *,
    active: list[Activ] | None = None,
    punct: tuple[float, float] | None = None,
) -> Export:
    """Alege macheta din brief și din activele disponibile, o compune, o verifică la 360 px
    (`MachetaIlizibila`) și o înregistrează (`rol_vizual='coperta'`: nu reintră în scene).
    `texte`: `titlu`, opțional `legenda`; pentru carusel `intrebare`, `idei`, `pas`."""
    ident, _ = sabloane.identitate(db, tenant_id, nume_brand)
    disponibile = active if active is not None else biblioteca.ale_clientului(db, tenant_id)
    fotografii = fotografii_potrivite(disponibile, str(brief.get("ce_vede_publicul") or ""))
    macheta, nota = sabloane.alege_macheta(brief, len(fotografii))
    titlu = str(texte.get("titlu") or texte.get("intrebare") or "").strip()
    if macheta == sabloane.MACHETA_TIPOGRAFICA:
        s = next(x for x in sabloane.asigura_sabloane(db, tenant_id, nume_brand) if x.tip == macheta)
        a, c = creeaza(db, tenant_id, s, {"titlu": titlu, "corp": str(texte.get("legenda") or "")})
        a.generare = {**(a.generare or {}), "macheta": macheta, "nota": nota}
        db.flush()
        return Export(macheta, nota, [a], [c.png])
    sigla = sabloane.logo_activ(db, tenant_id, ident)
    logo = biblioteca.citeste_fisier(sigla)
    componente = [sigla]
    if macheta == "carusel":
        idei = [str(x) for x in texte.get("idei") or []]
        pe_idei = fotografii_pe_idei(idei, fotografii)
        for f in pe_idei:
            if f is not None and f not in componente:
                componente.append(f)
        cadre = carusel_cadre(
            str(texte.get("intrebare") or titlu),
            idei,
            str(texte.get("pas") or ""),
            ident,
            logo=logo,
            fotografii=[
                None if f is None else (biblioteca.citeste_fisier(f), f.generare or {}) for f in pe_idei
            ],
        )
    else:
        foto = fotografii[0]
        componente.append(foto)
        corp, gen = biblioteca.citeste_fisier(foto), foto.generare or {}
        if macheta == "foto_dominanta":
            cadre = [foto_dominanta(corp, titlu, ident, logo=logo, generare=gen)]
        else:
            p = punct or (tuple(gen["punct_piesa"]) if isinstance(gen.get("punct_piesa"), list) else None)
            cadre = [
                detaliu_explicat(
                    corp,
                    titlu,
                    ident,
                    punct=p,
                    logo=logo,
                    generare=gen,
                    legenda=str(texte.get("legenda") or ""),
                )
            ]
    probleme = [p for m in cadre for p in verifica_export(m)]
    if probleme:
        raise MachetaIlizibila(probleme)
    for x in componente:
        licente.foloseste(db, x.id, scop="compozitie")
    gen_txt = {"titlu": titlu, "texte": {k: v for k, v in texte.items() if isinstance(v, str | list)}}
    salvate = [_salveaza(db, tenant_id, m, k, componente, gen_txt) for k, m in enumerate(cadre)]
    return Export(macheta, nota, salvate, [m.png for m in cadre])
