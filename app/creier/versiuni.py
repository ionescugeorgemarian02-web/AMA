"""Serviciul intrărilor versionate ale Creierului (F4.1, docs/10 §10.4–10.5, docs/20 §20.1).

Reguli:
- orice schimbare creează o versiune nouă (`propune_schimbare`); cea veche rămâne citibilă și nemodificabilă
  (declanșator în bază, migrarea 0021);
- o versiune trece `ciorna` -> `propus` -> `aprobat` -> `retras`; aprobarea unei versiuni retrage versiunea
  aprobată înainte (`inlocuita`) și propunerile mai vechi, în aceeași tranzacție (§10.4);
- aprobarea o face un OM (`utilizator_id`), cu excepția compartimentelor care se completează automat
  (`InfoCompartiment.aprobare_sistem`), unde `aproba(..., prin_sistem=True)`;
- sursa e obligatorie la orice versiune; valabilitatea (de la / până la) face parte din versiune;
- fiecare schimbare de stare lasă o urmă în audit, în aceeași tranzacție.

Sesiunea `db` poartă clientul (RLS). Funcțiile NU fac commit: apelantul îl face (sau `sesiune()` la ieșire).
"""

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.creier import compartimente as cmp
from app.creier.compartimente import (
    CauzaRetragere,
    Compartiment,
    ContinutInvalid,
    Nivel,
    PoartaInchisa,
    Stare,
    SursaTip,
)
from app.creier.diferenta import Schimbare, diferenta
from app.creier.modele import IntrareCreier, VersiuneCreier
from app.ids import new_id
from app.operare import audit


class EroareCreier(Exception):
    """Baza erorilor serviciului."""


class IntrareInexistenta(EroareCreier):
    pass


class VersiuneInexistenta(EroareCreier):
    pass


class TranzitieNepermisa(EroareCreier):
    pass


class RegulaCreier(EroareCreier):
    """Încălcarea unei reguli: nivel nepermis compartimentului, sursă lipsă, aprobare automată nepermisă …"""


@dataclass(frozen=True)
class Sursa:
    """De unde vine o versiune. `ref`: id-ul documentului / pasajului sau URL-ul; `citat`: textul exact."""

    tip: SursaTip
    ref: str | None = None
    citat: str | None = None
    detalii: dict[str, Any] = field(default_factory=dict)


def _acum(acum: dt.datetime | None) -> dt.datetime:
    return acum or dt.datetime.now(dt.UTC)


def _verifica_sursa(sursa: Sursa, utilizator_id: uuid.UUID | None) -> None:
    if sursa.tip in cmp.SURSE_CU_REFERINTA and not (sursa.ref or "").strip():
        raise RegulaCreier(f"sursa de tip „{sursa.tip.value}” cere o referință")
    if sursa.tip in cmp.SURSE_CU_AUTOR and utilizator_id is None:
        raise RegulaCreier(f"sursa de tip „{sursa.tip.value}” cere un autor (utilizator)")
    if sursa.citat is not None and len(sursa.citat) > 4000:
        raise RegulaCreier("citatul sursei are cel mult 4000 de caractere")


def _verifica_valabilitate(de_la: dt.datetime | None, pana_la: dt.datetime | None) -> None:
    for v in (de_la, pana_la):
        if v is not None and v.tzinfo is None:
            raise RegulaCreier("momentele de valabilitate trebuie să aibă fus orar (UTC)")
    if de_la is not None and pana_la is not None and pana_la <= de_la:
        raise RegulaCreier("„valabil până la” trebuie să fie după „valabil de la”")


# --- citire


def intrare(db: Session, intrare_id: uuid.UUID) -> IntrareCreier:
    r = db.get(IntrareCreier, intrare_id)
    if r is None:  # inexistentă sau a altui client (RLS)
        raise IntrareInexistenta(str(intrare_id))
    return r


def gaseste_intrare(
    db: Session,
    *,
    tenant_id: uuid.UUID | None,
    compartiment: Compartiment,
    cheie: str,
    nivel: Nivel = Nivel.CLIENT,
) -> IntrareCreier | None:
    q = select(IntrareCreier).where(
        IntrareCreier.compartiment == compartiment.value,
        IntrareCreier.cheie == cheie,
        IntrareCreier.nivel == nivel.value,
    )
    q = q.where(
        IntrareCreier.tenant_id.is_(None) if tenant_id is None else IntrareCreier.tenant_id == tenant_id
    )
    return db.execute(q).scalar_one_or_none()


def _blocheaza(db: Session, intrare_id: uuid.UUID) -> IntrareCreier:
    """Intrarea, cu schimbările ei serializate până la sfârșitul tranzacției (aplicația nu are drept de
    UPDATE pe intrări, deci nu se folosește `FOR UPDATE`)."""
    i = intrare(db, intrare_id)
    db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(str(intrare_id), 0))))
    return i


def citeste(db: Session, intrare_id: uuid.UUID, versiune: int) -> VersiuneCreier:
    """O versiune anume, în orice stare (versiunile vechi rămân citibile)."""
    v = db.execute(
        select(VersiuneCreier).where(VersiuneCreier.intrare_id == intrare_id, VersiuneCreier.nr == versiune)
    ).scalar_one_or_none()
    if v is None:
        raise VersiuneInexistenta(f"{intrare_id}@{versiune}")
    return v


def istoric(db: Session, intrare_id: uuid.UUID) -> list[VersiuneCreier]:
    """Toate versiunile, de la prima la ultima."""
    return list(
        db.execute(
            select(VersiuneCreier).where(VersiuneCreier.intrare_id == intrare_id).order_by(VersiuneCreier.nr)
        ).scalars()
    )


def versiune_aprobata(db: Session, intrare_id: uuid.UUID) -> VersiuneCreier | None:
    """Versiunea aprobată acum (cel mult una), indiferent de valabilitate."""
    return db.execute(
        select(VersiuneCreier).where(
            VersiuneCreier.intrare_id == intrare_id, VersiuneCreier.stare == "aprobat"
        )
    ).scalar_one_or_none()


def la_data(db: Session, intrare_id: uuid.UUID, la: dt.datetime) -> VersiuneCreier | None:
    """Versiunea în vigoare la momentul `la`: aprobată până atunci și neretrasă încă, iar `la` cade în
    valabilitatea ei. Pentru `la` = acum este versiunea aprobată valabilă."""
    q = (
        select(VersiuneCreier)
        .where(
            VersiuneCreier.intrare_id == intrare_id,
            VersiuneCreier.aprobat_la.is_not(None),
            VersiuneCreier.aprobat_la <= la,
            (VersiuneCreier.retras_la.is_(None)) | (VersiuneCreier.retras_la > la),
            (VersiuneCreier.valabil_de_la.is_(None)) | (VersiuneCreier.valabil_de_la <= la),
            (VersiuneCreier.valabil_pana_la.is_(None)) | (VersiuneCreier.valabil_pana_la > la),
        )
        .order_by(VersiuneCreier.nr.desc())
        .limit(1)
    )
    return db.execute(q).scalar_one_or_none()


def diferenta_versiuni(db: Session, intrare_id: uuid.UUID, a: int, b: int) -> list[Schimbare]:
    """Ce s-a schimbat în conținut de la versiunea `a` la versiunea `b`."""
    return diferenta(citeste(db, intrare_id, a).continut, citeste(db, intrare_id, b).continut)


def lista(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    compartiment: Compartiment | None = None,
    nivel: Nivel = Nivel.CLIENT,
) -> list[tuple[IntrareCreier, VersiuneCreier | None]]:
    """Intrările clientului, fiecare cu versiunea aprobată acum (sau `None`)."""
    q = (
        select(IntrareCreier, VersiuneCreier)
        .outerjoin(
            VersiuneCreier,
            (VersiuneCreier.intrare_id == IntrareCreier.id) & (VersiuneCreier.stare == "aprobat"),
        )
        .where(IntrareCreier.nivel == nivel.value, IntrareCreier.tenant_id == tenant_id)
        .order_by(IntrareCreier.creat_la, IntrareCreier.id)
    )
    if compartiment is not None:
        q = q.where(IntrareCreier.compartiment == compartiment.value)
    return [(i, v) for i, v in db.execute(q).all()]


# --- scriere


def _poarta(
    db: Session, tenant_id: uuid.UUID | None, compartiment: Compartiment, continut: dict[str, Any]
) -> None:
    probleme = cmp.probleme_poarta(db, tenant_id, compartiment, continut)
    if probleme:
        raise cmp.PoartaInchisa(probleme)


def _urma(
    db: Session,
    actiune: str,
    i: IntrareCreier,
    v: VersiuneCreier,
    utilizator_id: uuid.UUID | None,
    **detalii: Any,
) -> None:
    audit.record(
        db,
        actiune,
        obiect_tip="creier_versiune",
        obiect_id=v.id,
        utilizator_id=utilizator_id,
        tenant_id=i.tenant_id,
        detalii={
            "compartiment": i.compartiment,
            "intrare": i.id,
            "versiune": v.nr,
            "stare": v.stare,
            **detalii,
        },
    )


def _adauga_versiune(
    db: Session,
    i: IntrareCreier,
    *,
    continut: dict[str, Any],
    sursa: Sursa,
    de_la: dt.datetime | None,
    pana_la: dt.datetime | None,
    motiv: str,
    utilizator_id: uuid.UUID | None,
    propus: bool,
    acum: dt.datetime,
) -> VersiuneCreier:
    comp = Compartiment(i.compartiment)
    continut = cmp.valideaza_continut(comp, continut)
    if propus:
        _poarta(db, i.tenant_id, comp, continut)
    _verifica_sursa(sursa, utilizator_id)
    _verifica_valabilitate(de_la, pana_la)
    ultima = db.execute(
        select(func.max(VersiuneCreier.nr)).where(VersiuneCreier.intrare_id == i.id)
    ).scalar_one()
    v = VersiuneCreier(
        id=new_id(),
        intrare_id=i.id,
        tenant_id=i.tenant_id,
        nr=(ultima or 0) + 1,
        continut=continut,
        text_cautare=cmp.text_de_cautare(continut),
        stare=Stare.PROPUS.value if propus else Stare.CIORNA.value,
        sursa_tip=sursa.tip.value,
        sursa_ref=sursa.ref,
        sursa_citat=sursa.citat,
        sursa_detalii=sursa.detalii,
        valabil_de_la=de_la,
        valabil_pana_la=pana_la,
        motiv=motiv[:500],
        creat_de=utilizator_id,
        creat_la=acum,
        propus_la=acum if propus else None,
    )
    db.add(v)
    db.flush()
    return v


def creeaza_intrare(
    db: Session,
    *,
    tenant_id: uuid.UUID | None,
    compartiment: Compartiment,
    continut: dict[str, Any],
    sursa: Sursa,
    cheie: str | None = None,
    nivel: Nivel = Nivel.CLIENT,
    valabil_de_la: dt.datetime | None = None,
    valabil_pana_la: dt.datetime | None = None,
    motiv: str = "",
    utilizator_id: uuid.UUID | None = None,
    propune: bool = True,
    acum: dt.datetime | None = None,
) -> tuple[IntrareCreier, VersiuneCreier]:
    """O intrare nouă cu prima ei versiune (`propus` implicit, `ciorna` cu `propune=False`).

    `cheie` identifică intrarea în compartiment (implicit un identificator nou; un compartiment cu o singură
    intrare, ca profilul de brand, folosește o cheie fixă). Nivelurile `nisa` / `platforma` cer
    `tenant_id=None` și se scriu doar din sesiune de agenție."""
    info = cmp.COMPARTIMENTE[compartiment]
    if nivel not in info.niveluri:
        raise RegulaCreier(f"compartimentul „{info.nume}” nu are nivelul „{nivel.value}”")
    if (nivel is Nivel.CLIENT) != (tenant_id is not None):
        raise RegulaCreier("nivelul „client” cere un client; nișa și platforma nu au client")
    if nivel is not Nivel.CLIENT and sursa.tip is not SursaTip.AGREGAT:
        raise RegulaCreier("nișa și platforma primesc doar tipare agregate (sursa „agregat”)")
    if nivel is Nivel.CLIENT and sursa.tip is SursaTip.AGREGAT:
        raise RegulaCreier("sursa „agregat” nu se potrivește unei intrări a clientului")
    ora = _acum(acum)
    i = IntrareCreier(
        id=new_id(),
        tenant_id=tenant_id,
        nivel=nivel.value,
        compartiment=compartiment.value,
        cheie=cheie or new_id().hex,
        creat_la=ora,
        creat_de=utilizator_id,
    )
    db.add(i)
    db.flush()
    v = _adauga_versiune(
        db, i, continut=continut, sursa=sursa, de_la=valabil_de_la, pana_la=valabil_pana_la, motiv=motiv,
        utilizator_id=utilizator_id, propus=propune, acum=ora,
    )  # fmt: skip
    _urma(db, "creier.intrare_creata", i, v, utilizator_id)
    return i, v


def propune_schimbare(
    db: Session,
    intrare_id: uuid.UUID,
    *,
    continut: dict[str, Any],
    sursa: Sursa,
    valabil_de_la: dt.datetime | None = None,
    valabil_pana_la: dt.datetime | None = None,
    motiv: str = "",
    utilizator_id: uuid.UUID | None = None,
    propune: bool = True,
    acum: dt.datetime | None = None,
) -> VersiuneCreier:
    """Schimbarea unei intrări = o versiune nouă (`nr + 1`). Versiunile vechi nu se ating."""
    i = _blocheaza(db, intrare_id)
    v = _adauga_versiune(
        db, i, continut=continut, sursa=sursa, de_la=valabil_de_la, pana_la=valabil_pana_la, motiv=motiv,
        utilizator_id=utilizator_id, propus=propune, acum=_acum(acum),
    )  # fmt: skip
    _urma(db, "creier.versiune_propusa", i, v, utilizator_id)
    return v


def trimite_spre_aprobare(
    db: Session,
    intrare_id: uuid.UUID,
    versiune: int,
    *,
    utilizator_id: uuid.UUID | None = None,
    acum: dt.datetime | None = None,
) -> VersiuneCreier:
    """`ciorna` → `propus`."""
    i = intrare(db, intrare_id)
    v = citeste(db, intrare_id, versiune)
    if v.stare != Stare.CIORNA.value:
        raise TranzitieNepermisa(
            f"doar o ciornă se trimite spre aprobare (versiunea {versiune} e „{v.stare}”)"
        )
    _poarta(db, i.tenant_id, Compartiment(i.compartiment), v.continut)
    v.stare = Stare.PROPUS.value
    v.propus_la = _acum(acum)
    db.flush()
    _urma(db, "creier.versiune_trimisa", i, v, utilizator_id)
    return v


def aproba(
    db: Session,
    intrare_id: uuid.UUID,
    versiune: int,
    *,
    utilizator_id: uuid.UUID | None,
    prin_sistem: bool = False,
    acum: dt.datetime | None = None,
) -> VersiuneCreier:
    """`propus` → `aprobat`. Versiunea aprobată înainte și propunerile mai vechi se retrag (`inlocuita`).

    Aprobarea o dă un om (`utilizator_id`). `prin_sistem=True` e permis doar compartimentelor cu aprobare
    automată (exemple, insight, memorie de performanță)."""
    ora = _acum(acum)
    i = _blocheaza(db, intrare_id)
    info = cmp.COMPARTIMENTE[Compartiment(i.compartiment)]
    if prin_sistem and not info.aprobare_sistem:
        raise RegulaCreier(f"„{info.nume}” se aprobă doar de un om")
    if not prin_sistem and utilizator_id is None:
        raise RegulaCreier("aprobarea cere un utilizator")
    v = citeste(db, intrare_id, versiune)
    if v.stare != Stare.PROPUS.value:
        raise TranzitieNepermisa(f"doar o versiune propusă se aprobă (versiunea {versiune} e „{v.stare}”)")
    if prin_sistem and cmp.cere_om(Compartiment(i.compartiment), v.continut):
        raise RegulaCreier(f"„{info.nume}”: această intrare se aprobă doar de un om")
    _poarta(db, i.tenant_id, Compartiment(i.compartiment), v.continut)
    for veche in istoric(db, intrare_id):
        if veche.nr < v.nr and veche.stare in (Stare.APROBAT.value, Stare.PROPUS.value, Stare.CIORNA.value):
            veche.stare = Stare.RETRAS.value
            veche.retras_la = ora
            veche.retras_cauza = CauzaRetragere.INLOCUITA.value
            veche.retras_de = utilizator_id
            veche.inlocuita_de = v.nr
            db.flush()
    v.stare = Stare.APROBAT.value
    v.aprobat_la = ora
    v.aprobat_prin = "sistem" if prin_sistem else "om"
    v.aprobat_de = None if prin_sistem else utilizator_id
    db.flush()
    _urma(db, "creier.versiune_aprobata", i, v, utilizator_id, aprobat_prin=v.aprobat_prin)
    return v


def retrage(
    db: Session,
    intrare_id: uuid.UUID,
    versiune: int,
    *,
    utilizator_id: uuid.UUID | None,
    motiv: str = "",
    cauza: CauzaRetragere = CauzaRetragere.RETRAS,
    acum: dt.datetime | None = None,
) -> VersiuneCreier:
    """Scoate o versiune din uz (`ciorna` / `propus` / `aprobat` → `retras`). Rămâne citibilă. `cauza=RESPINS`
    când un om respinge o propunere; `EXPIRAT` o pune jobul de expirare (F4.6)."""
    i = intrare(db, intrare_id)
    v = citeste(db, intrare_id, versiune)
    if v.stare == Stare.RETRAS.value:
        raise TranzitieNepermisa(f"versiunea {versiune} este deja retrasă")
    if cauza is CauzaRetragere.INLOCUITA:
        raise RegulaCreier("„înlocuită” se pune doar la aprobarea unei versiuni noi")
    v.stare = Stare.RETRAS.value
    v.retras_la = _acum(acum)
    v.retras_de = utilizator_id
    v.retras_cauza = cauza.value
    v.retras_motiv = motiv[:500]
    db.flush()
    _urma(db, "creier.versiune_retrasa", i, v, utilizator_id, cauza=cauza.value)
    return v


def versiuni_de_expirat(db: Session, la: dt.datetime, *, limita: int = 500) -> Sequence[VersiuneCreier]:
    """Versiunile aprobate al căror `valabil_pana_la` a trecut (pentru jobul de expirare)."""
    return list(
        db.execute(
            select(VersiuneCreier)
            .where(
                VersiuneCreier.stare == "aprobat",
                VersiuneCreier.valabil_pana_la.is_not(None),
                VersiuneCreier.valabil_pana_la <= la,
            )
            .order_by(VersiuneCreier.valabil_pana_la)
            .limit(limita)
        ).scalars()
    )


__all__ = [
    "ContinutInvalid",
    "EroareCreier",
    "IntrareInexistenta",
    "PoartaInchisa",
    "RegulaCreier",
    "Sursa",
    "TranzitieNepermisa",
    "VersiuneInexistenta",
    "aproba",
    "citeste",
    "creeaza_intrare",
    "diferenta_versiuni",
    "gaseste_intrare",
    "intrare",
    "istoric",
    "la_data",
    "lista",
    "propune_schimbare",
    "retrage",
    "trimite_spre_aprobare",
    "versiune_aprobata",
    "versiuni_de_expirat",
]
