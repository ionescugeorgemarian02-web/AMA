"""Generatorul video extern (F16.5, docs/14 §14.2): un adaptor care se activează doar când există buget.

Reguli (D-026):
1. Oprit implicit (`AMA_VIDEO_EXTERN_ACTIV=false`): fără buget, nu se cheamă nimic.
2. Doar inserturi de 3–6 s (14.2), cu promptul verificat ca la imagini (fără text, persoane reale, mărci).
3. Furnizorul trebuie să declare drept de uz comercial și lipsa filigranului; altfel e refuzat înainte de
apel.
4. Bugetul: costul (secunde × tarif) se REZERVĂ în `video_generari` înainte de apel, sub un zăvor pe client;
   rezervările și generările reușite din luna curentă nu trec de plafonul lunar al clientului. Peste plafon:
   rând `refuzat`, fără apel. Un apel eșuat eliberează rezervarea (`esuat`, nu se numără).
5. Clipul intră în bibliotecă cu licența `generat` (furnizor, model, prompt, sămânță, condiții) și
eticheta AI.

# SIMULAT: `GeneratorVideoSimulat` (clip local prin FFmpeg, cost declarat); furnizorul real, tariful și
# condițiile
lui se verifică la migrare.
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import DateTime, Numeric, Text, func, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.config import get_settings
from app.ids import new_id
from app.media import biblioteca, ffmpeg, furnizori
from app.media.modele import Activ, BazaMedia
from app.operare import audit, urme

DURATA_MIN, DURATA_MAX = 3.0, 6.0


class GenerareVideo(BazaMedia):
    __tablename__ = "video_generari"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    prompt: Mapped[str] = mapped_column(Text)
    durata_sec: Mapped[float] = mapped_column(Numeric(4, 1))
    furnizor: Mapped[str] = mapped_column(Text)
    cost_bani: Mapped[int] = mapped_column()
    stare: Mapped[str] = mapped_column(Text)
    motiv: Mapped[str] = mapped_column(Text, default="")
    activ_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


@dataclass(frozen=True)
class ConditiiFurnizor:
    drept_comercial: bool
    filigran: bool
    text: str


class GeneratorVideo(Protocol):
    nume: str
    model: str
    conditii: ConditiiFurnizor

    def genereaza(self, prompt: str, *, durata: float, samanta: int, latime: int, inaltime: int) -> bytes: ...


class GeneratorVideoSimulat:
    """# SIMULAT: clip vertical local (FFmpeg), determinist după prompt și sămânță."""

    nume = "video-simulat"
    model = "simulat-video-1"
    conditii = ConditiiFurnizor(
        True, False, "uz comercial permis, fără filigran (SIMULAT; de verificat la migrare)"
    )

    def genereaza(self, prompt: str, *, durata: float, samanta: int, latime: int, inaltime: int) -> bytes:
        return ffmpeg.clip_sintetic(f"{prompt}|{samanta}", durata=durata, latime=latime, inaltime=inaltime)


class GeneratorOprit(RuntimeError):
    """Adaptorul nu e activ (fără buget)."""


class BugetDepasit(RuntimeError):
    pass


class GenerareRefuzata(ValueError):
    pass


_generator: GeneratorVideo = GeneratorVideoSimulat()


def seteaza(g: GeneratorVideo | None) -> None:
    global _generator
    _generator = g or GeneratorVideoSimulat()


def cost(durata: float) -> int:
    """Nucleu pur: costul în bani, pe secundă începută."""
    return int(-(-durata // 1)) * get_settings().video_extern_cost_secunda_bani


def cheltuit_luna(db: Session, tenant_id: uuid.UUID, acum: dt.datetime) -> int:
    inceput = acum.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    q = select(func.coalesce(func.sum(GenerareVideo.cost_bani), 0)).where(
        GenerareVideo.tenant_id == tenant_id,
        GenerareVideo.stare.in_(("rezervat", "gata")),
        GenerareVideo.la >= inceput,
    )
    return int(db.execute(q).scalar_one())


def _rand(
    db: Session, tenant_id: uuid.UUID, prompt: str, durata: float, c: int, stare: str, motiv: str = ""
) -> GenerareVideo:
    g = GenerareVideo(id=new_id(), tenant_id=tenant_id, prompt=prompt, durata_sec=durata,
    furnizor=_generator.nume,
                      cost_bani=c, stare=stare, motiv=motiv[:500], la=dt.datetime.now(dt.UTC))  # fmt: skip
    db.add(g)
    db.flush()
    return g


def genereaza_insert(
    db: Session, tenant_id: uuid.UUID, prompt: str, *, durata: float = 4.0, samanta: int = 1
) -> tuple[GenerareVideo, Activ | None]:
    """Un insert video generat: verificări, rezervarea costului, apelul, activul cu licența. Întoarce rândul
    (`gata`, `esuat` sau `refuzat`) și activul (doar la `gata`)."""
    s = get_settings()
    if not s.video_extern_activ:
        raise GeneratorOprit("generatorul video extern e oprit (fără buget)")
    if not DURATA_MIN <= durata <= DURATA_MAX:
        raise GenerareRefuzata(f"inserturile au {DURATA_MIN:g}–{DURATA_MAX:g} s, nu {durata:g} s")
    pr = furnizori.probleme_prompt(prompt)
    if pr:
        raise furnizori.PromptRefuzat("; ".join(pr))
    cond = _generator.conditii
    if not cond.drept_comercial or cond.filigran:
        raise GenerareRefuzata("furnizorul nu dă drept de uz comercial fără filigran")
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('video_extern:' || :t))"), {"t": str(tenant_id)})
    c, acum = cost(durata), dt.datetime.now(dt.UTC)
    folosit = cheltuit_luna(db, tenant_id, acum)
    if folosit + c > s.video_extern_plafon_lunar_bani:
        g = _rand(db, tenant_id, prompt, durata, c, "refuzat",
                  f"plafon lunar: {folosit} + {c} > {s.video_extern_plafon_lunar_bani} bani")  # fmt: skip
        audit.record(db, "video_extern.refuzat", obiect_tip="video_generare", obiect_id=g.id,
        tenant_id=tenant_id,
                     rezultat="refuzat", detalii={"cost_bani": c, "folosit_bani": folosit})  # fmt: skip
        return g, None
    g = _rand(db, tenant_id, prompt, durata, c, "rezervat")
    with urme.span("media", "video_extern.genereaza", db=db, obiect_tip="video_generare", obiect_id=g.id,
                   intrari={"durata": durata, "cost_bani": c}) as sp:  # fmt: skip
        try:
            corp = _generator.genereaza(prompt, durata=durata, samanta=samanta, latime=1080, inaltime=1920)
        except Exception as exc:
            g.stare, g.motiv = "esuat", f"{type(exc).__name__}: {exc}"[:500]
            sp.rezultat, sp.cod = "esec", type(exc).__name__
            db.flush()
            return g, None
        a = biblioteca.incarca(
            db, tenant_id, corp, nume_original="insert-generat.mp4", sursa="generat", utilizator_id=None,
            descriere=prompt[:500],
            licenta={"tip": "generat", "statut": "verificata", "furnizor": _generator.nume, "model":
            _generator.model,
                     "prompt": prompt, "samanta": samanta, "conditii": cond.text, "eticheta_ai": True},
            generare={"furnizor": _generator.nume, "model": _generator.model, "prompt": prompt,
            "samanta": samanta,
                      "cost_bani": c, "video_generare_id": str(g.id)},
        )  # fmt: skip
        g.stare, g.activ_id = "gata", a.id
        db.flush()
        sp.iesiri = {"activ_id": str(a.id)}
    audit.record(db, "video_extern.generat", obiect_tip="video_generare", obiect_id=g.id, tenant_id=tenant_id,
                 detalii={"cost_bani": c, "durata": durata})  # fmt: skip
    return g, a
