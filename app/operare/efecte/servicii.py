"""Datele efectelor externe: cerere (outbox), citire, tranziții după tabel, anulare, reluare, pauzele
conectorilor.

Nu atinge motorul și nu cheamă conectori (asta face `executor`). `inregistreaza` se apelează în ACEEAȘI
tranzacție cu
schimbarea de stare care cere efectul (de exemplu `productie.muta(... IN_PUBLICARE)`): ori se întâmplă
ambele, ori
niciuna.
"""

import contextlib
import hashlib
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app import productie
from app.db import get_engine
from app.ids import new_id
from app.operare import audit, evenimente
from app.operare.efecte.modele import Efect, PauzaConector
from app.operare.efecte.stari import OPRIRE_PE_TIP, Stare, Tip, cheia, este_permisa
from app.operare.jurnale import PARTI_INTERZISE
from app.operare.opriri import este_oprit
from app.productie import Stare as StareLivrabil

MOTIV_MAXIM = 300
MESAJ_MAXIM = 500


class EroareEfect(Exception):
    """Baza erorilor executorului de efecte."""


class EfectRefuzat(EroareEfect):
    """Efectul nu se poate cere: livrabilul nu a ajuns legitim în starea care îl permite (poarta de stare)."""


class EfectInexistent(EroareEfect):
    """Nu există, sau aparține altui client (izolarea pe client îl ascunde)."""


class TranzitieEfectNepermisa(EroareEfect):
    pass


# Starea livrabilului în care un efect de acest tip are voie să fie cerut și să plece (poarta de stare, 7.2).
STARE_LIVRABIL_PE_TIP: dict[Tip, StareLivrabil] = {Tip.PUBLICARE: StareLivrabil.IN_PUBLICARE}


@dataclass(frozen=True)
class Cerere:
    efect: Efect
    nou: bool  # False: același efect fusese deja cerut; se întoarce rândul primei cereri


def _fara_secrete(valoare: Any, cale: str = "payload") -> None:
    """Payload-ul efectului nu poartă secrete (21.2): tokenurile se rezolvă în conector, la execuție."""
    if isinstance(valoare, dict):
        for k, v in valoare.items():
            if any(p in str(k).lower() for p in PARTI_INTERZISE):
                raise EfectRefuzat(f"{cale}.{k}: cheie care pare secret; tokenurile se rezolvă în conector")
            _fara_secrete(v, f"{cale}.{k}")
    elif isinstance(valoare, list | tuple):
        for v in valoare:
            _fara_secrete(v, cale)


def inregistreaza(
    db: Session, livrabil_id: uuid.UUID, *, tip: Tip = Tip.PUBLICARE, payload: dict[str, Any] | None = None
) -> Cerere:
    """Pune efectul în tabelul „de trimis”. Poarta de stare: livrabilul trebuie să fie în starea
    potrivită tipului
    (pentru publicare, `in_publicare`, la care se ajunge doar prin `productie.muta`, deci cu aprobare
    sau autonomie).
    Cheia (client, livrabil, canal, versiune, tip) este unică: a doua cerere întoarce rândul primei
    (`nou=False`)."""
    livrabil = productie.citeste(db, livrabil_id)
    if livrabil is None:
        raise EfectRefuzat("livrabilul nu există")
    necesar = STARE_LIVRABIL_PE_TIP[tip]
    if livrabil.stare != necesar.value:
        raise EfectRefuzat(
            f"efectul „{tip.value}” se cere doar pentru un livrabil „{productie.ETICHETE[necesar]}”; "
            f"acesta e „{productie.ETICHETE[StareLivrabil(livrabil.stare)]}”"
        )
    continut = payload or {}
    _fara_secrete(continut)
    if len(json.dumps(continut, default=str)) > 16000:
        raise EfectRefuzat("payload prea mare: pasează identificatorul conținutului, nu conținutul")
    cheie = cheia(livrabil.tenant_id, livrabil.id, livrabil.canal, livrabil.versiune, tip)
    id_nou = new_id()
    inserat = db.execute(
        pg_insert(Efect)
        .values(
            id=id_nou,
            tenant_id=livrabil.tenant_id,
            livrabil_id=livrabil.id,
            canal=livrabil.canal,
            versiune=livrabil.versiune,
            tip=tip.value,
            cheia=cheie,
            payload=continut,
        )
        .on_conflict_do_nothing(index_elements=["cheia"])
        .returning(Efect.id)
    ).first()
    efect = db.execute(select(Efect).where(Efect.cheia == cheie)).scalar_one()
    nou = inserat is not None
    if nou:
        audit.record(
            db,
            "efect.cerut",
            obiect_tip="efect",
            obiect_id=efect.id,
            tenant_id=efect.tenant_id,
            actor_tip="sistem",
            detalii={
                "livrabil": efect.livrabil_id,
                "canal": efect.canal,
                "versiune": efect.versiune,
                "tip": tip.value,
            },
        )
        evenimente.emite(
            db,
            "efect.cerut",
            sursa="executor",
            obiect_tip="efect",
            obiect_id=efect.id,
            tenant_id=efect.tenant_id,
            date={"tip": tip.value, "canal": efect.canal, "versiune": efect.versiune},
        )
    return Cerere(efect, nou)


# --- citire -------------------------------------------------------------------------------------------------


def citeste(db: Session, efect_id: uuid.UUID) -> Efect | None:
    return db.get(Efect, efect_id)


def blocheaza(db: Session, efect_id: uuid.UUID) -> Efect:
    rand = db.execute(
        select(Efect).where(Efect.id == efect_id).with_for_update().execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if rand is None:
        raise EfectInexistent(str(efect_id))
    return rand


def ale_livrabilului(db: Session, livrabil_id: uuid.UUID) -> list[Efect]:
    return list(
        db.execute(select(Efect).where(Efect.livrabil_id == livrabil_id).order_by(Efect.creat_la)).scalars()
    )


def listeaza(db: Session, *, stari: tuple[Stare, ...] | None = None, limita: int = 200) -> list[Efect]:
    q = select(Efect).order_by(Efect.actualizat_la.desc()).limit(limita)
    if stari:
        q = q.where(Efect.stare.in_([s.value for s in stari]))
    return list(db.execute(q).scalars())


def numara_pe_stare(db: Session) -> dict[str, int]:
    return dict(db.execute(select(Efect.stare, func.count()).group_by(Efect.stare)).all())


# --- tranziții
# -------------------------------------------------------------------------------------------------


def muta_efect(db: Session, efect: Efect, la: Stare, **campuri: Any) -> None:
    """Singura cale de schimbare a stării unui efect: perechea trebuie să fie în `stari.TABEL`
    (declanșatorul din
    bază o impune încă o dată). Presupune rândul blocat."""
    din = Stare(efect.stare)
    if not este_permisa(din, la):
        raise TranzitieEfectNepermisa(f"efect {efect.id}: din „{din.value}” în „{la.value}” nu e permis")
    efect.stare = la.value
    for k, v in campuri.items():
        setattr(efect, k, v)
    efect.actualizat_la = func.now()
    db.flush()


def motiv_nevalabil(db: Session, efect: Efect) -> str | None:
    """Mai este efectul valabil? Versiunea livrabilului trebuie să fie aceeași, iar starea lui să-l
    permită."""
    livrabil = productie.citeste(db, efect.livrabil_id)
    if livrabil is None:
        return "livrabilul nu mai există"
    if livrabil.versiune != efect.versiune:
        return f"versiunea livrabilului s-a schimbat (v{efect.versiune} → v{livrabil.versiune})"
    necesar = STARE_LIVRABIL_PE_TIP[Tip(efect.tip)]
    if livrabil.stare != necesar.value:
        acum = productie.ETICHETE[StareLivrabil(livrabil.stare)]
        return f"livrabilul nu mai este „{productie.ETICHETE[necesar]}” (e „{acum}”)"
    return None


def motiv_oprit(db: Session, efect: Efect) -> str | None:
    """Oprirea care ține efectul pe loc acum (global pe clasă sau pe client), sau `None`."""
    from app.operare import opriri  # evită ciclul la import

    tip_oprire = OPRIRE_PE_TIP[Tip(efect.tip)]
    if este_oprit(db, tip_oprire, tenant_id=efect.tenant_id):
        if opriri.este_oprit(db, opriri.Oprire.CLIENT, tenant_id=efect.tenant_id):
            return "oprit: clientul"
        return f"oprit: {opriri.ETICHETE[tip_oprire].lower()}"
    return None


def anuleaza(
    db: Session, efect_id: uuid.UUID, *, motiv: str, utilizator_id: uuid.UUID | None = None
) -> Efect:
    """Anulează un efect care nu e final (de un om, sau pentru că nu mai e valabil). Nu poate anula un efect
    `în trimitere`: o încercare e în curs și rezultatul ei trebuie verificat la platformă."""
    motiv = motiv.strip()[:MOTIV_MAXIM]
    if len(motiv) < 3:
        raise ValueError("anularea cere un motiv (cel puțin 3 caractere)")
    efect = blocheaza(db, efect_id)
    if Stare(efect.stare) is Stare.IN_TRIMITERE:
        raise TranzitieEfectNepermisa("o încercare e în curs; așteaptă rezultatul ei")
    muta_efect(db, efect, Stare.ANULAT, motiv=motiv)
    audit.record(
        db,
        "efect.anulat",
        obiect_tip="efect",
        obiect_id=efect.id,
        tenant_id=efect.tenant_id,
        utilizator_id=utilizator_id,
        actor_tip=None if utilizator_id else "sistem",
        detalii={"motiv": motiv},
    )
    return efect


def repune_in_asteptare(db: Session, efect_id: uuid.UUID, *, motiv: str, utilizator_id: uuid.UUID) -> Efect:
    """Un om reia un efect `eșuat`: înapoi în așteptare. Înainte de trimitere, executorul
    întreabă totuși `verifica` (efectul poate exista la platformă)."""
    motiv = motiv.strip()[:MOTIV_MAXIM]
    if len(motiv) < 3:
        raise ValueError("reluarea cere un motiv (cel puțin 3 caractere)")
    efect = blocheaza(db, efect_id)
    # `incercari` NU se resetează: cât timp e > 0, următoarea încercare întreabă întâi `verifica` (vezi
    # executor)
    muta_efect(
        db, efect, Stare.IN_ASTEPTARE, eroare_cod=None, eroare_mesaj=None, motiv=motiv, programat_la=None
    )
    audit.record(
        db,
        "efect.reluat_de_om",
        obiect_tip="efect",
        obiect_id=efect.id,
        tenant_id=efect.tenant_id,
        utilizator_id=utilizator_id,
        detalii={"motiv": motiv},
    )
    return efect


# --- pauza conectorilor
# -----------------------------------------------------------------------------------------


def pauza(db: Session, tenant_id: uuid.UUID, canal: str) -> PauzaConector | None:
    return db.get(PauzaConector, (tenant_id, canal))


def pune_pauza(db: Session, tenant_id: uuid.UUID, canal: str, motiv: str) -> bool:
    """Canalul unui client intră pe pauză (autentificare expirată). Întoarce `True` dacă pauza e nouă."""
    nou = pauza(db, tenant_id, canal) is None
    if nou:
        db.add(PauzaConector(tenant_id=tenant_id, canal=canal, motiv=motiv[:MOTIV_MAXIM]))
        db.flush()
    return nou


def ridica_pauza(db: Session, tenant_id: uuid.UUID, canal: str, *, utilizator_id: uuid.UUID | None) -> bool:
    p = pauza(db, tenant_id, canal)
    if p is None:
        return False
    db.delete(p)
    db.flush()
    audit.record(
        db,
        "conector.reautorizat",
        obiect_tip="conector",
        obiect_id=f"{tenant_id}:{canal}",
        tenant_id=tenant_id,
        utilizator_id=utilizator_id,
        actor_tip=None if utilizator_id else "sistem",
        detalii={"canal": canal},
    )
    return True


def pauze(db: Session) -> list[PauzaConector]:
    return list(db.execute(select(PauzaConector).order_by(PauzaConector.de_la)).scalars())


# --- o singură încercare odată
# ---------------------------------------------------------------------------------


@contextlib.contextmanager
def incuietoare(efect_id: uuid.UUID) -> Iterator[bool]:
    """Încuietoare de sesiune în Postgres, pe un efect: o singură încercare odată. Se ține pe o
    conexiune proprie,
    deci dispare singură dacă procesul moare (nu rămâne niciodată blocat). Întoarce `False` dacă
    altcineva o ține."""
    cheie = int.from_bytes(hashlib.sha256(efect_id.bytes).digest()[:8], "big", signed=True)
    conexiune = get_engine().connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        luata = bool(conexiune.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": cheie}).scalar())
        try:
            yield luata
        finally:
            if luata:
                conexiune.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": cheie})
    finally:
        conexiune.close()
