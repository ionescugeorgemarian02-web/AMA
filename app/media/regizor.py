"""Regizorul (F8.5, docs/14 §14.5 pasul 4): de la scriptul pe bătăi și vocea verificată la lista de montaj.

Modelul (profilul `creatie`, prin gateway) alege doar cadrul și mișcarea pe fiecare bătaie, dintr-o listă
numerotată de active CU licență. Momentele le pune programul, din vocea reală: bătaia i ține de la primul
cuvânt
al frazei i până la primul cuvânt al frazei următoare (tăietura cade pe bătaie); prima începe la 0, ultima se
termină cu vocea plus o coadă scurtă. O alegere invalidă (bătaie lipsă, material inexistent) se înlocuiește
determinist, prin rotație, și se notează.
"""

import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app import continut, gateway
from app.config import get_settings
from app.logging import get_logger
from app.media import audio, ffmpeg, licente, lista, transcriere
from app.media.modele import Activ
from app.operare.motor import Prioritate

log = get_logger("app.media")
COADA = 0.6  # [I] secunde după ultimul cuvânt


class AlegereScena(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bataie: int = Field(ge=0)
    material: int = Field(ge=0)
    miscare: Literal["static", "zoom_in", "zoom_out", "panoramare_stanga", "panoramare_dreapta"] = "static"


class PlanRegizor(gateway.Iesire):
    scene: list[AlegereScena] = Field(min_length=1, max_length=10)
    coperta: str = Field(default="", max_length=60)


def fraze_din_script(campuri: dict[str, Any]) -> list[str]:
    """Bătăile rostite, în ordine: hook, vocea bătăilor, apelul la acțiune (conținutul E2, F6.4)."""
    out = [str(campuri.get("hook", "")).strip()]
    out += [str(b.get("voce", "")).strip() for b in campuri.get("batai", [])]
    out.append(str(campuri.get("cta", "")).strip())
    return [f for f in out if f]


def cale(a: Activ) -> Path:
    return Path(get_settings().media_dir) / a.cale


def info_activ(a: Activ) -> lista.InfoActiv:
    durata: float | None = None
    if a.categorie == "audio":
        durata = audio.citeste(cale(a).read_bytes()).durata
    elif a.categorie == "video":
        durata = ffmpeg.durata(cale(a))
    return lista.InfoActiv(a.categorie, not licente.probleme(a.licenta), durata)


def info_active(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, lista.InfoActiv]:
    out = {}
    for i in ids:
        a = db.get(Activ, i)
        if a is not None:
            out[i] = info_activ(a)
    return out


def texte(fraze: list[str], al: transcriere.Aliniere) -> list[lista.Text]:
    """Cuvintele afișate (cu majusculele și punctuația lor), cu momentele din aliniere."""
    out: list[lista.Text] = []
    k = 0
    for fi, f in enumerate(fraze):
        for tok in f.split():
            n = len(transcriere.jetoane(tok))
            if not n:
                continue
            c0, c1 = al.cuvinte[k], al.cuvinte[k + n - 1]
            k += n
            sfarsit = max(c1.sfarsit, c0.inceput + 0.05)
            out.append(lista.Text(cuvant=tok[:40], inceput=c0.inceput, sfarsit=sfarsit, fraza=fi))
    return out


def momente_batai(fraze: list[str], al: transcriere.Aliniere, durata: float) -> list[tuple[float, float]]:
    inceputuri: list[float] = []
    k = 0
    for f in fraze:
        inceputuri.append(al.cuvinte[k].inceput if k < len(al.cuvinte) else durata)
        k += len(transcriere.jetoane(f))
    inceputuri[0] = 0.0
    return [(round(a, 3), round(b, 3)) for a, b in zip(inceputuri, [*inceputuri[1:], durata], strict=True)]


def _repara(plan: PlanRegizor, n_batai: int, n_mat: int) -> tuple[list[AlegereScena], list[str]]:
    note: list[str] = []
    pe_bataie = {s.bataie: s for s in plan.scene if s.bataie < n_batai}
    out: list[AlegereScena] = []
    for b in range(n_batai):
        s = pe_bataie.get(b)
        if s is None or s.material >= n_mat:
            note.append(f"bătaia {b}: alegere invalidă, înlocuită prin rotație")
            s = AlegereScena(bataie=b, material=b % n_mat, miscare="zoom_in")
        out.append(s)
    return out, note


def construieste(
    *,
    format: str,
    canal: str,
    fraze: list[str],
    naratiune: transcriere.NaratiuneVerificata,
    materiale: list[Activ],
    alegeri: list[AlegereScena],
    coperta: str = "",
    muzica: Activ | None = None,
) -> lista.ListaMontaj:
    """Nucleul determinist: alegerile + momentele vocii -> lista de montaj."""
    durata = round(naratiune.naratiune.durata + COADA, 3)
    intervale = momente_batai(fraze, naratiune.aliniere, durata)
    scene = []
    for (a, b), s in zip(intervale, alegeri, strict=True):
        m = materiale[s.material]
        # formatul B e „imagini în mișcare”: o fotografie nu stă niciodată pe loc (altfel G6 o vede înghețată)
        miscare = (s.miscare if s.miscare != "static" else "zoom_in") if m.categorie == "foto" else "static"
        scene.append(lista.Scena(activ_id=m.id, inceput=a, sfarsit=b, miscare=miscare, bataie=s.bataie))
    return lista.ListaMontaj(
        format=format,
        canal=canal,
        durata=durata,
        voce=lista.Pista(activ_id=naratiune.naratiune.activ.id, durata=naratiune.naratiune.durata),
        muzica=lista.Muzica(activ_id=muzica.id) if muzica is not None else None,
        scene=scene,
        texte=texte(fraze, naratiune.aliniere),
        coperta=lista.Coperta(text=(coperta or fraze[0])[:60]),
    )


class ListaInvalida(ValueError):
    def __init__(self, probleme: list[str]) -> None:
        super().__init__("; ".join(probleme))
        self.probleme = probleme


def regizeaza(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    fraze: list[str],
    naratiune: transcriere.NaratiuneVerificata,
    materiale: list[Activ],
    format: str = "A",
    canal: str = "tiktok",
    muzica: Activ | None = None,
    livrabil_id: uuid.UUID | None = None,
) -> lista.ListaMontaj:
    """Cere alegerile modelului, construiește lista și o validează (`ListaInvalida` dacă nu trece)."""
    folosibile = [m for m in materiale if not licente.probleme(m.licenta)]
    if not folosibile:
        raise ListaInvalida(["niciun material cu licență"])
    continut.prompturi.asigura()
    r = gateway.apeleaza(
        db,
        prompt="media.regizor@1",
        schema=PlanRegizor,
        tenant_id=tenant_id,
        componenta="media.regizor",
        livrabil_id=livrabil_id,
        prioritate=Prioritate.P2,
        max_tokeni=800,
        variabile={
            "format": format,
            "batai": "\n".join(f"{i}. {f}" for i, f in enumerate(fraze)),
            "materiale": "\n".join(
                f"{i}: {m.descriere or m.nume_original}" for i, m in enumerate(folosibile)
            ),
        },
    )
    if not isinstance(r.iesire, PlanRegizor):
        raise TypeError("ieșirea nu respectă schema promptului")
    alegeri, note = _repara(r.iesire, len(fraze), len(folosibile))
    if note:
        log.warning("regizorul a primit alegeri invalide", extra={"note": note[:5]})
    lm = construieste(format=format, canal=canal, fraze=fraze, naratiune=naratiune, materiale=folosibile,
                      alegeri=alegeri, coperta=r.iesire.coperta, muzica=muzica)  # fmt: skip
    ids = {s.activ_id for s in lm.scene} | {lm.voce.activ_id} | ({lm.muzica.activ_id} if lm.muzica else set())
    p = lista.probleme(lm, info_active(db, ids))
    if p:
        raise ListaInvalida(p)
    return lm
