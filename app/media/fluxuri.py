"""Randarea ca job durabil pe culoarele grele (F8.9, docs/14 §14.11, ADR-03): câte un job media pe culoar.

Fluxul primește doar identificatori (clientul și randarea pregătită de `montaj.pregateste`); pasul randează și
înregistrează rezultatul, cu timpul și memoria de vârf ale randării. O reluare după o cădere refuză dublura: o
randare deja `gata` sau `respinsa` nu se mai randează.
"""

import uuid

from app.db import sesiune_tenant
from app.media import montaj
from app.media.modele import Randare
from app.operare import motor
from app.operare.motor import Coada, Prioritate

NUME = "media.randeaza"


@motor.pas(nume="media.randeaza_pas", reincercari=1)
def _randeaza(tenant_id: str, randare_id: str) -> str:
    with sesiune_tenant(uuid.UUID(tenant_id)) as db:
        r = db.get(Randare, uuid.UUID(randare_id))
        if r is None:
            return "inexistenta"
        if r.stare != "in_lucru":
            return r.stare
        return montaj.executa(db, r).stare


@motor.flux(NUME, timp_maxim_sec=1800)
def randeaza(tenant_id: str, randare_id: str) -> str:
    return _randeaza(tenant_id, randare_id)


def trimite(tenant_id: uuid.UUID, randare_id: uuid.UUID, *, prioritate: Prioritate = Prioritate.P2) -> str:
    return motor.trimite(
        randeaza, str(tenant_id), str(randare_id), coada=Coada.GREU, prioritate=prioritate,
        cheie=f"randare:{randare_id}",
    )  # fmt: skip


# --- formatul E (F8.12): filmarea brută a clientului -> clip publicabil, pe culoarul greu

NUME_FORMAT_E = "media.format_e"


@motor.pas(nume="media.format_e_pas", reincercari=0)
def _format_e(tenant_id: str, activ_id: str, livrabil_id: str) -> str:
    from app import productie, validare
    from app.media import formatul_e, normalizare, regizor, subtitrari
    from app.media.modele import Activ

    t = uuid.UUID(tenant_id)
    with sesiune_tenant(t) as db:
        brut = db.get(Activ, uuid.UUID(activ_id))
        lv = db.get(productie.Livrabil, uuid.UUID(livrabil_id))
        if brut is None or lv is None:
            return "inexistent"
        c = validare.continut.citeste(db, lv.id)
        fraze = [normalizare.normalizeaza(f) for f in regizor.fraze_din_script(c.campuri)]
        canal = lv.canal if lv.canal in subtitrari.ZONE_SIGURE else "tiktok"
        r = formatul_e.proceseaza(db, t, brut, fraze, canal=canal)
        return f"{r.stare}:{r.id}"


@motor.flux(NUME_FORMAT_E, timp_maxim_sec=1800)
def format_e(tenant_id: str, activ_id: str, livrabil_id: str) -> str:
    return _format_e(tenant_id, activ_id, livrabil_id)


def trimite_format_e(tenant_id: uuid.UUID, activ_id: uuid.UUID, livrabil_id: uuid.UUID) -> str:
    return motor.trimite(
        format_e, str(tenant_id), str(activ_id), str(livrabil_id), coada=Coada.GREU, prioritate=Prioritate.P1,
        cheie=f"format_e:{activ_id}",
    )  # fmt: skip
