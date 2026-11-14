"""Colectorul de metrici (F10.1, K1, docs/07 §7.2, docs/05 §5.12).

Citește rezultatele fiecărei postări publicate la 1 oră, 24 de ore, 72 de ore, 7 zile și 28 de zile de la
publicare și le ține în `metrici_postari`, un rând pe interval.

Reguli (D-009):
- **Ce se citește.** Postările plecate prin API (efecte `trimis`, cu identificatorul platformei), pe
  canalele care au cititor de metrici. Canalele asistate și blogul nu au cititor: cifrele lor se introduc de
  om (`inregistreaza_manual`, din exportul platformei) sau vin din analiza de trafic proprie (F10.6).
- **Când.** Jobul `analiza.colector` rulează la 10 minute. Un interval se citește din momentul lui până la
  momentul intervalului următor (ultimul: încă `GRATIE_FINALA`). Întârzierea se ține pe rând.
- **Fără cifre inventate.** Dacă un interval a trecut fără citire (colectorul oprit, platforma căzută),
  rândul lui devine `ratat`: o citire făcută mai târziu nu se trece drept cifra acelui interval. Dacă
  platforma refuză (postare ștearsă, ciornă nepublicată), rândul devine `indisponibil`. Verificarea de
  completitudine (`completitudine`) numără ce lipsește.
- **Erori.** Temporară: se reîncearcă la rularea următoare, cât intervalul e deschis. Autentificare: nu se
  insistă (gardianul sănătății, F9.8, cere reautorizarea); un canal pe pauză nu se citește.
- **Starea livrabilului.** La prima citire reușită, livrabilul trece din „publicat” în „în măsurare” (7.2).
  Trecerea în „închis” o face învățarea (F11), nu colectorul.
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app import productie
from app.analiza import retentie
from app.analiza.modele import MetriciPostare
from app.connectors.contract import CHEI_METRICI
from app.db import sesiune_agentie, sesiune_tenant
from app.ids import new_id
from app.logging import get_logger
from app.operare import audit, efecte, motor
from app.operare.efecte import metrici as usa_metrici
from app.operare.efecte import servicii as servicii_efecte

log = get_logger("app.analiza.colector")
NUME = "analiza.colector"
COMPONENTA = "K1"

# Intervalele din 7.2, în ordine: (cod, momentul de la publicare).
INTERVALE: tuple[tuple[str, dt.timedelta], ...] = (
    ("1h", dt.timedelta(hours=1)),
    ("24h", dt.timedelta(hours=24)),
    ("72h", dt.timedelta(hours=72)),
    ("7z", dt.timedelta(days=7)),
    ("28z", dt.timedelta(days=28)),
)
ETICHETE_INTERVAL: dict[str, str] = {
    "1h": "1 oră",
    "24h": "24 de ore",
    "72h": "72 de ore",
    "7z": "7 zile",
    "28z": "28 de zile",
}
GRATIE_FINALA = dt.timedelta(days=7)  # cât mai e valabilă citirea de la 28 de zile [I]
FEREASTRA = INTERVALE[-1][1] + GRATIE_FINALA + dt.timedelta(days=1)
LOT = 500  # postări pe rulare


class MetriciRefuzate(ValueError):
    """Cifrele introduse de om nu sunt valide sau rândul nu poate fi înlocuit."""


@dataclass(frozen=True)
class Plan:
    """Ce are de făcut colectorul pentru o postare, acum."""

    de_citit: str | None  # intervalul deschis, necitit încă
    ratate: tuple[str, ...]  # intervalele care au trecut fără citire
    intarziere: dt.timedelta = dt.timedelta(0)


def planifica(publicat_la: dt.datetime, existente: set[str], acum: dt.datetime) -> Plan:
    """Nucleu pur. Intervalul `i` e deschis între momentul lui și momentul intervalului următor (ultimul:
    încă `GRATIE_FINALA`). Cele închise și fără rând sunt ratate."""
    de_citit, intarziere, ratate = None, dt.timedelta(0), []
    for n, (cod, moment) in enumerate(INTERVALE):
        scadent = publicat_la + moment
        if acum < scadent:
            break
        if cod in existente:
            continue
        inchidere = publicat_la + (INTERVALE[n + 1][1] if n + 1 < len(INTERVALE) else moment + GRATIE_FINALA)
        if acum < inchidere:
            de_citit, intarziere = cod, acum - scadent
        else:
            ratate.append(cod)
    return Plan(de_citit, tuple(ratate), intarziere)


def curata(valori: dict[str, Any]) -> dict[str, int]:
    """Cifrele acceptate: doar cheile cunoscute, întregi ≥ 0. Orice altceva e refuzat (nu „reparat”)."""
    out: dict[str, int] = {}
    for k, v in valori.items():
        if k not in CHEI_METRICI:
            raise MetriciRefuzate(f"metrică necunoscută: {k}")
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise MetriciRefuzate(f"valoare nevalidă pentru {k}: trebuie un număr întreg, cel puțin 0")
        out[k] = v
    return out


def _scrie(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    livrabil_id: uuid.UUID,
    canal: str,
    id_extern: str,
    interval: str,
    stare: str,
    publicat_la: dt.datetime,
    acum: dt.datetime,
    valori: dict[str, int] | None = None,
    motiv: str = "",
    intarziere: dt.timedelta = dt.timedelta(0),
) -> bool:
    """Rândul unui interval, o singură dată (o rulare concurentă nu îl dublează și nu îl suprascrie)."""
    r = db.execute(
        pg_insert(MetriciPostare)
        .values(
            id=new_id(),
            tenant_id=tenant_id,
            livrabil_id=livrabil_id,
            canal=canal,
            id_extern=id_extern[:300],
            interval=interval,
            stare=stare,
            sursa="api",
            valori=valori or {},
            motiv=motiv[:300],
            publicat_la=publicat_la,
            citit_la=acum,
            intarziere_s=max(0, int(intarziere.total_seconds())),
        )
        .on_conflict_do_nothing(constraint="metrici_postari_unic")
        .returning(MetriciPostare.id)
    )
    return r.first() is not None


def _in_masurare(db: Session, livrabil_id: uuid.UUID) -> None:
    lv = productie.citeste(db, livrabil_id)
    if lv is None or lv.stare != productie.Stare.PUBLICAT.value:
        return
    try:
        productie.muta(
            db,
            livrabil_id,
            productie.Stare.PUBLICAT,
            productie.Stare.IN_MASURARE,
            componenta=COMPONENTA,
            motiv="prima citire de metrici",
        )
    except productie.TranzitieRefuzata as exc:  # altcineva l-a mutat între timp: cifrele rămân valabile
        log.info("livrabil nemutat în măsurare", extra={"tip_eroare": type(exc).__name__})


def citeste_postarea(
    tenant_id: uuid.UUID,
    livrabil_id: uuid.UUID,
    canal: str,
    id_extern: str,
    publicat_la: dt.datetime,
    acum: dt.datetime,
) -> str:
    """Citirea unei postări, acum. Întoarce ce s-a întâmplat: `citit:<interval>`, `indisponibil:<interval>`,
    `amanat` (eroare temporară sau de autentificare, canal pe pauză), `nimic` (niciun interval deschis)."""
    with sesiune_tenant(tenant_id) as db:
        existente = set(
            db.execute(
                select(MetriciPostare.interval).where(
                    MetriciPostare.livrabil_id == livrabil_id, MetriciPostare.canal == canal
                )
            ).scalars()
        )
        plan = planifica(publicat_la, existente, acum)
        comune: dict[str, Any] = {
            "tenant_id": tenant_id,
            "livrabil_id": livrabil_id,
            "canal": canal,
            "id_extern": id_extern,
            "publicat_la": publicat_la,
            "acum": acum,
        }
        for cod in plan.ratate:
            _scrie(db, interval=cod, stare="ratat", motiv="intervalul a trecut fără citire", **comune)
        if plan.de_citit is None:
            return "nimic"
        if servicii_efecte.pauza(db, tenant_id, canal) is not None:
            return "amanat"
    # Apelul la platformă se face în afara tranzacției: nu ținem o conexiune deschisă cât așteptăm rețeaua.
    try:
        cifre = usa_metrici.citeste(tenant_id, canal, id_extern)
    except (motor.EroareTemporara, motor.EroareAutentificare) as exc:
        # `EroareAutentificare` e o `EroareDefinitiva`: se prinde întâi, altfel un token expirat ar marca
        # intervalul „indisponibil” în loc să aștepte reautorizarea.
        log.info("metrici amânate", extra={"canal": canal, "tip_eroare": type(exc).__name__})
        return "amanat"
    except motor.EroareDefinitiva as exc:
        with sesiune_tenant(tenant_id) as db:
            _scrie(
                db, interval=plan.de_citit, stare="indisponibil", motiv=str(exc), intarziere=plan.intarziere,
                **comune,
            )  # fmt: skip
        return f"indisponibil:{plan.de_citit}"
    with sesiune_tenant(tenant_id) as db:
        nou = _scrie(
            db, interval=plan.de_citit, stare="citit", valori=curata(cifre.ca_dict()),
            intarziere=plan.intarziere, **comune,
        )  # fmt: skip
        if nou:
            _in_masurare(db, livrabil_id)
    if nou:  # curba de retenție (F10.2), unde platforma o dă; nu poate strica citirea de mai sus
        retentie.actualizeaza(tenant_id, livrabil_id, canal, id_extern, publicat_la, plan.de_citit, acum)
    return f"citit:{plan.de_citit}"


def _postari(acum: dt.datetime) -> list[tuple[uuid.UUID, uuid.UUID, str, str, dt.datetime]]:
    """Postările plecate prin API care mai pot avea un interval deschis: cea mai nouă publicare pe
    (livrabil, canal), fără rândul ultimului interval."""
    E = efecte.Efect
    ultim = INTERVALE[-1][0]
    are_ultimul = (
        select(MetriciPostare.id)
        .where(
            MetriciPostare.livrabil_id == E.livrabil_id,
            MetriciPostare.canal == E.canal,
            MetriciPostare.interval == ultim,
        )
        .exists()
    )
    with sesiune_agentie() as db:
        randuri = db.execute(
            select(E.tenant_id, E.livrabil_id, E.canal, E.id_extern, E.trimis_la)
            .where(
                E.stare == "trimis",
                E.id_extern.is_not(None),
                E.trimis_la.is_not(None),
                E.trimis_la <= acum - INTERVALE[0][1],
                E.trimis_la > acum - FEREASTRA,
                ~are_ultimul,
            )
            .distinct(E.livrabil_id, E.canal)
            .order_by(E.livrabil_id, E.canal, E.trimis_la.desc())
            .limit(LOT)
        ).all()
    return [(t, lv, c, str(i), la) for t, lv, c, i, la in randuri if la is not None]


def colecteaza(acum: dt.datetime | None = None) -> dict[str, int]:
    """O rulare a colectorului peste toți clienții. Întoarce numărătoarea pe rezultat."""
    acum = acum or dt.datetime.now(dt.UTC)
    numar: dict[str, int] = {}
    for tenant_id, livrabil_id, canal, id_extern, publicat_la in _postari(acum):
        if not usa_metrici.are_cititor(canal):
            continue
        try:
            rez = citeste_postarea(tenant_id, livrabil_id, canal, id_extern, publicat_la, acum)
        except Exception as exc:  # o postare cu probleme nu oprește restul
            log.warning("postare necitită", extra={"canal": canal, "tip_eroare": type(exc).__name__})
            rez = "eroare"
        cheie = rez.split(":")[0]
        numar[cheie] = numar.get(cheie, 0) + 1
    return numar


def inregistreaza_manual(
    db: Session,
    livrabil_id: uuid.UUID,
    canal: str,
    interval: str,
    valori: dict[str, Any],
    *,
    utilizator_id: uuid.UUID,
    publicat_la: dt.datetime | None = None,
    acum: dt.datetime | None = None,
) -> MetriciPostare:
    """Cifre introduse de om, din exportul sau aplicația platformei (canalele asistate; 23.21). Nu
    înlocuiește o citire făcută prin API; înlocuiește un rând `ratat`, `indisponibil` sau unul manual."""
    if interval not in ETICHETE_INTERVAL:
        raise MetriciRefuzate(f"interval necunoscut: {interval}")
    cifre = curata(valori)
    if not cifre:
        raise MetriciRefuzate("nicio cifră de înregistrat")
    lv = productie.citeste(db, livrabil_id)
    if lv is None:
        raise MetriciRefuzate("livrabilul nu există")
    acum = acum or dt.datetime.now(dt.UTC)
    moment = publicat_la or _publicat_la(db, livrabil_id, canal)
    if moment is None:
        raise MetriciRefuzate("livrabilul nu a fost publicat pe acest canal")
    rand = db.execute(
        select(MetriciPostare)
        .where(
            MetriciPostare.livrabil_id == livrabil_id,
            MetriciPostare.canal == canal,
            MetriciPostare.interval == interval,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if rand is not None and rand.stare == "citit" and rand.sursa == "api":
        raise MetriciRefuzate("intervalul are deja cifre citite de la platformă")
    if rand is None:
        rand = MetriciPostare(
            tenant_id=lv.tenant_id,
            livrabil_id=livrabil_id,
            canal=canal,
            interval=interval,
            publicat_la=moment,
        )
        db.add(rand)
    rand.stare, rand.sursa, rand.valori, rand.motiv = "citit", "manual", cifre, ""
    rand.introdus_de, rand.citit_la = utilizator_id, acum
    scadent = moment + dict(INTERVALE)[interval]
    rand.intarziere_s = max(0, int((acum - scadent).total_seconds()))
    db.flush()
    audit.record(
        db,
        "metrici.introduse_manual",
        obiect_tip="livrabil",
        obiect_id=livrabil_id,
        tenant_id=lv.tenant_id,
        utilizator_id=utilizator_id,
        detalii={"canal": canal, "interval": interval, "chei": sorted(cifre)},
    )
    _in_masurare(db, livrabil_id)
    return rand


def _publicat_la(db: Session, livrabil_id: uuid.UUID, canal: str) -> dt.datetime | None:
    """Momentul publicării pe canal: efectul trimis prin API sau confirmarea publicării asistate."""
    from app.publicare.modele import PublicareAsistata

    E = efecte.Efect
    api: dt.datetime | None = db.execute(
        select(func.max(E.trimis_la)).where(
            E.livrabil_id == livrabil_id, E.canal == canal, E.stare == "trimis"
        )
    ).scalar_one_or_none()
    if api is not None:
        return api
    return db.execute(
        select(func.max(PublicareAsistata.publicat_la)).where(
            PublicareAsistata.livrabil_id == livrabil_id, PublicareAsistata.canal == canal
        )
    ).scalar_one_or_none()


def ale_livrabilului(db: Session, livrabil_id: uuid.UUID) -> list[MetriciPostare]:
    """Citirile unui livrabil, pe canal și în ordinea intervalelor."""
    ordine = {cod: n for n, (cod, _) in enumerate(INTERVALE)}
    randuri = db.execute(select(MetriciPostare).where(MetriciPostare.livrabil_id == livrabil_id)).scalars()
    return sorted(randuri, key=lambda r: (r.canal, ordine[r.interval]))


def ultimele(db: Session, livrabil_id: uuid.UUID, canal: str) -> dict[str, int]:
    """Cele mai recente cifre citite ale postării (valori cumulate), sau `{}`."""
    citite = [r for r in ale_livrabilului(db, livrabil_id) if r.canal == canal and r.stare == "citit"]
    return dict(citite[-1].valori) if citite else {}


def recente(db: Session, limita: int = 50) -> list[MetriciPostare]:
    """Cea mai recentă citire reușită a fiecărei postări (livrabil + canal), cele mai noi primele."""
    randuri = db.execute(
        select(MetriciPostare)
        .where(MetriciPostare.stare == "citit")
        .order_by(MetriciPostare.citit_la.desc())
        .limit(limita * len(INTERVALE))
    ).scalars()
    vazute: set[tuple[uuid.UUID, str]] = set()
    out: list[MetriciPostare] = []
    for r in randuri:
        if (r.livrabil_id, r.canal) not in vazute:
            vazute.add((r.livrabil_id, r.canal))
            out.append(r)
    return out[:limita]


def completitudine(db: Session, tenant_id: uuid.UUID, *, de_la: dt.datetime | None = None) -> dict[str, int]:
    """Verificarea de completitudine a colectorului (5.12): câte intervale au cifre, câte au fost ratate și
    câte nu au fost disponibile, pentru postările clientului."""
    q = select(MetriciPostare.stare, func.count()).where(MetriciPostare.tenant_id == tenant_id)
    if de_la is not None:
        q = q.where(MetriciPostare.publicat_la >= de_la)
    numar = {"citit": 0, "ratat": 0, "indisponibil": 0}
    for stare, n in db.execute(q.group_by(MetriciPostare.stare)).all():
        numar[str(stare)] = int(n)
    return numar


@motor.pas("analiza.pas_colector")
def _pas() -> str:
    return str(colecteaza())


@motor.flux(NUME)
def flux(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _pas()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME, "3-59/10 * * * *", flux)


declara_programari()
