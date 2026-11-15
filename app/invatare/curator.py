"""Curatorul și playbook-ul (F11.2, K8, docs/11 §11.3): schimbări mici asupra lecțiilor, nu o rescriere.

- **Aprobarea.** O propunere a Reflectorului devine lecție activă doar aprobată de un om. Lecțiile sensibile
  (conformitate, prețuri, promisiuni) le poate aproba doar proprietarul. Respingerea cere un motiv.
- **Limita.** Cel mult `MAX_ACTIVE` (40) lecții active pe domeniu; peste limită aprobarea e refuzată, cu
  mesaj: întâi se retrage una.
- **În contextul sarcinii următoare.** Lecțiile active ale clientului (pe client, pe canalul livrabilului și
  pe agentul „autor”) intră în promptul autorului, prin punctul de extensie
  `continut.scriere.inregistreaza_adaos_context`. Ce lecții au intrat se notează pe livrabil
  (`lectii_folosite`), cum cere 11.3 („generatorul notează ce lecții a folosit”).
- **Contoarele.** La decizia omului asupra livrabilului (punctul de extensie al aprobărilor, în aceeași
  tranzacție): aprobat → „a ajutat” +1 la fiecare lecție folosită; respins → „a dăunat” +1. O singură dată
  pe livrabil și lecție. La început semnalul uman e cel mai valoros (11.1); contoarele din rezultatele reale
  (recompensa postării) NU sunt încă legate aici.
- **Retragerea automată.** Când „a dăunat” depășește „a ajutat”, lecția se retrage singură, cu urmă în
  audit. Un om o poate retrage oricând (reversibilitate, 11.6).
"""

import datetime as dt
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app import productie
from app.continut import scriere
from app.conturi import Rol
from app.invatare import constitutie
from app.invatare.modele import Lectie, LectieFolosita
from app.operare import audit

MAX_ACTIVE = 40  # pe domeniu (11.3)
MAX_IN_CONTEXT = 12  # câte lecții intră într-un prompt: cele mai utile întâi


class CuratorRefuzat(ValueError):
    """Schimbarea cerută nu e permisă (stare, rol, limită, motiv lipsă)."""


def _lectie(db: Session, lectie_id: uuid.UUID) -> Lectie:
    r = db.execute(select(Lectie).where(Lectie.id == lectie_id).with_for_update()).scalar_one_or_none()
    if r is None:
        raise CuratorRefuzat("lecția nu există")
    return r


def active(
    db: Session, tenant_id: uuid.UUID, domeniu_tip: str | None = None, domeniu: str = ""
) -> list[Lectie]:
    q = select(Lectie).where(Lectie.tenant_id == tenant_id, Lectie.stare == "activa")
    if domeniu_tip is not None:
        q = q.where(Lectie.domeniu_tip == domeniu_tip, Lectie.domeniu == domeniu)
    return list(db.execute(q.order_by((Lectie.a_ajutat - Lectie.a_daunat).desc(), Lectie.creat_la)).scalars())


def istoric(db: Session, tenant_id: uuid.UUID, *, limita: int = 50) -> list[Lectie]:
    """Promovările și revenirile unui client (11.7): lecțiile decise, cele mai recente întâi."""
    return list(
        db.execute(
            select(Lectie)
            .where(Lectie.tenant_id == tenant_id, Lectie.stare.in_(("activa", "retrasa", "respinsa")))
            .order_by(Lectie.actualizat_la.desc())
            .limit(limita)
        ).scalars()
    )


def _muta(
    db: Session,
    r: Lectie,
    stare: str,
    *,
    utilizator_id: uuid.UUID | None,
    motiv: str,
    actiune: str,
    acum: dt.datetime | None = None,
) -> None:
    r.stare, r.motiv, r.actualizat_la = stare, motiv[:300], acum or dt.datetime.now(dt.UTC)
    if utilizator_id is not None:
        r.decis_de, r.decis_la = utilizator_id, r.actualizat_la
    db.flush()
    audit.record(
        db,
        actiune,
        obiect_tip="lectie",
        obiect_id=r.id,
        tenant_id=r.tenant_id,
        utilizator_id=utilizator_id,
        actor_tip="utilizator" if utilizator_id else "sistem",
        detalii={"lectie": r.cheie, "motiv": motiv[:120], "a_ajutat": r.a_ajutat, "a_daunat": r.a_daunat},
    )


def aproba(
    db: Session, lectie_id: uuid.UUID, *, utilizator_id: uuid.UUID, rol: Rol, acum: dt.datetime | None = None
) -> Lectie:
    """Propusă → activă. Constituția (F11.5) poate refuza: învățarea înghețată sau o promovare deja făcută
    pe același domeniu în ultimele 7 zile (`ConstitutieIncalcata`)."""
    r = _lectie(db, lectie_id)
    if r.stare != "propusa":
        raise CuratorRefuzat("doar o lecție propusă se poate aproba")
    constitutie.poate_promova(db, r.tenant_id, r.domeniu_tip, r.domeniu, acum=acum)
    if r.sensibila and rol is not Rol.PROPRIETAR:
        raise CuratorRefuzat("lecția atinge conformitatea, prețurile sau promisiunile: o aprobă proprietarul")
    n = db.execute(
        select(func.count())
        .select_from(Lectie)
        .where(
            Lectie.tenant_id == r.tenant_id,
            Lectie.stare == "activa",
            Lectie.domeniu_tip == r.domeniu_tip,
            Lectie.domeniu == r.domeniu,
        )
    ).scalar_one()
    if n >= MAX_ACTIVE:
        raise CuratorRefuzat(f"domeniul are deja {MAX_ACTIVE} de lecții active: retrage una întâi")
    _muta(
        db, r, "activa", utilizator_id=utilizator_id, motiv="", actiune="invatare.lectie_aprobata", acum=acum
    )
    return r


def respinge(db: Session, lectie_id: uuid.UUID, *, utilizator_id: uuid.UUID, motiv: str) -> Lectie:
    r = _lectie(db, lectie_id)
    if r.stare != "propusa":
        raise CuratorRefuzat("doar o lecție propusă se poate respinge")
    if len(motiv.strip()) < 3:
        raise CuratorRefuzat("scrie pe scurt de ce respingi lecția")
    _muta(
        db,
        r,
        "respinsa",
        utilizator_id=utilizator_id,
        motiv=motiv.strip(),
        actiune="invatare.lectie_respinsa",
    )
    return r


def retrage(db: Session, lectie_id: uuid.UUID, *, utilizator_id: uuid.UUID | None, motiv: str) -> Lectie:
    """Anularea unei promovări (11.6, punctul 8): lecția activă iese din context, cu urmă."""
    r = _lectie(db, lectie_id)
    if r.stare != "activa":
        raise CuratorRefuzat("doar o lecție activă se poate retrage")
    _muta(
        db, r, "retrasa", utilizator_id=utilizator_id, motiv=motiv.strip(), actiune="invatare.lectie_retrasa"
    )
    return r


def de_retras(a_ajutat: int, a_daunat: int) -> bool:
    """Nucleu pur (11.3): „a dăunat” depășește „a ajutat”."""
    return a_daunat > a_ajutat


def noteaza(db: Session, lectie_id: uuid.UUID, *, a_ajutat: bool) -> Lectie:
    """Un contor +1; lecția activă care a dăunat mai mult decât a ajutat se retrage automat."""
    r = _lectie(db, lectie_id)
    if a_ajutat:
        r.a_ajutat += 1
    else:
        r.a_daunat += 1
    r.actualizat_la = dt.datetime.now(dt.UTC)
    if r.stare == "activa" and de_retras(r.a_ajutat, r.a_daunat):
        _muta(
            db, r, "retrasa", utilizator_id=None, motiv="a dăunat mai des decât a ajutat",
            actiune="invatare.lectie_retrasa",
        )  # fmt: skip
    db.flush()
    return r


def pentru_livrabil(db: Session, lv: productie.Livrabil) -> list[Lectie]:
    """Lecțiile active care se aplică livrabilului: ale clientului, ale canalului lui și ale autorului."""
    toate = active(db, lv.tenant_id)
    potrivite = [
        x
        for x in toate
        if x.domeniu_tip == "client"
        or (x.domeniu_tip == "canal" and x.domeniu == lv.canal)
        or (x.domeniu_tip == "agent" and x.domeniu == "autor")
    ]
    return potrivite[:MAX_IN_CONTEXT]


def _context_autor(db: Session, lv: productie.Livrabil) -> str:
    lectii = pentru_livrabil(db, lv)
    if not lectii:
        return ""
    for x in lectii:
        db.execute(
            pg_insert(LectieFolosita)
            .values(tenant_id=lv.tenant_id, livrabil_id=lv.id, lectie_id=x.id)
            .on_conflict_do_nothing()
        )
    return "Lecții din playbook (ține cont de ele):\n" + "\n".join(f"- {x.text}" for x in lectii)


def _dupa_decizie(
    db: Session, ap: productie.Aprobare, lv: productie.Livrabil, hotarare: productie.Hotarare
) -> None:
    """Decizia omului actualizează contoarele lecțiilor folosite la acest livrabil, o singură dată."""
    if hotarare not in (productie.Hotarare.APROBAT, productie.Hotarare.RESPINS):
        return
    with constitutie.flux_invatare(db):  # contoarele sunt scriere a învățării: sub gardul Constituției
        folosite = list(
            db.execute(
                select(LectieFolosita.lectie_id).where(
                    LectieFolosita.livrabil_id == lv.id, LectieFolosita.socotit.is_(False)
                )
            ).scalars()
        )
        for lectie_id in folosite:
            noteaza(db, lectie_id, a_ajutat=hotarare is productie.Hotarare.APROBAT)
        if folosite:
            db.execute(
                update(LectieFolosita)
                .where(LectieFolosita.livrabil_id == lv.id, LectieFolosita.lectie_id.in_(folosite))
                .values(socotit=True)
            )


def folosite_la(db: Session, livrabil_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        db.execute(
            select(LectieFolosita.lectie_id).where(LectieFolosita.livrabil_id == livrabil_id)
        ).scalars()
    )


scriere.inregistreaza_adaos_context(_context_autor)
productie.aprobari.inregistreaza_dupa_decizie(_dupa_decizie)
