"""Propunerile de schimbare și aplicarea lor (F13.4, I2; docs/16 §16.1 punctele 3–5).

O propunere e tipizată (`creeaza`, `stare`, `buget`, `stare_anunt`), păstrează starea de dinainte și pe cea de
după, trece prin gardian (F13.5) și, aprobată, se aplică printr-un efect de sistem `reclama` (executorul
F2.5/F7:
cheie de idempotență = propunerea, încercări, opriri). Starea campaniei la noi se schimbă doar când efectul a
ajuns la platformă (`reconciliaza`). Anularea creează propunerea inversă (dinainte ↔ după) și o aplică
imediat.
"""

import datetime as dt
import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.operare import audit, opriri, urme
from app.operare.efecte import sistem
from app.reclame import gardian, rezultate, verificare
from app.reclame.modele import Anunt, Campanie, ContReclame, Propunere

TIPURI = ("creeaza", "stare", "buget", "stare_anunt", "adauga_anunt")
STARI_CAMPANIE = {"pauza": "in_pauza", "activa": "activa"}
ETICHETE_STARE = {
    "in_constructie": "în construcție",
    "in_pauza": "în pauză",
    "activa": "activă",
    "oprita": "oprită",
    "esuata": "eșuată",
    "blocata": "blocată",
}


class PropunereRefuzata(ValueError):
    """Propunerea nu poate fi făcută, aprobată, aplicată sau anulată (motivul e în mesaj)."""


def stare_campanie(c: Campanie) -> dict[str, Any]:
    return {"stare": "activa" if c.stare == "activa" else "pauza", "buget_zilnic_bani": c.buget_zilnic_bani}


def context_gardian(db: Session, cont: ContReclame, c: Campanie, acum: dt.datetime) -> gardian.Context:
    """Ce știe gardianul despre cont în clipa propunerii (bugetele active, cheltuiala lunii, ritmul)."""
    azi = acum.date()
    inceput_luna = azi.replace(day=1)
    luna_urmatoare = (inceput_luna + dt.timedelta(days=32)).replace(day=1)
    suma = db.execute(
        select(func.coalesce(func.sum(Campanie.buget_zilnic_bani), 0)).where(
            Campanie.cont_id == cont.id, Campanie.stare == "activa", Campanie.id != c.id
        )
    ).scalar_one()
    automate = db.execute(
        select(func.count()).where(
            Propunere.cont_id == cont.id,
            Propunere.sursa.in_(gardian.AUTOMATE),
            Propunere.stare.in_(("aprobata", "aplicata")),
            Propunere.creat_la >= dt.datetime.combine(azi, dt.time(), dt.UTC),
        )
    ).scalar_one()
    return gardian.Context(
        plafon_zilnic_bani=cont.plafon_zilnic_bani,
        plafon_lunar_bani=cont.plafon_lunar_bani,
        plafon_campanie_bani=cont.plafon_campanie_bani,
        schimbare_max_pct=cont.schimbare_max_pct,
        asteptare_ore=cont.asteptare_ore,
        schimbari_pe_zi=cont.schimbari_pe_zi,
        suma_active_bani=int(suma),
        cheltuit_luna_bani=rezultate.totaluri(db, cont.id, inceput_luna, azi).cheltuiala_bani,
        zile_ramase=(luna_urmatoare - azi).days,
        schimbari_automate_azi=int(automate),
        ultima_schimbare=c.schimbat_la,
        reclame_oprite=opriri.este_oprit(db, opriri.Oprire.RECLAME),
        acum=acum,
    )


def _verdict(db: Session, p: Propunere, cont: ContReclame, c: Campanie, acum: dt.datetime) -> dict[str, Any]:
    """Verdictul gardianului de buget (F13.5)."""
    return gardian.verifica(p.tip, p.inainte, p.dupa, p.sursa, context_gardian(db, cont, c, acum)).ca_dict()


def verificare_lansare(db: Session, c: Campanie) -> list[str]:
    """Verificarea dinaintea activării (16.3 pasul 6, F13.8): o reclamă bună și pagina de destinație vie."""
    bune = [
        a for a in db.execute(select(Anunt).where(Anunt.campanie_id == c.id)).scalars() if a.stare == "activa"
    ]
    if not bune:
        return ["campania nu are nicio reclamă trecută de verificare"]
    if verificare.CITESTE_PAGINA(bune[0].link) is None:
        return ["pagina de destinație nu răspunde"]
    return []


def propune(
    db: Session,
    campanie_id: uuid.UUID,
    tip: str,
    dupa: dict[str, Any],
    *,
    motiv: str,
    sursa: str,
    anunt_id: uuid.UUID | None = None,
    utilizator_id: uuid.UUID | None = None,
    acum: dt.datetime | None = None,
    anuleaza_id: uuid.UUID | None = None,
) -> Propunere:
    """Scrie propunerea cu starea de dinainte și verdictul gardianului. Refuzată = rămâne în istoric, fără
    efect."""
    if tip not in TIPURI:
        raise PropunereRefuzata(f"tip necunoscut: {tip}")
    acum = acum or dt.datetime.now(dt.UTC)
    c = db.get(Campanie, campanie_id)
    if c is None:
        raise PropunereRefuzata("campanie inexistentă")
    cont = db.get(ContReclame, c.cont_id)
    if cont is None:
        raise PropunereRefuzata("cont inexistent")
    if tip != "creeaza" and c.id_extern is None:
        raise PropunereRefuzata("campania nu există încă la platformă")
    inainte: dict[str, Any] = stare_campanie(c)
    if tip in ("stare_anunt", "adauga_anunt"):
        a = db.get(Anunt, anunt_id) if anunt_id else None
        if a is None or a.campanie_id != c.id or (tip == "stare_anunt") != (a.id_extern is not None):
            raise PropunereRefuzata(
                "reclama nu există la platformă" if tip == "stare_anunt" else "reclamă invalidă"
            )
        inainte = {"stare": "activa" if a.stare == "activa" else "pauza"}
    p = Propunere(
        tenant_id=c.tenant_id,
        cont_id=c.cont_id,
        campanie_id=c.id,
        anunt_id=anunt_id,
        tip=tip,
        inainte=inainte,
        dupa=dupa,
        motiv=motiv.strip()[:500],
        sursa=sursa,
        decis_de=utilizator_id,
        anuleaza_id=anuleaza_id,
    )
    db.add(p)
    db.flush()
    p.verdict = _verdict(db, p, cont, c, acum)
    if tip == "stare" and dupa.get("stare") == "activa" and p.verdict.get("permis"):
        lipsuri = verificare_lansare(db, c)
        if lipsuri:
            p.verdict = {"permis": False, "motive": lipsuri, "cere_client": False}
    if not p.verdict.get("permis"):
        p.stare, p.decis_la = "refuzata", acum
    urme.inregistreaza(
        db, "buget", f"gardian:{tip}", tenant_id=c.tenant_id, obiect_tip="reclame_propunere", obiect_id=str(p.id),
        rezultat="ok" if p.verdict.get("permis") else "respins", motiv="; ".join(p.verdict.get("motive") or []),
        cod="" if p.verdict.get("permis") else "peste_plafon", intrari={"sursa": sursa, "inainte": inainte, "dupa": dupa},
    )  # fmt: skip
    audit.record(
        db,
        "reclame.propunere",
        obiect_tip="reclame_propunere",
        obiect_id=p.id,
        tenant_id=c.tenant_id,
        utilizator_id=utilizator_id,
        actor_tip=None if utilizator_id else "sistem",
        detalii={"tip": tip, "sursa": sursa, "inainte": inainte, "dupa": dupa, "stare": p.stare},
    )
    return p


def _payload(db: Session, p: Propunere, c: Campanie, cont: ContReclame) -> dict[str, Any]:
    comun = {"platforma": cont.platforma, "cont_extern": cont.cont_extern, "propunere": str(p.id)}
    if p.tip == "creeaza":
        anunturi = db.execute(select(Anunt).where(Anunt.campanie_id == c.id).order_by(Anunt.nume)).scalars()
        return comun | {
            "actiune": "creeaza_campanie",
            "nume": c.nume,
            "obiectiv": p.dupa.get("obiectiv", "lead"),
            "buget_zilnic_bani": c.buget_zilnic_bani,
            "reclame": [
                {"nume": a.nume, "titlu": a.titlu, "text": a.text, "link": a.link}
                for a in anunturi
                if a.stare != "blocata"
            ],
        }
    if p.tip == "stare":
        return comun | {"actiune": "stare_campanie", "obiect_extern": c.id_extern, "stare": p.dupa["stare"]}
    if p.tip == "buget":
        return comun | {
            "actiune": "buget_campanie",
            "obiect_extern": c.id_extern,
            "buget_zilnic_bani": int(p.dupa["buget_zilnic_bani"]),
        }
    a = db.get(Anunt, p.anunt_id)
    if p.tip == "adauga_anunt" and a is not None:
        return comun | {
            "actiune": "creeaza_anunt",
            "obiect_extern": c.id_extern,
            "nume": a.nume,
            "titlu": a.titlu,
            "text": a.text,
            "link": a.link,
        }
    return comun | {
        "actiune": "stare_anunt",
        "obiect_extern": a.id_extern if a else "",
        "stare": p.dupa["stare"],
    }


def aproba(db: Session, propunere_id: uuid.UUID, *, utilizator_id: uuid.UUID | None = None) -> Propunere:
    """Aprobă (omul sau, pentru construcția din planul aprobat și oprirea de urgență, sistemul) și aplică."""
    p = db.get(Propunere, propunere_id)
    if p is None or p.stare != "propusa":
        raise PropunereRefuzata("propunerea nu mai așteaptă o decizie")
    p.stare, p.decis_la = "aprobata", dt.datetime.now(dt.UTC)
    p.decis_de = utilizator_id or p.decis_de
    c, cont = db.get(Campanie, p.campanie_id), db.get(ContReclame, p.cont_id)
    if c is None or cont is None:
        raise PropunereRefuzata("campania sau contul nu mai există")
    e = sistem.cere(
        db, "reclama", cheie=f"propunere:{p.id}", payload=_payload(db, p, c, cont), tenant_id=p.tenant_id
    )
    p.efect_id = e.id
    audit.record(
        db,
        "reclame.propunere_aprobata",
        obiect_tip="reclame_propunere",
        obiect_id=p.id,
        tenant_id=p.tenant_id,
        utilizator_id=utilizator_id,
        actor_tip=None if utilizator_id else "sistem",
    )
    return p


def respinge(db: Session, propunere_id: uuid.UUID, *, utilizator_id: uuid.UUID) -> Propunere:
    p = db.get(Propunere, propunere_id)
    if p is None or p.stare != "propusa":
        raise PropunereRefuzata("propunerea nu mai așteaptă o decizie")
    p.stare, p.decis_de, p.decis_la = "anulata", utilizator_id, dt.datetime.now(dt.UTC)
    return p


def reconciliaza(db: Session) -> int:
    """Mută starea campaniilor după efectele ajunse la platformă. Întoarce câte propuneri s-au încheiat."""
    gata = 0
    for p in db.execute(
        select(Propunere).where(Propunere.stare == "aprobata").order_by(Propunere.creat_la)
    ).scalars():
        e = sistem.citeste(db, p.efect_id) if p.efect_id else None
        if e is None or e.stare in ("in_asteptare",):
            continue
        c = db.get(Campanie, p.campanie_id)
        if c is None:
            continue
        if e.stare != "trimis":
            p.stare = "esuata"
            if p.tip == "creeaza":
                c.stare = "esuata"
            gata += 1
            continue
        p.stare, p.aplicat_la = "aplicata", e.trimis_la or dt.datetime.now(dt.UTC)
        if p.tip == "creeaza":
            c.id_extern, c.stare = e.id_extern, "in_pauza"
            harta = json.loads(e.link or "{}").get("reclame", {})
            for a in db.execute(select(Anunt).where(Anunt.campanie_id == c.id)).scalars():
                if a.nume in harta:
                    a.id_extern, a.stare = str(harta[a.nume]), "activa"
        elif p.tip == "stare":
            c.stare = STARI_CAMPANIE[str(p.dupa["stare"])]
        elif p.tip == "buget":
            c.buget_zilnic_bani = int(p.dupa["buget_zilnic_bani"])
        else:
            anunt = db.get(Anunt, p.anunt_id)
            if anunt is not None and p.tip == "adauga_anunt":
                anunt.id_extern, anunt.stare = e.id_extern, "activa"
            elif anunt is not None:
                anunt.stare = "activa" if p.dupa["stare"] == "activa" else "oprita"
        c.schimbat_la = p.aplicat_la
        audit.record(
            db,
            "reclame.propunere_aplicata",
            obiect_tip="reclame_propunere",
            obiect_id=p.id,
            tenant_id=p.tenant_id,
            actor_tip="sistem",
            detalii={"tip": p.tip, "dupa": p.dupa},
        )
        gata += 1
    return gata


def anuleaza(db: Session, propunere_id: uuid.UUID, *, utilizator_id: uuid.UUID) -> Propunere:
    """Anularea dintr-o atingere: propunerea inversă, aprobată și aplicată imediat (D-010)."""
    p = db.get(Propunere, propunere_id)
    if p is None or p.stare != "aplicata":
        raise PropunereRefuzata("se poate anula doar o schimbare aplicată")
    if p.tip == "creeaza":
        raise PropunereRefuzata("o campanie creată nu se „anulează”; e deja în pauză")
    deja = db.execute(
        select(Propunere.id).where(Propunere.anuleaza_id == p.id, Propunere.stare != "refuzata")
    ).first()
    if deja is not None:
        raise PropunereRefuzata("schimbarea a fost deja anulată")
    inv = propune(
        db,
        p.campanie_id,
        p.tip,
        dict(p.inainte),
        motiv=f"Anulare: {p.motiv}"[:500],
        sursa="anulare",
        anunt_id=p.anunt_id,
        utilizator_id=utilizator_id,
        anuleaza_id=p.id,
    )
    if inv.stare == "propusa":
        aproba(db, inv.id, utilizator_id=utilizator_id)
    return inv


def ale_campaniei(db: Session, campanie_id: uuid.UUID) -> list[Propunere]:
    q = select(Propunere).where(Propunere.campanie_id == campanie_id).order_by(Propunere.creat_la.desc())
    return list(db.execute(q).scalars())


def ale_contului(db: Session, cont_id: uuid.UUID, *, limita: int = 50) -> list[Propunere]:
    q = (
        select(Propunere)
        .where(Propunere.cont_id == cont_id)
        .order_by(Propunere.creat_la.desc())
        .limit(limita)
    )
    return list(db.execute(q).scalars())
