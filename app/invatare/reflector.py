"""Reflectorul (F11.1, docs/11 §11.3, treapta N3): după un lot închis de postări măsurate, compară
rezultatele, verdictele validatorilor și deciziile oamenilor și PROPUNE lecții scurte, fiecare cu dovezi.

Nu activează nimic: o propunere devine lecție activă doar prin Curator și aprobare (F11.2). Nu atinge
validatorii, regulile sau faptele (Constituția, 11.6): doar scrie rânduri `propusa` în `lectii`.

- **Lotul.** Postările clientului cu recompensă citită (F10.3), de la sfârșitul lotului anterior încoace. Se
  închide când sunt cel puțin `MINIM_LOT` (20, din 11.2); sub prag nu se propune nimic.
- **Regulile** (deterministe, nuclee pure; pragurile sunt de pornire [I]):
  - *rezultate*: un tipar de hook sau un slot cu cel puțin `MINIM_GRUP` postări, a cărui medie e cu cel
    puțin `PRAG_DIFERENTA` peste sau sub media lotului (același tip de recompensă) → „folosește mai des” /
    „folosește mai rar”;
  - *verdicte*: o regulă de validator care a oprit cel puțin `MINIM_REPETARI` livrabile din lot → „evită din
    prima ciornă…”;
  - *decizii*: un motiv de respingere dat de om de cel puțin `MINIM_REPETARI` ori → lecție pe acel motiv.
- **Lecții sensibile.** Cele care ating conformitatea, prețurile sau promisiunile (regulile G2/G9 și motivele
  „fapt greșit”, „conformitate”) sunt marcate și cer aprobarea proprietarului (11.3).
- Formularea e un șablon determinist, cu cifrele din dovezi. Diferența dintre ciornă și versiunea editată
  de om (exemplele de aur, F6.7) NU este încă citită de Reflector; nici formularea cu model.
"""

import datetime as dt
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app import productie, validare
from app.analiza import EtichetePostare, etichete
from app.ids import new_id
from app.invatare.modele import Lectie, LotReflectie
from app.operare import audit

MINIM_LOT = 20  # 11.2: „20 de livrabile închise”
MINIM_GRUP = 3
MINIM_REPETARI = 3
PRAG_DIFERENTA = 0.25  # cu cât trebuie să difere media grupului de media lotului
TIP = "interactiuni_pe_afisari"
VALIDATORI_SENSIBILI = ("G2", "G9")  # fapte și juridic: prețuri, promisiuni, conformitate
MOTIVE_SENSIBILE = ("fapt_gresit", "conformitate")


@dataclass(frozen=True)
class Postare:
    """Ce vede Reflectorul dintr-o postare a lotului."""

    livrabil_id: str
    canal: str
    tipar_hook: str
    slot: str
    recompensa: float


@dataclass(frozen=True)
class Propunere:
    cheie: str
    domeniu_tip: str
    domeniu: str
    text: str
    sursa: str
    dovezi: list[dict[str, Any]] = field(default_factory=list)
    sensibila: bool = False


def _la_suta(x: float) -> str:
    return f"{x * 100:.1f}".replace(".", ",")


def din_rezultate(postari: list[Postare]) -> list[Propunere]:
    """Nucleu pur: tiparele de hook și sloturile care ies din media lotului."""
    if not postari:
        return []
    medie = sum(p.recompensa for p in postari) / len(postari)
    out: list[Propunere] = []
    for camp, nume in (("tipar_hook", "hook-urile de tip"), ("slot", "postările de")):
        grupuri: dict[str, list[Postare]] = {}
        for p in postari:
            if getattr(p, camp):
                grupuri.setdefault(getattr(p, camp), []).append(p)
        for valoare, g in sorted(grupuri.items()):
            if len(g) < MINIM_GRUP or medie <= 0:
                continue
            m = sum(p.recompensa for p in g) / len(g)
            abatere = (m - medie) / medie
            if abs(abatere) < PRAG_DIFERENTA:
                continue
            sens = "mai_des" if abatere > 0 else "mai_rar"
            eticheta = etichete.ETICHETE_HOOK.get(valoare, valoare)
            out.append(
                Propunere(
                    cheie=f"rezultate:{camp}:{valoare}:{sens}"[:200],
                    domeniu_tip="client",
                    domeniu="",
                    text=(
                        f"Folosește {'mai des' if abatere > 0 else 'mai rar'} {nume} „{eticheta}”: "
                        f"{_la_suta(m)} interacțiuni la 100 de afișări, față de {_la_suta(medie)} "
                        f"media lotului (din {len(g)} postări)."
                    )[:400],
                    sursa="rezultate",
                    dovezi=[
                        {
                            "livrabil_id": p.livrabil_id,
                            "canal": p.canal,
                            "la_suta": round(p.recompensa * 100, 1),
                        }
                        for p in g[:10]
                    ],
                )
            )
    return out


def din_verdicte(esecuri: list[tuple[str, str, str]]) -> list[Propunere]:
    """Nucleu pur. `esecuri`: (livrabil, validator, regulă) pentru verdictele care au oprit un livrabil. O
    regulă care a oprit cel puțin `MINIM_REPETARI` livrabile diferite devine propunere pentru autor."""
    pe_regula: dict[tuple[str, str], set[str]] = {}
    for livrabil, validator, regula in esecuri:
        if regula:
            pe_regula.setdefault((validator, regula), set()).add(livrabil)
    out = []
    for (validator, regula), livrabile in sorted(pe_regula.items()):
        if len(livrabile) < MINIM_REPETARI:
            continue
        out.append(
            Propunere(
                cheie=f"verdicte:{regula}"[:200],
                domeniu_tip="agent",
                domeniu="autor",
                text=(
                    f"Evită din prima ciornă ce oprește regula {regula} ({validator}): a oprit "
                    f"{len(livrabile)} livrabile din lot."
                ),
                sursa="verdicte",
                dovezi=[
                    {"livrabil_id": i, "validator": validator, "regula": regula}
                    for i in sorted(livrabile)[:10]
                ],
                sensibila=validator in VALIDATORI_SENSIBILI,
            )
        )
    return out


def din_decizii(respingeri: list[tuple[str, str]]) -> list[Propunere]:
    """Nucleu pur. `respingeri`: (livrabil, codul motivului) pentru respingerile date de oameni."""
    numar = Counter(cod for _, cod in respingeri if cod and cod != "altceva")
    out = []
    for cod, n in sorted(numar.items()):
        if n < MINIM_REPETARI:
            continue
        eticheta = productie.MOTIVE_RESPINGERE.get(cod, cod)
        out.append(
            Propunere(
                cheie=f"decizii:{cod}",
                domeniu_tip="client",
                domeniu="",
                text=(
                    f"Oamenii au respins de {n} ori pentru „{eticheta}”: "
                    "verifică asta înainte de a cere aprobarea."
                ),
                sursa="decizii",
                dovezi=[{"livrabil_id": i, "motiv": c} for i, c in respingeri if c == cod][:10],
                sensibila=cod in MOTIVE_SENSIBILE,
            )
        )
    return out


def _postari(db: Session, tenant_id: uuid.UUID, de_la: dt.datetime | None) -> list[EtichetePostare]:
    q = select(EtichetePostare).where(
        EtichetePostare.tenant_id == tenant_id,
        EtichetePostare.recompensa.is_not(None),
        EtichetePostare.recompensa_tip == TIP,
    )
    if de_la is not None:
        q = q.where(EtichetePostare.actualizat_la > de_la)
    return list(db.execute(q.order_by(EtichetePostare.actualizat_la)).scalars())


def reflecteaza(db: Session, tenant_id: uuid.UUID, *, acum: dt.datetime | None = None) -> LotReflectie | None:
    """Închide lotul curent al clientului și scrie propunerile. `None` dacă lotul nu are încă `MINIM_LOT`
    postări măsurate. O propunere cu aceeași cheie ca o lecție existentă nu se dublează."""
    acum = acum or dt.datetime.now(dt.UTC)
    ultimul = db.execute(
        select(func.max(LotReflectie.pana_la)).where(LotReflectie.tenant_id == tenant_id)
    ).scalar_one_or_none()
    randuri = _postari(db, tenant_id, ultimul)
    if len(randuri) < MINIM_LOT:
        return None
    ids = [r.livrabil_id for r in randuri]
    postari = [
        Postare(
            str(r.livrabil_id),
            r.canal,
            r.tipar_hook,
            etichete.eticheta_slot(r.zi_saptamana, r.ora),
            float(r.recompensa or 0.0),
        )
        for r in randuri
    ]
    V = validare.VerdictSalvat
    esecuri = [
        (str(lid), str(validator), str((dovezi or [{}])[0].get("regula", "")))
        for lid, validator, dovezi in db.execute(
            select(V.livrabil_id, V.validator, V.dovezi).where(
                V.tenant_id == tenant_id, V.livrabil_id.in_(ids), V.rezultat == "esec"
            )
        ).all()
    ]
    A = productie.Aprobare
    respingeri = [
        (str(lid), str(cod or ""))
        for lid, cod in db.execute(
            select(A.livrabil_id, A.motiv_cod).where(
                A.tenant_id == tenant_id, A.livrabil_id.in_(ids), A.stare == "respins"
            )
        ).all()
    ]
    propuneri = [*din_rezultate(postari), *din_verdicte(esecuri), *din_decizii(respingeri)]
    lot = LotReflectie(
        tenant_id=tenant_id,
        de_la=ultimul or min(r.actualizat_la for r in randuri) - dt.timedelta(seconds=1),
        pana_la=max(max(r.actualizat_la for r in randuri), acum),
        postari=len(randuri),
    )
    db.add(lot)
    db.flush()
    noi = 0
    for p in propuneri:
        r = db.execute(
            pg_insert(Lectie)
            .values(
                id=new_id(),
                tenant_id=tenant_id,
                lot_id=lot.id,
                cheie=p.cheie,
                domeniu_tip=p.domeniu_tip,
                domeniu=p.domeniu,
                text=p.text,
                dovezi=p.dovezi,
                sursa=p.sursa,
                sensibila=p.sensibila,
            )
            .on_conflict_do_nothing(constraint="lectii_unic")
            .returning(Lectie.id)
        )
        noi += r.first() is not None
    lot.propuneri = noi
    audit.record(
        db,
        "invatare.lot_reflectat",
        obiect_tip="lot",
        obiect_id=lot.id,
        tenant_id=tenant_id,
        actor_tip="sistem",
        detalii={"postari": len(randuri), "propuneri": noi},
    )
    return lot


def propuneri(db: Session, tenant_id: uuid.UUID | None = None, *, limita: int = 100) -> list[Lectie]:
    q = select(Lectie).where(Lectie.stare == "propusa").order_by(Lectie.creat_la.desc()).limit(limita)
    if tenant_id is not None:
        q = q.where(Lectie.tenant_id == tenant_id)
    return list(db.execute(q).scalars())
