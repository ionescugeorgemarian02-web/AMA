"""Cererile de aprobare la platforme (F9.2–F9.6, docs/15 §15.3): App Review (Meta), auditul YouTube și TikTok,
Community Management API (LinkedIn).

Al doilea val de cereri pleacă abia când conectorul merge în modul de test, pe conturile agenției, și pleacă
ÎMPREUNĂ cu înregistrarea fluxului real: pașii HTTP ai publicării de probă (fără tokenuri), descrierea cazului
de
utilizare și, la migrare, filmarea ecranului. Fără înregistrare care să conțină o publicare reușită, cererea
nu
pleacă (și baza refuză starea „trimisă” fără înregistrare).

# NEVERIFICAT / SIMULAT: depunerea propriu-zisă se face în consola fiecărei platforme (nu are API); aici se
pregătește dosarul, se notează starea și se anunță omul. Filmarea ecranului: la migrare.
"""

import datetime as dt
import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.operare import audit
from app.publicare.canale import ETICHETE_APROBARE, StareAprobare
from app.publicare.modele import AprobareApi

# Cazul de utilizare descris în cerere, pe permisiune; calea de publicare care trebuie să apară în
# înregistrare.
CERERI: dict[tuple[str, str], dict[str, str]] = {
    ("meta", "pagini"): {
        "titlu": "Meta App Review: pages_manage_posts",
        "caz": "Agenția publică, după aprobarea omului în portal, postările programate pe paginile "
        "de Facebook "
        "ale clienților ei, o singură dată, la ora aleasă.",
        "publicare": "POST /feed",
    },
}
DIRECTOR = "inregistrari"


class CerereRefuzata(RuntimeError):
    pass


def _baza() -> Path:
    return Path(get_settings().media_dir)


def salveaza_inregistrarea(platforma: str, permisiune: str, pasi: list[dict[str, Any]]) -> str:
    """Scrie înregistrarea fluxului lângă fișierele media; întoarce calea relativă."""
    cerere = CERERI[(platforma, permisiune)]
    acum = dt.datetime.now(dt.UTC)
    rel = f"{DIRECTOR}/{platforma}-{permisiune}-{acum:%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}.json"
    cale = _baza() / rel
    cale.parent.mkdir(parents=True, exist_ok=True)
    cale.write_text(
        json.dumps(
            {
                "platforma": platforma,
                "permisiune": permisiune,
                "titlu": cerere["titlu"],
                "caz_de_utilizare": cerere["caz"],
                "inregistrat_la": acum.isoformat(),
                "pasi": pasi,
                "filmare": None,  # NEVERIFICAT: filmarea ecranului fluxului real, la migrare
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    return rel


def citeste_inregistrarea(rel: str) -> dict[str, Any]:
    cale = (_baza() / rel).resolve()
    if not cale.is_relative_to(_baza().resolve() / DIRECTOR) or not cale.is_file():
        raise CerereRefuzata("înregistrarea fluxului nu există")
    return dict(json.loads(cale.read_text(encoding="utf-8")))


def publicare_reusita(inregistrare: dict[str, Any], publicare: str) -> bool:
    """Nucleu pur: înregistrarea conține o publicare reușită (`METODA /sufix`, răspuns 2xx)?"""
    metoda, sufix = publicare.split(" ", 1)
    return any(
        p.get("metoda") == metoda and str(p.get("cale", "")).endswith(sufix) and 200 <= int(p["status"]) < 300
        for p in inregistrare.get("pasi", [])
    )


def trimite_cererea(
    db: Session, platforma: str, permisiune: str, *, inregistrare: str, utilizator_id: uuid.UUID | None = None
) -> AprobareApi:
    a = db.get(AprobareApi, (platforma, permisiune), with_for_update=True)
    if a is None or (platforma, permisiune) not in CERERI:
        raise CerereRefuzata("permisiune necunoscută")
    if StareAprobare(a.stare) in (StareAprobare.TRIMISA, StareAprobare.APROBATA):
        raise CerereRefuzata(f"cererea este deja „{ETICHETE_APROBARE[StareAprobare(a.stare)].lower()}”")
    date = citeste_inregistrarea(inregistrare)
    if date.get("platforma") != platforma or date.get("permisiune") != permisiune:
        raise CerereRefuzata("înregistrarea e a altei cereri")
    if not publicare_reusita(date, CERERI[(platforma, permisiune)]["publicare"]):
        raise CerereRefuzata("înregistrarea nu conține o publicare reușită în modul de test")
    a.stare, a.inregistrare = StareAprobare.TRIMISA.value, inregistrare
    a.trimisa_la = a.actualizat_la = dt.datetime.now(dt.UTC)
    db.flush()
    audit.record(
        db,
        "publicare.cerere_aprobare",
        obiect_tip="aprobare_api",
        obiect_id=f"{platforma}:{permisiune}",
        utilizator_id=utilizator_id,
        tenant_id=None,
        actor_tip=None if utilizator_id else "sistem",
        detalii={
            "platforma": platforma,
            "permisiune": permisiune,
            "inregistrare": inregistrare,
            "pasi": len(date.get("pasi", [])),
        },
    )
    return a


def decide(
    db: Session,
    platforma: str,
    permisiune: str,
    *,
    aprobata: bool,
    observatii: str = "",
    utilizator_id: uuid.UUID | None = None,
) -> AprobareApi:
    """Răspunsul platformei, notat de om. Respinsă: canalul rămâne asistat, cererea se reface (15.3)."""
    a = db.get(AprobareApi, (platforma, permisiune), with_for_update=True)
    if a is None or StareAprobare(a.stare) is not StareAprobare.TRIMISA:
        raise CerereRefuzata("se decide doar o cerere trimisă")
    a.stare = (StareAprobare.APROBATA if aprobata else StareAprobare.RESPINSA).value
    a.observatii, a.decisa_la = observatii[:2000], dt.datetime.now(dt.UTC)
    a.actualizat_la = a.decisa_la
    db.flush()
    audit.record(
        db,
        "publicare.aprobare_decisa",
        obiect_tip="aprobare_api",
        obiect_id=f"{platforma}:{permisiune}",
        utilizator_id=utilizator_id,
        tenant_id=None,
        detalii={"stare": a.stare, "observatii": observatii[:200]},
    )
    return a
