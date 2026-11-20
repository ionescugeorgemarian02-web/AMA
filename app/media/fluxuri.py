"""Randarea ca job durabil pe culoarele grele (F8.9, docs/14 §14.11, ADR-03): câte un job media pe culoar.

Fluxul primește doar identificatori (clientul și randarea pregătită de `montaj.pregateste`); pasul randează și
înregistrează rezultatul, cu timpul și memoria de vârf ale randării. O reluare după o cădere refuză dublura: o
randare deja `gata` sau `respinsa` nu se mai randează.
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db import sesiune_tenant
from app.media import montaj, regizor
from app.media.modele import Randare
from app.operare import motor, resurse
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
        ok, motiv = resurse.permite_greu()
        if not ok:  # F15.1: disc plin sau memorie la limită -> randarea nouă se amână, nu pornește
            la = dt.datetime.now(dt.UTC) + resurse.AMANARE_GREU
            motor.trimite(
                randeaza, tenant_id, randare_id, coada=Coada.GREU, prioritate=Prioritate.P1,
                cheie=f"randare:{randare_id}:amanata:{int(la.timestamp()) // 600}", la=la,
            )  # fmt: skip
            return f"amanata_{motiv}"
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


BLOCAT_MATERIAL = "material_lipsa"


def natura_materialului(db: Session, livrabil_id: uuid.UUID, script: dict[str, Any]) -> regizor.Natura:
    """`educativ` sau `prezentare` (F-editorial): din script, altfel din brieful vizual al livrabilului.
    Necunoscută înseamnă `prezentare`: fără material real nu inventăm o imagine a afacerii."""
    from app import continut

    natura = script.get("natura")
    if natura is None:
        b = continut.brief.al_livrabilului(db, livrabil_id)
        natura = (b.continut or {}).get("natura") if b is not None else None
    return "educativ" if natura == "educativ" else "prezentare"


@motor.pas(nume="media.script_pregateste", reincercari=1)
def pregateste_script(tenant_id: str, livrabil_id: str, versiune: str) -> str:
    """Storyboardul din inventarul real, apoi vocea și lista de montaj (F-editorial: storyboardul ÎNAINTE de
    voce și montaj). O prezentare fără material potrivit se oprește cu cereri precise (`BLOCAT_MATERIAL`)."""
    from sqlalchemy import select

    from app import productie, validare
    from app.conturi.modele import Client
    from app.media import animatie, cereri, normalizare, sabloane, transcriere
    from app.media.modele import Activ

    tid, lid = uuid.UUID(tenant_id), uuid.UUID(livrabil_id)
    with sesiune_tenant(tid) as db:
        lv = productie.blocheaza(db, lid)
        if lv.versiune != int(versiune):
            return ""
        deja = db.scalar(
            select(Randare.id)
            .where(
                Randare.tenant_id == tid,
                Randare.livrabil_id == lid,
                Randare.calitate == "final",
                Randare.masuratori["versiune_continut"].as_integer() == lv.versiune,
            )
            .order_by(Randare.creat_la)
            .limit(1)
        )
        if deja:
            return str(deja)
        script = validare.continut.citeste(db, lid, lv.versiune).campuri
        sb = regizor.storyboard(db, tid, script, natura=natura_materialului(db, lid, script))
        if sb.blocat:
            cereri.deschide(db, tid, lid, lv.versiune, sb)
            return BLOCAT_MATERIAL
        cereri.rezolva(db, tid, lid)
        fraze = [normalizare.normalizeaza(f) for f in regizor.fraze_din_script(script)]
        voce = transcriere.naratiune_verificata(db, tid, fraze, profil_cod="ro-espeak-nativ")
        de_ilustrat = [s.scena for s in sb.scene if s.sursa == "ilustratie"]
        clipuri: dict[int, Activ] = {}
        if de_ilustrat:
            intervale = regizor.momente_batai(fraze, voce.aliniere, voce.naratiune.durata + regizor.COADA)
            ident, _ = sabloane.identitate(
                db, tid, db.scalars(select(Client.nume).where(Client.id == tid)).one()
            )
            paleta = ident["culori"]
            clipuri = animatie.clipuri_scene(
                db,
                tid,
                script,
                {i: intervale[i][1] - intervale[i][0] for i in de_ilustrat},
                eticheta=ident["nume"],
                culori={
                    "fundal": paleta["fundal"],
                    "fundal2": paleta["secundara"],
                    "text": paleta["text"],
                    "accent": paleta["primara"],
                },
            )
        active: list[Activ] = []
        fixe: list[int] = []
        for s in sb.scene:
            a = clipuri[s.scena] if s.activ_id is None else db.get(Activ, s.activ_id)
            if a is None:
                raise regizor.ListaInvalida([f"scena {s.scena}: activul ales nu mai există"])
            if a not in active:
                active.append(a)
            fixe.append(active.index(a))
        lm = regizor.regizeaza(
            db,
            tid,
            fraze=fraze,
            script=script,
            naratiune=voce,
            materiale=active,
            format="B" if all(a.categorie == "foto" for a in active) else "A",
            canal=lv.canal,
            livrabil_id=lid,
            materiale_fixe=fixe,
        )
        return str(montaj.pregateste(db, tid, lm, livrabil_id=lid).id)


@motor.flux("media.script", timp_maxim_sec=2400)
def produce_script(tenant_id: str, livrabil_id: str, versiune: str) -> str:
    rid = pregateste_script(tenant_id, livrabil_id, versiune)
    if rid == BLOCAT_MATERIAL:
        return rid
    return _randeaza(tenant_id, rid) if rid else "versiune_inlocuita"


def reia_livrabil(
    db: Session, tenant_id: uuid.UUID, livrabil_id: uuid.UUID, *, utilizator_id: uuid.UUID | None
) -> str:
    """Reia producția video a aceluiași livrabil după încărcarea materialului cerut (F-editorial). Pornește
    fluxul în aceeași tranzacție; storyboardul se reface din inventarul nou și redeschide cererile rămase."""
    from app import productie
    from app.media import cereri
    from app.operare import audit

    lv = productie.citeste(db, livrabil_id)
    if lv is None:
        raise LookupError("livrabil inexistent")
    n = cereri.rezolva(db, tenant_id, livrabil_id)
    cheie = f"video:{livrabil_id}:v{lv.versiune}:reluare:{uuid.uuid4().hex[:12]}"
    motor.trimite_atomic(
        db, produce_script, str(tenant_id), str(livrabil_id), str(lv.versiune), cheie=cheie, coada=Coada.GREU
    )
    audit.record(
        db,
        "livrabil.video_reluat",
        obiect_tip="livrabil",
        obiect_id=livrabil_id,
        tenant_id=tenant_id,
        utilizator_id=utilizator_id,
        detalii={"versiune": lv.versiune, "cereri_inchise": n},
    )
    return cheie
