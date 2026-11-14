"""Montajul (F8.6): o listă validă -> un video vertical final, fără intervenție, înregistrat în bibliotecă.

Pașii: validarea listei (licențe, durate), consemnarea folosirii fiecărui activ (`licente.foloseste`),
randarea
(`randare`), salvarea ca activ `video` (sursa `montaj`) cu licența `productie_proprie` (componentele și
licențele
lor) și rândul din `randari` cu timpul și memoria de vârf ale randării (F8.9).
"""

import datetime as dt
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.media import biblioteca, ffmpeg, licente, lista, randare, regizor
from app.media.modele import Activ, Randare


def intrari(db: Session, lm: lista.ListaMontaj) -> randare.Intrari:
    scene: dict[str, Any] = {}
    categorii: dict[str, str] = {}
    for s in lm.scene:
        a = db.get(Activ, s.activ_id)
        if a is None:
            raise regizor.ListaInvalida([f"activ inexistent: {s.activ_id}"])
        scene[str(a.id)] = regizor.cale(a)
        categorii[str(a.id)] = a.categorie
    voce = db.get(Activ, lm.voce.activ_id)
    muzica = db.get(Activ, lm.muzica.activ_id) if lm.muzica else None
    if voce is None:
        raise regizor.ListaInvalida(["vocea lipsește"])
    return randare.Intrari(scene, categorii, regizor.cale(voce), regizor.cale(muzica) if muzica else None)


def valideaza(db: Session, lm: lista.ListaMontaj) -> None:
    ids = {s.activ_id for s in lm.scene} | {lm.voce.activ_id} | ({lm.muzica.activ_id} if lm.muzica else set())
    p = lista.probleme(lm, regizor.info_active(db, ids))
    if p:
        raise regizor.ListaInvalida(p)


def componente(db: Session, lm: lista.ListaMontaj) -> list[dict[str, Any]]:
    ids = [lm.voce.activ_id, *(s.activ_id for s in lm.scene)] + ([lm.muzica.activ_id] if lm.muzica else [])
    out, vazute = [], set()
    for i in ids:
        if i in vazute:
            continue
        vazute.add(i)
        a = db.get(Activ, i)
        lic = (a.licenta or {}) if a else {}
        chei = ("tip", "statut", "identificator", "autor", "profil", "model", "samanta", "eticheta_ai")
        out.append(
            {
                "activ_id": str(i),
                "categorie": a.categorie if a else "?",
                "sursa": a.sursa if a else "?",
                "licenta": {k: lic.get(k) for k in chei if k in lic},
            }
        )
    return out


def pregateste(
    db: Session,
    tenant_id: uuid.UUID,
    lm: lista.ListaMontaj,
    *,
    livrabil_id: uuid.UUID | None = None,
    calitate: str = "final",
) -> Randare:
    """Validează lista, deschide randarea (`in_lucru`) și consemnează folosirea fiecărui activ."""
    valideaza(db, lm)
    r = Randare(tenant_id=tenant_id, livrabil_id=livrabil_id, lista=lm.model_dump(mode="json"),
                stare="in_lucru",
                calitate=calitate, masuratori={})  # fmt: skip
    db.add(r)
    db.flush()
    for i in (
        {s.activ_id for s in lm.scene} | {lm.voce.activ_id} | ({lm.muzica.activ_id} if lm.muzica else set())
    ):
        licente.foloseste(db, i, scop="montaj", obiect_id=r.id)
    return r


def executa(db: Session, r: Randare) -> Randare:
    """Randează o randare pregătită și înregistrează videoul, cu măsurătorile (F8.9)."""
    lm = lista.ListaMontaj.model_validate(r.lista)
    inceput, t0 = dt.datetime.now(dt.UTC), time.monotonic()
    with ffmpeg.masurare() as rulari, tempfile.TemporaryDirectory() as tmp:
        corp = _randeaza(db, r, lm, Path(tmp))
    secunde = sum(x.secunde for x in rulari)
    r.masuratori = {
        **(r.masuratori or {}),
        "secunde": round(secunde, 2),
        "total_sec": round(time.monotonic() - t0, 2),
        "memorie_mb": round(max(x.memorie_mb for x in rulari), 1),
        "durata_video": lm.durata,
        "inceput_la": inceput.isoformat(),
        "sfarsit_la": dt.datetime.now(dt.UTC).isoformat(),
    }
    return _inregistreaza(db, r, lm, corp)


def _randeaza(db: Session, r: Randare, lm: lista.ListaMontaj, tmp: Path) -> bytes:
    corp, _ = randare.randeaza(lm, intrari(db, lm), calitate=r.calitate)
    return corp


def produ(
    db: Session,
    tenant_id: uuid.UUID,
    lm: lista.ListaMontaj,
    *,
    livrabil_id: uuid.UUID | None = None,
    calitate: str = "final",
) -> Randare:
    """Lista -> video final, fără intervenție: pregătire, randare, înregistrare."""
    return executa(db, pregateste(db, tenant_id, lm, livrabil_id=livrabil_id, calitate=calitate))


def _inregistreaza(db: Session, r: Randare, lm: lista.ListaMontaj, corp: bytes) -> Randare:
    a = biblioteca.incarca(
        db,
        r.tenant_id,
        corp,
        nume_original=f"video-{r.id}.mp4",
        sursa="montaj",
        utilizator_id=None,
        descriere=f"video format {lm.format}, {lm.canal}, {lm.durata:.1f} s",
        licenta={"tip": "productie_proprie", "statut": licente.STATUT_OK, "componente": componente(db, lm)},
        generare={"randare_id": str(r.id), "format": lm.format, "calitate": r.calitate},
    )
    r.activ_id = a.id
    r.stare = "gata"
    r.terminat_la = dt.datetime.now(dt.UTC)
    db.flush()
    return r


def ale_clientului(db: Session, tenant_id: uuid.UUID) -> list[Randare]:
    return list(
        db.execute(select(Randare).where(Randare.tenant_id == tenant_id).order_by(Randare.creat_la)).scalars()
    )
