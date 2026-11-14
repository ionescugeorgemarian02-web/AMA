"""Planificarea publicării prin API (F9.7, D4 Planificatorul de canale, docs/15 §15.2, §15.5).

- **Alegerea canalului și a modului**: la aprobarea unei versiuni din calendar, modul efectiv al canalului
  (`canale.mod`) decide: automat → se programează aici; asistat → pachetul asistat (F6.6). Aprobarea este
  consimțământul pentru acea postare (15.2).
- **Sloturi**: pe client și canal, ore locale (Europe/Bucharest) pe zi a săptămânii (`publicare_reguli`, cu
  valori de pornire [I] pe canal). Primul slot liber după aprobare.
- **Frecvență**: cel mult `max_pe_zi` postări pe zi și canal și cel puțin `pauza_minima_min` între ele.
- **Zile blocate**: în ziua blocată nu pleacă nimic; postarea se mută pe primul slot liber.
- **La minut**: jobul `publicare.tic` (în fiecare minut) trimite ce a ajuns la oră: livrabilul `programat →
  în publicare` și efectul extern cerut în aceeași tranzacție (executorul de efecte, F2.5).
- **Pauza de criză**: oprirea publicării (globală sau pe client, `operare.opriri`) ține totul pe loc: nimic
  programat nu pleacă, iar ce era deja cerut stă în executor; după repornire, pleacă (15.5).
- **Trecerea pe asistat**: un om trece canalul pe asistat; ce era programat devine pachet asistat.
"""

import datetime as dt
import uuid
import zoneinfo
from dataclasses import dataclass
from typing import Any

from sqlalchemy import DateTime, Integer, Text, delete, func, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from app import productie, validare
from app.db import sesiune_agentie, sesiune_tenant
from app.ids import new_id
from app.logging import get_logger
from app.operare import audit, efecte, motor, opriri
from app.productie import Stare
from app.publicare import asistata, blog, canale, consimtamant, fisiere
from app.publicare.modele import BazaPublicare

log = get_logger("app.publicare.programare")
TZ = zoneinfo.ZoneInfo("Europe/Bucharest")
COMPONENTA = "D4"
NUME_TIC = "publicare.tic"
ZILE_CAUTARE = 30
# [I] sloturile de pornire pe canal (ora locală, toate zilele); învățarea (F10/F11) le înlocuiește pe client.
SLOTURI_IMPLICITE: dict[str, list[str]] = {
    "facebook": ["09:30", "18:30"],
    "instagram": ["12:00", "19:00"],
    "linkedin": ["08:30"],
    "linkedin_pagina": ["08:30"],
    "youtube": ["17:00"],
    "tiktok": ["19:30"],
    "blog": ["10:00"],
}


class RegulaCanal(BazaPublicare):
    __tablename__ = "publicare_reguli"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    canal: Mapped[str] = mapped_column(Text, primary_key=True)
    sloturi: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    max_pe_zi: Mapped[int] = mapped_column(Integer, default=1)
    pauza_minima_min: Mapped[int] = mapped_column(Integer, default=180)
    actualizat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ZiBlocata(BazaPublicare):
    __tablename__ = "publicare_zile_blocate"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    zi: Mapped[dt.date] = mapped_column(primary_key=True)
    motiv: Mapped[str] = mapped_column(Text, default="")
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PublicareProgramata(BazaPublicare):
    __tablename__ = "publicari_programate"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    livrabil_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    versiune: Mapped[int] = mapped_column(Integer)
    canal: Mapped[str] = mapped_column(Text)
    la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    stare: Mapped[str] = mapped_column(Text, default="programata")
    motiv: Mapped[str] = mapped_column(Text, default="")
    efect_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    creat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizat_la: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EroareProgramare(RuntimeError):
    pass


# --- nucleu pur ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Reguli:
    sloturi: dict[str, list[str]]  # "0".."6" (luni = 0) sau "*" → ["HH:MM", …]
    max_pe_zi: int = 1
    pauza_minima_min: int = 180

    def ore(self, zi: dt.date) -> list[dt.time]:
        brut = self.sloturi.get(str(zi.weekday()), self.sloturi.get("*", []))
        return sorted(dt.time.fromisoformat(o) for o in brut)


def alege_slot(
    r: Reguli,
    *,
    dupa: dt.datetime,
    ocupate: list[dt.datetime],
    blocate: set[dt.date],
    zile: int = ZILE_CAUTARE,
) -> dt.datetime | None:
    """Primul slot (UTC, la minut) după `dupa`, într-o zi neblocată, cu loc în plafonul zilei și la distanța
    minimă de postările deja ocupate. `None` dacă nu există în `zile` zile."""
    local = dupa.astimezone(TZ)
    pauza = dt.timedelta(minutes=r.pauza_minima_min)
    for i in range(zile + 1):
        zi = local.date() + dt.timedelta(days=i)
        if zi in blocate:
            continue
        in_zi = [o for o in ocupate if o.astimezone(TZ).date() == zi]
        if len(in_zi) >= r.max_pe_zi:
            continue
        for ora in r.ore(zi):
            cand = dt.datetime.combine(zi, ora, tzinfo=TZ).astimezone(dt.UTC)
            if cand < dupa.replace(second=0, microsecond=0):
                continue
            if all(abs(cand - o) >= pauza for o in ocupate):
                return cand
    return None


# --- citire și setări ---------------------------------------------------------------------------------------


def reguli(db: Session, tenant_id: uuid.UUID, canal: str) -> Reguli:
    rc = db.get(RegulaCanal, (tenant_id, canal))
    if rc is None or not rc.sloturi:
        return Reguli(
            {"*": SLOTURI_IMPLICITE.get(canal, ["10:00"])},
            rc.max_pe_zi if rc else 1,
            rc.pauza_minima_min if rc else 180,
        )
    return Reguli({k: list(v) for k, v in rc.sloturi.items()}, rc.max_pe_zi, rc.pauza_minima_min)


def seteaza_reguli(
    db: Session,
    tenant_id: uuid.UUID,
    canal: str,
    *,
    sloturi: dict[str, list[str]],
    max_pe_zi: int = 1,
    pauza_minima_min: int = 180,
) -> None:
    for ore in sloturi.values():
        for o in ore:
            dt.time.fromisoformat(o)  # refuză orele invalide
    db.execute(
        pg_insert(RegulaCanal)
        .values(
            tenant_id=tenant_id,
            canal=canal,
            sloturi=sloturi,
            max_pe_zi=max_pe_zi,
            pauza_minima_min=pauza_minima_min,
        )
        .on_conflict_do_update(
            index_elements=["tenant_id", "canal"],
            set_={
                "sloturi": sloturi,
                "max_pe_zi": max_pe_zi,
                "pauza_minima_min": pauza_minima_min,
                "actualizat_la": func.now(),
            },
        )
    )


def zile_blocate(db: Session, tenant_id: uuid.UUID) -> set[dt.date]:
    return set(db.execute(select(ZiBlocata.zi).where(ZiBlocata.tenant_id == tenant_id)).scalars())


def blocheaza_zi(
    db: Session, tenant_id: uuid.UUID, zi: dt.date, *, motiv: str, utilizator_id: uuid.UUID
) -> None:
    db.execute(
        pg_insert(ZiBlocata).values(tenant_id=tenant_id, zi=zi, motiv=motiv[:300]).on_conflict_do_nothing()
    )
    audit.record(
        db,
        "publicare.zi_blocata",
        obiect_tip="client",
        obiect_id=tenant_id,
        tenant_id=tenant_id,
        utilizator_id=utilizator_id,
        detalii={"zi": zi.isoformat(), "motiv": motiv[:200]},
    )


def deblocheaza_zi(db: Session, tenant_id: uuid.UUID, zi: dt.date, *, utilizator_id: uuid.UUID) -> None:
    db.execute(delete(ZiBlocata).where(ZiBlocata.tenant_id == tenant_id, ZiBlocata.zi == zi))
    audit.record(
        db,
        "publicare.zi_deblocata",
        obiect_tip="client",
        obiect_id=tenant_id,
        tenant_id=tenant_id,
        utilizator_id=utilizator_id,
        detalii={"zi": zi.isoformat()},
    )


def _ocupate(
    db: Session, tenant_id: uuid.UUID, canal: str, exceptie: uuid.UUID | None = None
) -> list[dt.datetime]:
    q = select(PublicareProgramata.la).where(
        PublicareProgramata.tenant_id == tenant_id,
        PublicareProgramata.canal == canal,
        PublicareProgramata.stare.in_(("programata", "plecata")),
    )
    if exceptie is not None:
        q = q.where(PublicareProgramata.id != exceptie)
    return list(db.execute(q).scalars())


def ale_clientului(
    db: Session, *, stari: tuple[str, ...] = ("programata",), limita: int = 100
) -> list[PublicareProgramata]:
    return list(
        db.execute(
            select(PublicareProgramata)
            .where(PublicareProgramata.stare.in_(stari))
            .order_by(PublicareProgramata.la)
            .limit(limita)
        ).scalars()
    )


def a_livrabilului(db: Session, livrabil_id: uuid.UUID) -> list[PublicareProgramata]:
    return list(
        db.execute(
            select(PublicareProgramata)
            .where(PublicareProgramata.livrabil_id == livrabil_id)
            .order_by(PublicareProgramata.creat_la)
        ).scalars()
    )


# --- pachetul pentru API
# --------------------------------------------------------------------------------------


def pachet_api(db: Session, lv: productie.Livrabil, m: canale.ModEfectiv) -> dict[str, Any]:
    """Pachetul versiunii aprobate (15.4): textul, tagurile, fișierul, eticheta AI din pașaport (G11),
    vizibilitatea (privată / ciornă cât aplicația e în test). Fără tokenuri și fără conținutul fișierului
    (doar calea)."""
    c = validare.continut.citeste(db, lv.id, lv.versiune)
    if lv.canal == blog.CANAL:
        try:
            return blog.pachet(c)
        except blog.ArticolRefuzat as exc:
            raise EroareProgramare(str(exc)) from None
    p: dict[str, Any] = {
        "text": c.text,
        "titlu": str(c.campuri.get("titlu", ""))[:200],
        "taguri": [str(h).lstrip("#") for h in c.campuri.get("hashtaguri", []) if str(h).strip("# ")],
        "eticheta_ai": False,
        "marcaj_comercial": False,
        "vizibilitate": "privat" if m.restrans else "public",
    }
    f = fisiere.al_continutului(db, c)
    if any(a.get("activ_id") for a in c.active) and f is None:
        raise EroareProgramare("fișierul livrabilului nu mai există")
    if f is not None:
        p["fisier"], p["tip_media"] = f.cale, "video" if f.video else "imagine"
        p["eticheta_ai"] = f.eticheta_ai.get(lv.canal, False)
    if c.campuri.get("link"):
        p["link"] = str(c.campuri["link"])
    if lv.canal == "tiktok":
        p["mod_tiktok"] = "ciorna" if m.restrans else "direct"
        if p["mod_tiktok"] == "direct":
            cons = consimtamant.al_versiunii(db, lv.id, lv.versiune, lv.canal)
            if cons is None:
                raise EroareProgramare(
                    "postarea directă pe TikTok așteaptă previzualizarea și consimțământul"
                )
            p["consimtamant"] = consimtamant.pentru_pachet(cons)
    return p


# --- programarea
# ---------------------------------------------------------------------------------------------


def programeaza(
    db: Session,
    livrabil_id: uuid.UUID,
    *,
    la: dt.datetime | None = None,
    acum: dt.datetime | None = None,
    utilizator_id: uuid.UUID | None = None,
) -> PublicareProgramata:
    """Versiunea aprobată primește minutul ei: `aprobat → programat`. Idempotent pe versiune."""
    acum = acum or dt.datetime.now(dt.UTC)
    lv = productie.blocheaza(db, livrabil_id)
    existenta = next((p for p in a_livrabilului(db, lv.id) if p.versiune == lv.versiune), None)
    if existenta is not None:
        return existenta
    if Stare(lv.stare) is not Stare.APROBAT:
        raise EroareProgramare(
            f"se programează doar un livrabil aprobat, nu „{productie.ETICHETE[Stare(lv.stare)]}”"
        )
    aprobare = next(
        (a for a in reversed(productie.aprobari.ale_livrabilului(db, lv.id)) if a.stare == "aprobat"), None
    )
    if aprobare is None or aprobare.versiune != lv.versiune:
        raise EroareProgramare("versiunea curentă nu este cea aprobată")
    m = canale.mod(db, lv.tenant_id, lv.canal)
    if not m.automat:
        raise EroareProgramare(f"canalul {lv.canal} e pe asistat: {m.motiv}")
    blocate = zile_blocate(db, lv.tenant_id)
    if la is None:
        la = alege_slot(
            reguli(db, lv.tenant_id, lv.canal),
            dupa=max(acum, lv.termen_la or acum),
            ocupate=_ocupate(db, lv.tenant_id, lv.canal),
            blocate=blocate,
        )
        if la is None:
            raise EroareProgramare("niciun slot liber în următoarele 30 de zile")
    elif la.astimezone(TZ).date() in blocate:
        raise EroareProgramare("ziua aleasă este blocată pentru acest client")
    p = PublicareProgramata(
        tenant_id=lv.tenant_id,
        livrabil_id=lv.id,
        versiune=lv.versiune,
        canal=lv.canal,
        la=la.replace(second=0, microsecond=0),
    )
    db.add(p)
    db.flush()
    productie.muta(
        db,
        lv.id,
        Stare.APROBAT,
        Stare.PROGRAMAT,
        componenta=COMPONENTA,
        motiv=f"programat prin API ({m.motiv})",
        utilizator_id=utilizator_id,
        versiune=lv.versiune,
        detalii={"programare": str(p.id), "la": p.la.isoformat()},
    )
    return p


def _la_asistat(db: Session, p: PublicareProgramata, motiv: str) -> None:
    asistata.pregateste(db, p.livrabil_id, din_programat=True)
    p.stare, p.motiv, p.actualizat_la = "asistata", motiv[:300], dt.datetime.now(dt.UTC)


def _muta_slotul(db: Session, p: PublicareProgramata, acum: dt.datetime, motiv: str) -> None:
    la = alege_slot(
        reguli(db, p.tenant_id, p.canal),
        dupa=acum + dt.timedelta(minutes=1),
        ocupate=_ocupate(db, p.tenant_id, p.canal, exceptie=p.id),
        blocate=zile_blocate(db, p.tenant_id),
    )
    if la is not None:
        p.la = la
    p.motiv, p.actualizat_la = motiv[:300], dt.datetime.now(dt.UTC)


def _pleaca(db: Session, p: PublicareProgramata, acum: dt.datetime) -> str:
    """O postare ajunsă la minutul ei. Întoarce ce s-a întâmplat (pentru jurnal și teste)."""
    if opriri.este_oprit(db, opriri.Oprire.PUBLICARE, tenant_id=p.tenant_id):
        p.motiv = "pauză de criză: publicarea e oprită"
        return "oprit"
    if acum.astimezone(TZ).date() in zile_blocate(db, p.tenant_id):
        _muta_slotul(db, p, acum, "zi blocată: mutată pe primul slot liber")
        return "mutat"
    lv = productie.blocheaza(db, p.livrabil_id)
    if lv.versiune != p.versiune or Stare(lv.stare) is not Stare.PROGRAMAT:
        p.stare, p.motiv = "anulata", "livrabilul nu mai e programat pe această versiune"
        return "anulat"
    m = canale.mod(db, p.tenant_id, p.canal)
    if not m.automat:
        _la_asistat(db, p, f"canalul a trecut pe asistat: {m.motiv}")
        return "asistat"
    try:
        pachet = pachet_api(db, lv, m)
    except EroareProgramare as exc:
        p.motiv = str(exc)
        return "asteapta"
    productie.muta(
        db,
        lv.id,
        Stare.PROGRAMAT,
        Stare.IN_PUBLICARE,
        componenta=COMPONENTA,
        motiv="ora programată",
        detalii={"programare": str(p.id)},
    )
    cerere = efecte.cere(db, lv.id, payload=pachet)
    p.stare, p.efect_id, p.motiv, p.actualizat_la = "plecata", cerere.efect.id, "", dt.datetime.now(dt.UTC)
    return "plecat"


def tic_acum(acum: dt.datetime | None = None) -> dict[str, int]:
    """Trimite postările ajunse la minutul lor (`la <= acum`), fiecare în tranzacția clientului ei."""
    acum = acum or dt.datetime.now(dt.UTC)
    with sesiune_agentie() as db:
        scadente = db.execute(
            select(PublicareProgramata.id, PublicareProgramata.tenant_id)
            .where(PublicareProgramata.stare == "programata", PublicareProgramata.la <= acum)
            .order_by(PublicareProgramata.la)
            .limit(200)
        ).all()
    rezultat: dict[str, int] = {}
    for pid, tenant_id in scadente:
        with sesiune_tenant(tenant_id) as db:
            p = db.get(PublicareProgramata, pid, with_for_update=True)
            if p is None or p.stare != "programata":
                continue
            r = _pleaca(db, p, acum)
        rezultat[r] = rezultat.get(r, 0) + 1
    if rezultat:
        log.info("publicare la minut", extra={"rezultat": rezultat})
    return rezultat


@motor.pas("publicare.pas_tic")
def _tic_pas() -> str:
    return str(tic_acum())


@motor.flux(NUME_TIC)
def tic(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _tic_pas()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME_TIC, "* * * * *", tic)


declara_programari()


# --- oamenii și cârligul aprobării
# ----------------------------------------------------------------------------


def treci_pe_asistat(
    db: Session, tenant_id: uuid.UUID, canal: str, *, utilizator_id: uuid.UUID, motiv: str = ""
) -> int:
    """Canalul trece pe asistat; postările programate prin API devin pachete asistate. Întoarce câte."""
    canale.alege_mod(db, tenant_id, canal, canale.Mod.ASISTAT, utilizator_id=utilizator_id, motiv=motiv)
    n = 0
    for p in db.execute(
        select(PublicareProgramata)
        .where(
            PublicareProgramata.tenant_id == tenant_id,
            PublicareProgramata.canal == canal,
            PublicareProgramata.stare == "programata",
        )
        .with_for_update()
    ).scalars():
        _la_asistat(db, p, "canal trecut pe asistat de un om")
        n += 1
    return n


def alege_drumul(
    db: Session,
    livrabil_id: uuid.UUID,
    *,
    utilizator_id: uuid.UUID | None = None,
    acum: dt.datetime | None = None,
) -> str:
    """Alegerea canalului (D4): versiunea aprobată pleacă prin API dacă modul efectiv al canalului e automat
    („api”), altfel devine pachet asistat („asistat”)."""
    lv = productie.blocheaza(db, livrabil_id)
    if canale.mod(db, lv.tenant_id, lv.canal).automat:
        programeaza(db, lv.id, utilizator_id=utilizator_id, acum=acum)
        return "api"
    asistata.pregateste(db, lv.id, utilizator_id=utilizator_id)
    return "asistat"


def dupa_decizie(
    db: Session, ap: productie.Aprobare, lv: productie.Livrabil, hotarare: productie.Hotarare
) -> None:
    """La aprobarea unui livrabil din calendar, pe un canal în mod automat, postarea se programează singură
    (pe canalele asistate, pachetul îl pregătește `asistata.dupa_decizie`)."""
    if hotarare is not productie.Hotarare.APROBAT or not canale.are_api(lv.canal):
        return
    din_calendar = asistata.din_calendar(db, lv.id) or lv.canal == blog.CANAL  # articolele F7.10 (F9.9)
    if not din_calendar or not canale.mod(db, lv.tenant_id, lv.canal).automat:
        return
    alege_drumul(db, lv.id, utilizator_id=ap.decis_de)


productie.aprobari.inregistreaza_dupa_decizie(dupa_decizie)
