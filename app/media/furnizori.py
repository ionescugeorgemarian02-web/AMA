"""Furnizorii de imagini și cadre (F8.4, docs/14 §14.3): stock cu licență și generare, în spatele unor
adaptoare.

Ordinea surselor: materialele clientului (portal), stock cu licență, imagini generate (fundal / ilustrație,
fără
text), grafică din șabloane (F8.10). Fiecare activ adus de aici intră în bibliotecă cu licența completă:
stock-ul
cu identificatorul, autorul și o copie a licenței de la data descărcării; generarea cu promptul, modelul și
sămânța.

Până la migrare, ambii furnizori sunt SIMULAȚI și deterministi (D-007): imagini desenate local (Pillow),
clipuri
video produse local (ffmpeg). Furnizorii reali (API-uri de stock, cota gratuită de generare): la migrare.
"""

import datetime as dt
import hashlib
import io
import os
import random
import re
import tempfile
import uuid
from dataclasses import dataclass
from typing import Protocol

from PIL import Image, ImageDraw, ImageFilter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.media import biblioteca, ffmpeg
from app.media.modele import Activ


@dataclass(frozen=True)
class RezultatStock:
    furnizor: str
    identificator: str
    autor: str
    url: str
    tip: str  # foto / video
    licenta_text: str
    descriere: str
    url_fisier: str = ""  # adresa de descărcare (furnizorii reali); `url` e pagina publică a fișierului
    licenta: str = ""  # numele scurt al licenței (ex. „CC BY-SA 4.0”), pentru atribuire
    url_licenta: str = ""


class FurnizorStock(Protocol):
    nume: str

    def cauta(self, interogare: str, *, tip: str = "foto", n: int = 3) -> list[RezultatStock]: ...

    def descarca(self, r: RezultatStock) -> bytes: ...


class GeneratorImagini(Protocol):
    nume: str
    model: str

    def genereaza(self, prompt: str, *, samanta: int, latime: int, inaltime: int) -> bytes: ...


def _rng(*parti: object) -> random.Random:
    return random.Random(int(hashlib.sha256("|".join(map(str, parti)).encode()).hexdigest()[:16], 16))  # noqa: S311


def imagine_abstracta(cheie: str, latime: int, inaltime: int) -> bytes:
    """O imagine JPEG deterministă (forme moi, culori calde), fără text. Folosită de furnizorii simulați."""
    r = _rng(cheie)
    baza = tuple(r.randint(60, 200) for _ in range(3))
    img = Image.new("RGB", (latime, inaltime), baza)
    d = ImageDraw.Draw(img)
    for _ in range(14):
        x, y = r.randint(0, latime), r.randint(0, inaltime)
        raza = r.randint(latime // 10, latime // 3)
        culoare = tuple(r.randint(30, 240) for _ in range(3))
        d.ellipse((x - raza, y - raza, x + raza, y + raza), fill=culoare)
    img = img.filter(ImageFilter.GaussianBlur(radius=max(2, latime // 120)))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88)
    return out.getvalue()


class StockSimulat:
    """# SIMULAT: un catalog de stock determinist (fotografii și clipuri verticale), cu licență de tip CC0."""

    nume = "stock-simulat"
    LICENTA = (
        "Licență de probă (SIMULAT): utilizare comercială permisă, fără atribuire obligatorie, "
        "fără revânzare "
        "a fișierului ca atare. Text salvat la data descărcării."
    )

    def cauta(self, interogare: str, *, tip: str = "foto", n: int = 3) -> list[RezultatStock]:
        cheie = re.sub(r"[^a-z0-9]+", "-", interogare.lower()).strip("-")[:40] or "x"
        return [
            RezultatStock(
                self.nume,
                f"{tip}-{cheie}-{i}",
                f"Autor Simulat {i + 1}",
                f"https://stock.exemplu.test/{tip}/{cheie}-{i}",
                tip,
                self.LICENTA,
                f"{interogare} ({tip} {i + 1})",
            )
            for i in range(n)
        ]

    def descarca(self, r: RezultatStock) -> bytes:
        if r.tip == "video":
            return ffmpeg.clip_sintetic(r.identificator, durata=6.0)
        return imagine_abstracta(r.identificator, 1080, 1920)


class GeneratorSimulat:
    """# SIMULAT: imagini generate local, deterministe după prompt și sămânță."""

    nume = "generator-simulat"
    model = "simulat-imagine-1"

    def genereaza(self, prompt: str, *, samanta: int, latime: int, inaltime: int) -> bytes:
        return imagine_abstracta(f"{prompt}|{samanta}", latime, inaltime)


# 14.3: fără text în imagine, fără persoane reale, fără mărci ale altora, fără stilul unui artist numit [I]
INTERZISE_PROMPT = (
    (re.compile(r"\b(text|scris|literele|titlu|logo|sigl[aă])\b", re.I), "fără text sau logo în imagine"),
    (re.compile(r"\bîn stilul (lui|unui|artistului)\b|\bstyle of\b", re.I), "fără stilul unui artist numit"),
    (re.compile(r"\b(portret|chipul|fotografie realistă a) (lui|unei|unui)\b", re.I), "fără persoane reale"),
    (re.compile(r"\b(starbucks|nescafe|coca-cola|nike|apple|mcdonald)", re.I), "fără mărcile altora"),
)


class PromptRefuzat(ValueError):
    pass


def probleme_prompt(prompt: str) -> list[str]:
    return [motiv for rx, motiv in INTERZISE_PROMPT if rx.search(prompt)]


def stock_din_mediu() -> FurnizorStock:
    """Furnizorul de stock după mediu. `AMA_STOCK` (pexels / pixabay / commons / simulat) îl alege explicit;
    altfel Pexels dacă există `PEXELS_API_KEY`, apoi Pixabay (`PIXABAY_API_KEY`), apoi Wikimedia Commons (fără
    cheie). În `AMA_ENV=test` rămâne `StockSimulat` dacă nu e cerut explicit (CI fără rețea)."""
    cerut = os.environ.get("AMA_STOCK", "").strip().lower()
    if not cerut:
        if get_settings().env == "test":
            return StockSimulat()
        if os.environ.get("PEXELS_API_KEY", "").strip():
            cerut = "pexels"
        elif os.environ.get("PIXABAY_API_KEY", "").strip():
            cerut = "pixabay"
        else:
            cerut = "commons"
    if cerut == "pexels":
        from app.media.stock_pexels import StockPexels

        return StockPexels()
    if cerut == "pixabay":
        from app.media.stock_pixabay import StockPixabay

        return StockPixabay()
    if cerut == "commons":
        from app.media.stock_commons import StockCommons

        return StockCommons()
    if cerut == "simulat":
        return StockSimulat()
    raise ValueError(f"AMA_STOCK necunoscut: {cerut}")


_stock: FurnizorStock | None = None  # None = ales după mediu la prima folosire
_generator: GeneratorImagini = GeneratorSimulat()


def seteaza(stock: FurnizorStock | None = None, generator: GeneratorImagini | None = None) -> None:
    """`stock=None` = implicitul (`stock_din_mediu`, în teste `StockSimulat`)."""
    global _stock, _generator
    _stock = stock
    _generator = generator or GeneratorSimulat()


def furnizor_stock() -> FurnizorStock:
    global _stock
    if _stock is None:
        _stock = stock_din_mediu()
    return _stock


def cauta_stock(interogare: str, *, tip: str = "foto", n: int = 3) -> list[RezultatStock]:
    return furnizor_stock().cauta(interogare, tip=tip, n=n)


def aduce_stock(db: Session, tenant_id: uuid.UUID, r: RezultatStock) -> Activ:
    """Descarcă și înregistrează, cu identificatorul, autorul și copia licenței de la data descărcării.
    Un fișier deja adus (același furnizor și identificator) nu se mai descarcă."""
    existent = db.execute(
        select(Activ).where(
            Activ.tenant_id == tenant_id,
            Activ.sursa == "stock",
            Activ.licenta["furnizor"].astext == r.furnizor,
            Activ.licenta["identificator"].astext == r.identificator,
        )
    ).scalar_one_or_none()
    if existent is not None:
        return existent
    corp = furnizor_stock().descarca(r)
    return biblioteca.incarca(
        db,
        tenant_id,
        corp,
        nume_original=f"{r.identificator}.{'mp4' if r.tip == 'video' else 'jpg'}",
        sursa="stock",
        utilizator_id=None,
        descriere=r.descriere,
        licenta={
            "tip": "stock",
            "statut": "verificata",
            "furnizor": r.furnizor,
            "identificator": r.identificator,
            "autor": r.autor,
            "url": r.url,
            "copie": r.licenta_text,
            **({"licenta": r.licenta} if r.licenta else {}),
            **({"url_licenta": r.url_licenta} if r.url_licenta else {}),
            "descarcat_la": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        },
    )


def genereaza_imagine(
    db: Session, tenant_id: uuid.UUID, prompt: str, *, samanta: int, latime: int = 1080, inaltime: int = 1920
) -> Activ:
    """Imagine generată (fundal / ilustrație): promptul, modelul și sămânța se păstrează; eticheta AI e
    obligatorie (G11)."""
    p = probleme_prompt(prompt)
    if p:
        raise PromptRefuzat("; ".join(p))
    corp = _generator.genereaza(prompt, samanta=samanta, latime=latime, inaltime=inaltime)
    return biblioteca.incarca(
        db,
        tenant_id,
        corp,
        nume_original="generat.jpg",
        sursa="generat",
        utilizator_id=None,
        descriere=prompt[:500],
        licenta={
            "tip": "generat",
            "statut": "verificata",
            "furnizor": _generator.nume,
            "model": _generator.model,
            "prompt": prompt,
            "samanta": samanta,
            "conditii": "uz comercial permis de condițiile furnizorului (SIMULAT; de verificat la migrare)",
            "eticheta_ai": True,
        },
        generare={
            "furnizor": _generator.nume,
            "model": _generator.model,
            "prompt": prompt,
            "samanta": samanta,
        },
    )


# --- muzica (F8.7, 14.8): bibliotecă cu licență clară, fiecare piesă cu fișierul ei de licență


class BibliotecaMuzica(Protocol):
    nume: str

    def piesa(self, stare: str, durata: float) -> tuple[bytes, dict[str, str]]: ...


class MuzicaSimulata:
    """# SIMULAT: o piesă instrumentală sintetizată local (acorduri lente), deterministă după „stare”."""

    nume = "muzica-simulata"

    def piesa(self, stare: str, durata: float) -> tuple[bytes, dict[str, str]]:
        r = _rng(stare)
        baza = r.choice([196.0, 220.0, 247.0, 262.0])
        expr = "+".join(
            f"0.12*sin(2*PI*{baza * m:.2f}*t)*(0.6+0.4*sin(2*PI*{0.25 * (k + 1):.2f}*t))"
            for k, m in enumerate((1.0, 1.25, 1.5, 2.0))
        )
        with tempfile.TemporaryDirectory() as d:
            iesire = f"{d}/m.wav"
            ffmpeg.ruleaza(["-f", "lavfi", "-i", f"aevalsrc={expr}:s=48000:d={durata:.2f}", "-ac", "1",
                            "-c:a", "pcm_s16le", iesire])  # fmt: skip
            with open(iesire, "rb") as f:
                corp = f.read()
        return corp, {
            "identificator": f"piesa-{stare}",
            "autor": "Compozitor Simulat",
            "copie": "Licență de probă: sincronizare în video comercial permisă pe orice platformă.",
        }


_muzica: BibliotecaMuzica | None = None


def seteaza_muzica(b: BibliotecaMuzica | None) -> None:
    """`None` = implicitul: compoziția locală (`muzica_locala`), iar în teste piesa simulată (rapidă)."""
    global _muzica
    _muzica = b


def _biblioteca_muzica() -> BibliotecaMuzica:
    if _muzica is not None:
        return _muzica
    if get_settings().env == "test":
        return MuzicaSimulata()
    from app.media.muzica_locala import MuzicaLocala

    return MuzicaLocala()


def aduce_muzica(db: Session, tenant_id: uuid.UUID, stare: str = "calm", durata: float = 20.0) -> Activ:
    biblioteca_muzica = _biblioteca_muzica()
    corp, lic = biblioteca_muzica.piesa(stare, durata)
    return biblioteca.incarca(
        db, tenant_id, corp, nume_original=f"{lic['identificator']}.wav", sursa="muzica", utilizator_id=None,
        descriere=f"muzică {stare}",
        licenta={"tip": "muzica", "statut": "verificata", "furnizor": biblioteca_muzica.nume, **lic},
    )  # fmt: skip
