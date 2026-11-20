"""Controlul tehnic media, G6 (F8.8, docs/09 §9.4–9.5): un video final trece doar dacă formatul, imaginea,
sunetul, sincronizarea și subtitrările sunt în regulă. Totul se măsoară determinist, dintr-o singură decodare:

- format: H.264 + AAC, rezoluția și cadrele pe secundă ale canalului, `yuv420p`, sub limita de mărime;
- imagine: fără cadre negre mai lungi de 0,5 s și fără cadre înghețate mai lungi de 2 s (cu excepțiile
  intenționate);
- sunet: nivel integrat −14 LUFS ± 1, vârf sub −1 dBTP, fără tăceri mai lungi de 1,5 s;
- sincronizare: sub 100 ms între durata sunetului și a imaginii;
- subtitrări: fiecare ecran în zona sigură a canalului, niciun cuvânt tăiat (din geometria calculată la
  montaj; OCR pe cadre-eșantion: NEVERIFICAT, la migrare).

Verdictul este un `validare.Verdict` (G6, V0), cu dovezi pentru fiecare problemă.
"""

import io
import re
import tempfile
import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from PIL import Image
from sqlalchemy.orm import Session

from app import validare
from app.media import ffmpeg, lista, subtitrari, sunet

VERSIUNE = "1"
NEGRU_MAX, INGHETAT_MAX, LINISTE_MAX = 0.5, 2.0, 1.5
DESINCRONIZARE_MAX = 0.1
MB = 1024 * 1024
LIMITE_CANAL = {"tiktok": 287 * MB, "instagram": 300 * MB, "facebook": 300 * MB, "youtube": 300 * MB}  # [I]


@dataclass(frozen=True)
class Asteptari:
    canal: str = "tiktok"
    latime: int = 1080
    inaltime: int = 1920
    cadre_pe_secunda: int = 30
    ecrane: tuple[subtitrari.Ecran, ...] = ()
    intentionate: tuple[tuple[float, float], ...] = field(default_factory=tuple)  # intervale permise (îngheț)


@dataclass(frozen=True)
class Problema:
    regula: str
    detalii: str


def _intervale(text: str, cheie_start: str, cheie_sfarsit: str) -> list[tuple[float, float]]:
    """Intervalele raportate de filtru, cu cele lipite (sfârșitul unuia = începutul următorului) unite."""
    starturi = [float(x) for x in re.findall(cheie_start + r":\s*(-?[\d.]+)", text)]
    sfarsituri = [float(x) for x in re.findall(cheie_sfarsit + r":\s*(-?[\d.]+)", text)]
    brute = zip(starturi, sfarsituri + [float("inf")] * (len(starturi) - len(sfarsituri)), strict=False)
    out: list[tuple[float, float]] = []
    for a, b in sorted(brute):
        if out and a - out[-1][1] <= 0.1:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def masoara(cale: Path) -> dict[str, Any]:
    """O decodare: cadre negre, înghețate, tăceri și nivelul sonor (ebur128)."""
    r = ffmpeg.ruleaza([
        "-i", str(cale),
        "-vf", "blackdetect=d=0.1:pix_th=0.10,freezedetect=n=-60dB:d=0.5",
        "-af", "silencedetect=n=-50dB:d=0.3,ebur128=peak=true",
        "-f", "null", "-",
    ], fir=2)  # fmt: skip
    t = r.stderr
    negre = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", t)]
    inghetate = _intervale(t, r"lavfi\.freezedetect\.freeze_start", r"lavfi\.freezedetect\.freeze_end")
    linisti = _intervale(t, r"silence_start", r"silence_end")
    rez = t[t.rfind("Summary:") :]
    i = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", rez)
    p = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", rez)
    return {
        "negre": negre,
        "inghetate": inghetate,
        "linisti": linisti,
        "lufs": float(i.group(1)) if i and i.group(1) != "-inf" else -99.0,
        "varf": float(p.group(1)) if p and p.group(1) != "-inf" else -99.0,
    }


def _permis(a: float, b: float, intentionate: tuple[tuple[float, float], ...]) -> bool:
    return any(x <= a + 0.05 and b <= y + 0.05 for x, y in intentionate)


def probleme(cale: Path, a: Asteptari) -> tuple[list[Problema], dict[str, Any]]:
    out: list[Problema] = []
    info = ffmpeg.probe(cale)
    durata_fisier = float(info["format"].get("duration", 0))
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    au = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    if v is None:
        return [Problema("format", "fără pistă video")], {}
    if au is None:
        out.append(Problema("format", "fără pistă audio"))
    if v.get("codec_name") != "h264":
        out.append(Problema("format", f"codec video {v.get('codec_name')}, nu H.264"))
    if au is not None and au.get("codec_name") != "aac":
        out.append(Problema("format", f"codec audio {au.get('codec_name')}, nu AAC"))
    if (v.get("width"), v.get("height")) != (a.latime, a.inaltime):
        out.append(
            Problema("format", f"rezoluție {v.get('width')}×{v.get('height')}, nu {a.latime}×{a.inaltime}")
        )
    num, _, den = str(v.get("avg_frame_rate", "0/1")).partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    if abs(fps - a.cadre_pe_secunda) > 0.05:
        out.append(Problema("format", f"{fps:.2f} cadre pe secundă, nu {a.cadre_pe_secunda}"))
    if v.get("pix_fmt") != "yuv420p":
        out.append(Problema("format", f"format de pixeli {v.get('pix_fmt')}"))
    marime = cale.stat().st_size
    if marime > LIMITE_CANAL.get(a.canal, 287 * MB):
        out.append(Problema("format", f"{marime // MB} MB, peste limita canalului"))
    if au is not None:
        dv, da = float(v.get("duration", durata_fisier)), float(au.get("duration", durata_fisier))
        if abs(dv - da) > DESINCRONIZARE_MAX:
            out.append(Problema("sincronizare", f"sunetul durează {da:.2f} s, imaginea {dv:.2f} s"))
    m = masoara(cale)
    for x, y in m["negre"]:
        if y - x > NEGRU_MAX:
            out.append(Problema("cadre_negre", f"negru între {x:.2f} și {y:.2f} s"))
    for x, y in m["inghetate"]:
        y = min(y, durata_fisier)
        if y - x > INGHETAT_MAX and not _permis(x, y, a.intentionate):
            out.append(Problema("cadre_inghetate", f"imagine înghețată între {x:.2f} și {y:.2f} s"))
    if au is not None:
        for x, y in m["linisti"]:
            y = min(y, durata_fisier)
            if y - x > LINISTE_MAX:
                out.append(Problema("tacere", f"tăcere între {x:.2f} și {y:.2f} s"))
        if abs(m["lufs"] - sunet.TINTA_LUFS) > sunet.TOLERANTA_LU:
            out.append(Problema("nivel_sonor", f"{m['lufs']:.1f} LUFS, ținta {sunet.TINTA_LUFS:.0f} ± 1"))
        if m["varf"] > sunet.VARF_MAX_DBTP:
            out.append(Problema("nivel_sonor", f"vârf {m['varf']:.1f} dBTP, peste {sunet.VARF_MAX_DBTP:.0f}"))
    for e in a.ecrane:
        if not subtitrari.in_zona(e, a.canal, a.latime, a.inaltime):
            out.append(Problema("subtitrari", f"„{e.text}” iese din zona sigură ({e.inceput:.2f} s)"))
        if e.cutie[0] < 0 or e.cutie[2] > a.latime:
            out.append(Problema("subtitrari", f"„{e.text}” e tăiată la marginea imaginii"))
    return out, {**m, "durata": durata_fisier, "marime": marime, "fps": fps}


def verdict(cale: Path, a: Asteptari) -> tuple[validare.Verdict, dict[str, Any]]:
    p, masuri = probleme(cale, a)
    if not p:
        return validare.trece("G6", VERSIUNE, validare.Treapta.V0), masuri
    dovezi = [validare.Dovada(fragment="", regula=f"G6.{x.regula}", detalii=x.detalii) for x in p]
    return (
        validare.esec(
            "G6",
            VERSIUNE,
            validare.Treapta.V0,
            dovezi=dovezi,
            instructiune="Refă montajul: " + "; ".join(x.detalii for x in p[:4]),
        ),
        masuri,
    )


# --- verdictul editorial (F-editorial, decizia 7): separat de G6 ---
#
# G6 spune dacă fișierul e corect tehnic; verdictul editorial spune dacă arată ce trebuie. Verificările
# automate sunt demonstrabile (date, nu păreri): sigla ca singur subiect, același activ repetat, text ieșit
# din cadru, material lipsă, export al altei versiuni. Relevanța și compoziția cer ochi: operatorul sau un
# model care primește imaginile. Un MP4 cu G6 trecut poate fi respins editorial. Numerotarea scenelor e a
# storyboardului (0 = hook), aceeași ca în cererile de material din panou.

VERSIUNE_EDITORIAL = "1"
PLAT_CULORI, PLAT_PRAG = 8, 0.9  # [I] imagine „plată”: ≥ 90% din pixeli în 8 culori (text și siglă pe fundal)
ROLURI_SUBIECT = ("fotografie", "filmare", "ilustratie")
# etapa de reluat, în ordinea fluxului: se cere prima etapă afectată
ETAPE: dict[str, str] = {
    "material": "Încarcă materialul cerut",
    "selectie": "Revino la selecția materialelor",
    "machetare": "Revino la machetare",
    "montaj": "Refă montajul pentru versiunea curentă",
}
STARI_EVALUARE = {
    "neverificata": "neverificată",
    "autoevaluare": "autoevaluare",
    "evaluator": "evaluator separat",
    "operator": "operator",
}


@dataclass(frozen=True)
class Motiv:
    regula: (
        str  # sigla_singurul_subiect | activ_repetat | text_iesit | material_lipsa | alta_versiune | vizual
    )
    detalii: str
    etapa: str
    scene: tuple[int, ...] = ()


@dataclass(frozen=True)
class ScenaEditoriala:
    scena: int
    activ_id: str | None
    rol: str | None
    eticheta: str
    obligatorie: bool = True  # bătaie cu indicație vizuală proprie (hook-ul și apelul pot refolosi un cadru)


@dataclass(frozen=True)
class ImagineEditoriala:
    nume: str
    latime: int
    inaltime: int
    cutii_text: tuple[tuple[int, int, int, int], ...] | None  # None: geometria textului nu e cunoscută
    are_sigla: bool
    subiecte: int  # componente cu rol de subiect (fotografie, filmare, ilustrație)
    plata: float  # partea din pixeli în cele mai frecvente `PLAT_CULORI` culori


@dataclass(frozen=True)
class EvaluareVizuala:
    """Cine a judecat relevanța și compoziția. `modele`: generatorul și evaluatorul (coduri); `cu_imagini`:
    modelul a primit imaginile, nu doar text."""

    evaluator: Literal["operator", "model"] | None = None
    cu_imagini: bool = False
    modele: tuple[str, ...] = ()
    rezultat: Literal["trece", "respins", ""] = ""
    note: str = ""
    etapa: str = "selectie"


def stare_evaluare(e: EvaluareVizuala | None) -> str:
    """`neverificata` (nimeni sau un model doar cu text), `autoevaluare` (un singur model), `evaluator`
    (alt model, cu imagini) sau `operator`."""
    if e is None or e.evaluator is None:
        return "neverificata"
    if e.evaluator == "operator":
        return "operator"
    if not e.cu_imagini:
        return "neverificata"
    return "autoevaluare" if len(set(e.modele)) <= 1 else "evaluator"


def interval(scene: list[int] | tuple[int, ...]) -> str:
    """„Scenele 2–4”, „Scenele 1, 3”, „Scena 2”."""
    s = sorted(set(scene))
    if len(s) == 1:
        return f"Scena {s[0]}"
    if s == list(range(s[0], s[-1] + 1)):
        return f"Scenele {s[0]}–{s[-1]}"
    return "Scenele " + ", ".join(str(x) for x in s)


def plata(png: bytes) -> float:
    """Partea din pixeli acoperită de cele mai frecvente `PLAT_CULORI` culori (cuantizate la 32 de niveluri):
    aproape 1 pentru text și siglă pe fundal plin, mică pentru o fotografie."""
    img = Image.open(io.BytesIO(png)).convert("RGB")
    img.thumbnail((270, 270))
    culori = Counter((r >> 3, g >> 3, b >> 3) for r, g, b in img.getdata())  # type: ignore[attr-defined]
    total = sum(culori.values()) or 1
    return round(sum(n for _, n in culori.most_common(PLAT_CULORI)) / total, 3)


def _iesit(c: tuple[int, int, int, int], latime: int, inaltime: int) -> bool:
    return c[0] < 0 or c[1] < 0 or c[2] > latime or c[3] > inaltime


def judeca(
    *,
    scene: list[ScenaEditoriala],
    imagini: list[ImagineEditoriala],
    lipsa: list[tuple[int, str]],
    ecrane: Sequence[tuple[str, tuple[int, int, int, int]]] = (),
    cadru: tuple[int, int] = (1080, 1920),
    versiune_livrabil: int | None = None,
    versiune_export: int | None = None,
    are_export: bool = True,
) -> list[Motiv]:
    """Nucleul pur al verificărilor automate. Întoarce motivele de respingere (gol = trece)."""
    out: list[Motiv] = []
    if lipsa:
        out.append(Motiv(
            "material_lipsa",
            f"{interval([s for s, _ in lipsa])} nu au material: "
            + "; ".join(f"{s}: {subiect}" for s, subiect in lipsa),
            "material",
            tuple(s for s, _ in lipsa),
        ))  # fmt: skip
    elif not are_export and not imagini:
        out.append(Motiv("material_lipsa", "Nu există niciun export de judecat.", "material"))
    sigla = [s for s in scene if s.rol == "logo"]
    if sigla:
        acelasi = len({s.activ_id for s in sigla}) == 1 and len(sigla) > 1
        ce = "aceeași siglă" if acelasi else "sigla ca subiect"
        verb = "folosesc" if len(sigla) > 1 else "folosește"
        out.append(Motiv(
            "sigla_singurul_subiect", f"{interval([s.scena for s in sigla])} {verb} {ce}.", "selectie",
            tuple(s.scena for s in sigla),
        ))  # fmt: skip
    pe_activ: dict[str, list[ScenaEditoriala]] = {}
    for s in scene:
        if s.activ_id and s.obligatorie and s.rol != "logo":
            pe_activ.setdefault(s.activ_id, []).append(s)
    for grup in pe_activ.values():
        if len(grup) > 1:
            out.append(Motiv(
                "activ_repetat",
                f"{interval([s.scena for s in grup])} folosesc același material ({grup[0].eticheta}).",
                "selectie",
                tuple(s.scena for s in grup),
            ))  # fmt: skip
    for im in imagini:
        if im.are_sigla and im.subiecte == 0:
            out.append(Motiv(
                "sigla_singurul_subiect",
                f"Imaginea „{im.nume}” are doar text și siglă, fără fotografie "
                f"({im.plata:.0%} din pixeli în {PLAT_CULORI} culori).",
                "selectie" if not lipsa else "material",
            ))  # fmt: skip
        for c in im.cutii_text or ():
            if _iesit(c, im.latime, im.inaltime):
                out.append(
                    Motiv("text_iesit", f"Textul din „{im.nume}” iese din cadru ({list(c)}).", "machetare")
                )
    for text, c in ecrane:
        if _iesit(c, *cadru):
            out.append(Motiv("text_iesit", f"Subtitrarea „{text}” iese din cadru ({list(c)}).", "montaj"))
    if versiune_livrabil is not None and versiune_export is not None and versiune_export != versiune_livrabil:
        out.append(Motiv(
            "alta_versiune",
            f"Exportul aparține versiunii {versiune_export}, "
            f"iar livrabilul e la versiunea {versiune_livrabil}.",
            "montaj",
        ))  # fmt: skip
    return out


def mesaj(motive: list[Motiv]) -> tuple[str, str]:
    """(etapa de reluat, mesajul scurt): primul motiv al primei etape afectate + ce faci."""
    if not motive:
        return "", ""
    ordine = list(ETAPE)
    etapa = min((m.etapa for m in motive), key=ordine.index)
    primul = next(m for m in motive if m.etapa == etapa)
    return etapa, f"{primul.detalii.rstrip('.')}. {ETAPE[etapa]}."


# --- partea cu baza și fișierele


def cadre_pe_scene(video: Path, lm: lista.ListaMontaj) -> list[tuple[int, float, uuid.UUID, bytes]]:
    """Câte un cadru reprezentativ pe scenă (bătaie), extras din MP4 la mijlocul scenei:
    (scena, momentul, activul vizibil atunci, PNG)."""
    intervale: dict[int, tuple[float, float]] = {}
    for s in lm.scene:
        a, b = intervale.get(s.bataie, (s.inceput, s.sfarsit))
        intervale[s.bataie] = (min(a, s.inceput), max(b, s.sfarsit))
    out = []
    with tempfile.TemporaryDirectory(prefix="ama-cadre-") as d:
        for scena, (a, b) in sorted(intervale.items()):
            t = round((a + b) / 2, 3)
            activ = next(
                (s.activ_id for s in lm.scene if s.bataie == scena and s.inceput <= t <= s.sfarsit),
                next(s.activ_id for s in lm.scene if s.bataie == scena),
            )
            dest = Path(d) / f"{scena}.png"
            ffmpeg.ruleaza(["-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", str(dest)], timp_maxim=120)
            out.append((scena, t, activ, dest.read_bytes()))
    return out


def plansa(celule: list[tuple[str, str, bytes]], *, latime_celula: int = 270) -> bytes:
    """Planșa (contact sheet): câte o celulă pe cadru, cu eticheta (titlu + activul) sub imagine."""
    from PIL import ImageDraw, ImageFont

    font = ImageFont.truetype(str(subtitrari.cale_font("DejaVuSans-Bold.ttf")), 18)
    font_mic = ImageFont.truetype(str(subtitrari.cale_font("DejaVuSans.ttf")), 15)
    mini = []
    for titlu, activ, png in celule:
        img = Image.open(io.BytesIO(png)).convert("RGB")
        h = round(img.height * latime_celula / img.width)
        mini.append((titlu, activ, img.resize((latime_celula, h))))
    coloane = min(4, max(1, len(mini)))
    pad, eticheta = 12, 52
    h_rand = max(m[2].height for m in mini) + eticheta + pad
    randuri = (len(mini) + coloane - 1) // coloane
    foaie = Image.new("RGB", (coloane * (latime_celula + pad) + pad, randuri * h_rand + pad), "#F4F1EA")
    desen = ImageDraw.Draw(foaie)
    for k, (titlu, activ, img) in enumerate(mini):
        x = pad + (k % coloane) * (latime_celula + pad)
        y = pad + (k // coloane) * h_rand
        foaie.paste(img, (x, y))
        desen.text((x, y + img.height + 6), titlu, font=font, fill="#1E1E1E")
        text = activ if font_mic.getlength(activ) <= latime_celula else activ[:34] + "…"
        desen.text((x, y + img.height + 30), text, font=font_mic, fill="#4A4A4A")
    out = io.BytesIO()
    foaie.save(out, "PNG")
    return out.getvalue()


def _eticheta(a: Any) -> str:
    if a is None:
        return "activ inexistent"
    rol = {"logo": "sigla", "fotografie": "fotografie", "filmare": "filmare", "ilustratie": "ilustrație"}
    return f"{rol.get(a.rol_vizual or '', a.rol_vizual or 'activ')}: {a.subiect or a.nume_original}"[:80]


def _imagine(db: Session, a: Any) -> tuple[ImagineEditoriala, bytes]:
    from app.media import biblioteca
    from app.media.modele import Activ

    png = biblioteca.citeste_fisier(a)
    gen = a.generare or {}
    w, h = gen.get("dimensiuni") or Image.open(io.BytesIO(png)).size
    cutii = gen.get("cutii_text")
    roluri = []
    for c in (a.licenta or {}).get("componente") or []:
        if c.get("activ_id"):
            x = db.get(Activ, uuid.UUID(c["activ_id"]))
            roluri.append(x.rol_vizual if x is not None else None)
    return (
        ImagineEditoriala(
            nume=a.nume_original,
            latime=int(w),
            inaltime=int(h),
            cutii_text=tuple(tuple(c) for c in cutii) if cutii is not None else None,
            are_sigla="logo" in roluri,
            subiecte=sum(r in ROLURI_SUBIECT for r in roluri),
            plata=plata(png),
        ),
        png,
    )


def verdict_editorial(
    db: Session,
    tenant_id: uuid.UUID,
    livrabil_id: uuid.UUID,
    *,
    randare: Any = None,
    imagini: list[Any] | None = None,
    evaluare: EvaluareVizuala | None = None,
) -> dict[str, Any]:
    """Verdictul editorial al livrabilului, separat de G6: pe MP4 (câte un cadru pe scenă, la mijloc) și pe
    PNG-urile finale (`imagini`: activele exportate). Compune planșa, o înregistrează ca activ `export` și
    persistă verdictul în `randari.control["editorial"]` (dacă există randare) și în audit."""
    from sqlalchemy import select

    from app import productie
    from app.media import biblioteca, cereri, licente
    from app.media.modele import Activ, Randare
    from app.operare import audit

    lv = productie.citeste(db, livrabil_id)
    versiune = lv.versiune if lv is not None else None
    if randare is None:
        randare = db.scalars(
            select(Randare)
            .where(Randare.tenant_id == tenant_id, Randare.livrabil_id == livrabil_id,
                   Randare.calitate == "final", Randare.activ_id.is_not(None))
            .order_by(Randare.creat_la.desc(), Randare.id.desc())
            .limit(1)
        ).first()  # fmt: skip
    lipsa = sorted({(c.scena, c.subiect) for c in cereri.deschise(db, tenant_id, livrabil_id)})
    scene: list[ScenaEditoriala] = []
    ecrane: list[tuple[str, tuple[int, int, int, int]]] = []
    celule: list[tuple[str, str, bytes]] = []
    cadre_info: list[dict[str, Any]] = []
    cadru = (1080, 1920)
    versiune_export = None
    if randare is not None and randare.activ_id is not None:
        lm = lista.ListaMontaj.model_validate(randare.lista)
        cadru = (lm.latime, lm.inaltime)
        versiune_export = (randare.masuratori or {}).get("versiune_continut")
        sb = (randare.masuratori or {}).get("storyboard") or {}
        obligatorii = {s["scena"]: s.get("obligatorie", True) for s in sb.get("scene", [])}
        lipsa += [(s["scena"], s["subiect"]) for s in sb.get("scene", []) if s.get("sursa") == "lipsa"]
        lipsa = sorted(set(lipsa))
        ultima = max((s.bataie for s in lm.scene), default=0)
        mp4 = db.get(Activ, randare.activ_id)
        if mp4 is not None:
            from app.media import regizor

            for scena, t, activ_id, png in cadre_pe_scene(regizor.cale(mp4), lm):
                a = db.get(Activ, activ_id)
                et = _eticheta(a)
                scene.append(ScenaEditoriala(
                    scena, str(activ_id), a.rol_vizual if a is not None else None, et,
                    obligatorii.get(scena, 0 < scena < ultima),
                ))  # fmt: skip
                celule.append((f"Scena {scena} · {t:.1f} s", et, png))
                cadre_info.append({"scena": scena, "moment": t, "activ_id": str(activ_id), "activ": et,
                                   "plata": plata(png)})  # fmt: skip
        if lm.texte:
            ecrane = [(e.text, e.cutie) for e in subtitrari.grupeaza(lm)]
    info_imagini = []
    for a in imagini or []:
        im, png = _imagine(db, a)
        info_imagini.append(im)
        sigla = "da" if im.are_sigla else "nu"
        celule.append((f"Imagine · {im.nume}"[:30], f"{im.subiecte} subiecte, sigla: {sigla}", png))
    motive = judeca(
        scene=scene, imagini=info_imagini, lipsa=lipsa, ecrane=ecrane, cadru=cadru,
        versiune_livrabil=versiune, versiune_export=versiune_export, are_export=randare is not None,
    )  # fmt: skip
    st = stare_evaluare(evaluare)
    if evaluare is not None and evaluare.rezultat == "respins" and st != "neverificata":
        motive.append(Motiv("vizual", evaluare.note or "Relevanța sau compoziția nu convin.", evaluare.etapa))
    etapa, text = mesaj(motive)
    plansa_id = None
    if celule:
        foaie = plansa(celule)
        p = biblioteca.incarca(
            db, tenant_id, foaie, nume_original=f"plansa-{livrabil_id}.png", sursa="control",
            utilizator_id=None, rol_vizual="export", descriere=f"planșa editorială, livrabilul {livrabil_id}",
            licenta={"tip": "productie_proprie", "statut": licente.STATUT_OK,
                     "componente": [{"descriere": "cadre din exporturile livrabilului"}]},
            generare={"livrabil_id": str(livrabil_id), "versiune": versiune},
        )  # fmt: skip
        plansa_id = str(p.id)
    date: dict[str, Any] = {
        "validator": "editorial",
        "versiune": VERSIUNE_EDITORIAL,
        "rezultat": "respins" if motive else "trece",
        "motive": [
            {"regula": m.regula, "detalii": m.detalii, "etapa": m.etapa, "scene": list(m.scene)}
            for m in motive
        ],
        "etapa": etapa,
        "etapa_text": ETAPE.get(etapa, ""),
        "mesaj": text,
        "evaluare_vizuala": {
            "stare": st,
            "eticheta": STARI_EVALUARE[st],
            "evaluator": evaluare.evaluator if evaluare else None,
            "rezultat": evaluare.rezultat if evaluare and st != "neverificata" else "",
            "note": evaluare.note if evaluare else "",
        },
        "cadre": cadre_info,
        "imagini": [
            {"nume": i.nume, "subiecte": i.subiecte, "sigla": i.are_sigla, "plata": i.plata}
            for i in info_imagini
        ],
        "plansa_activ_id": plansa_id,
        "versiune_livrabil": versiune,
        "versiune_export": versiune_export,
        "randare_id": str(randare.id) if randare is not None else None,
    }
    if randare is not None:
        randare.control = {**(randare.control or {}), "editorial": date}
        db.flush()
    audit.record(
        db, "livrabil.verdict_editorial", obiect_tip="livrabil", obiect_id=livrabil_id, tenant_id=tenant_id,
        rezultat="ok" if not motive else "refuzat",
        detalii={"rezultat": date["rezultat"], "etapa": etapa, "mesaj": text, "versiune": versiune},
    )  # fmt: skip
    return date
