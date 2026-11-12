"""Singura cale prin care se schimbă starea unui livrabil: `muta` (F2.3, 7.2–7.3).

- Blochează rândul (`FOR NO KEY UPDATE`: nu blochează istoricul, care are cheie străină spre el) și
  cere starea așteptată (`din`): două mutări simultane pe același livrabil → una reușește, cealaltă primește
  `ConflictStare`. Opțional verifică și versiunea conținutului.
- O mutare care nu e în tabel (`stari.TABEL`) sau încalcă regulile (revenirea, ieșirea doar prin om) este
  REFUZATĂ și ÎNREGISTRATĂ în `livrabile_tranzitii` (`rezultat = 'refuzata'`). Înregistrarea se face într-o
  tranzacție separată, deja încheiată când se aruncă excepția: dacă apelantul își anulează tranzacția (cazul
  obișnuit după o excepție), refuzul rămâne.
- În bază, un declanșator refuză orice UPDATE al stării care nu e în tabel sau nu trece pe aici.
- Fiecare mutare aplicată scrie istoricul (din, în, componentă, motiv, când) și un eveniment (22.1).
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, insert, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import ContextDb, sesiune
from app.db.motor import CTX_KEY
from app.ids import new_id
from app.logging import get_logger
from app.operare import evenimente
from app.productie import stari
from app.productie.modele import Livrabil, Tranzitie
from app.productie.stari import Stare

log = get_logger("app.productie")

MOTIV_MAXIM = 500
CLASA_IMPLICITA = "publicare_continut"


class EroareProductie(Exception):
    """Baza erorilor producției."""


class LivrabilInexistent(EroareProductie):
    """Nu există, sau aparține altui client (izolarea pe client îl ascunde)."""


class TranzitieRefuzata(EroareProductie):
    """Mutarea nu s-a făcut; refuzul e înregistrat. `cod`: nepermisa, conflict, versiune sau doar_om."""

    def __init__(self, cod: str, mesaj: str, *, din: Stare, la: Stare) -> None:
        super().__init__(mesaj)
        self.cod, self.din, self.la = cod, din, la


class TranzitieNepermisa(TranzitieRefuzata):
    pass


class ConflictStare(TranzitieRefuzata):
    """Starea livrabilului nu mai e cea așteptată: altcineva l-a mutat între timp."""


class VersiuneNepotrivita(TranzitieRefuzata):
    pass


@dataclass(frozen=True)
class Rezultat:
    """Ce s-a întâmplat la `muta`. `stare` e starea de acum; poate diferi de cea cerută dacă o limită a trimis
    livrabilul la om (vezi `escaladat`)."""

    livrabil: Livrabil
    cerut: Stare
    stare: Stare
    escaladat: str | None = None  # codul limitei depășite (F2.4), altfel None
    intrare_eroare_id: uuid.UUID | None = None
    detalii: dict[str, Any] = field(default_factory=dict)

    @property
    def aplicat(self) -> bool:
        return self.stare == self.cerut


@dataclass(frozen=True)
class Cerere:
    """Ce s-a cerut: același pachet de câmpuri la refuz și la aplicare."""

    din: Stare
    la: Stare
    componenta: str
    utilizator_id: uuid.UUID | None = None


def _limita(valoare: str) -> str:
    return valoare[:MOTIV_MAXIM]


# --- citire ----------------------------------------------------------


def citeste(db: Session, livrabil_id: uuid.UUID) -> Livrabil | None:
    return db.get(Livrabil, livrabil_id)


def stare_curenta(livrabil: Livrabil) -> Stare:
    return Stare(livrabil.stare)


def istoric(db: Session, livrabil_id: uuid.UUID, *, si_refuzuri: bool = True) -> list[Tranzitie]:
    q = (
        select(Tranzitie)
        .where(Tranzitie.livrabil_id == livrabil_id)
        .order_by(Tranzitie.creat_la, Tranzitie.id)
    )
    if not si_refuzuri:
        q = q.where(Tranzitie.rezultat == "aplicata")
    return list(db.execute(q).scalars())


def _blocheaza(db: Session, livrabil_id: uuid.UUID) -> Livrabil:
    rand = db.execute(
        select(Livrabil)
        .where(Livrabil.id == livrabil_id)
        .with_for_update(
            key_share=True
        )  # FOR NO KEY UPDATE: istoricul (cheie străină) se poate scrie în paralel
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if rand is None:
        raise LivrabilInexistent(str(livrabil_id))
    return rand


# --- creare ----------------------------------------------------------


def creeaza(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    tip: str,
    canal: str,
    termen_la: Any = None,
    clasa: str | None = None,
    componenta: str = "D3",
    utilizator_id: uuid.UUID | None = None,
) -> Livrabil:
    """Un livrabil nou, în starea `planificat`, cu bugetul implicit din configurare."""
    s = get_settings()
    livrabil = Livrabil(
        id=new_id(),
        tenant_id=tenant_id,
        tip=tip,
        canal=canal,
        clasa_actiune=clasa or CLASA_IMPLICITA,
        termen_la=termen_la,
        stare=Stare.PLANIFICAT.value,
        versiune=1,
        buget_apeluri_llm=s.productie_buget_apeluri_llm,
        buget_timp_sec=s.productie_buget_timp_sec,
    )
    db.add(livrabil)
    db.flush()
    _scrie_istoric(
        db,
        livrabil,
        din=None,
        la=Stare.PLANIFICAT,
        rezultat="aplicata",
        componenta=componenta,
        utilizator_id=utilizator_id,
        motiv="livrabil planificat",
    )
    evenimente.emite(
        db,
        "livrabil.creat",
        sursa="productie",
        obiect_tip="livrabil",
        obiect_id=livrabil.id,
        tenant_id=tenant_id,
        date={"tip": tip, "canal": canal, "clasa": livrabil.clasa_actiune},
    )
    return livrabil


# --- istoric ---------------------------------------------------------


def _valori_istoric(
    livrabil: Livrabil,
    *,
    din: Stare | None,
    la: Stare,
    rezultat: str,
    componenta: str,
    utilizator_id: uuid.UUID | None,
    motiv: str,
    detalii: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": new_id(),
        "tenant_id": livrabil.tenant_id,
        "livrabil_id": livrabil.id,
        "rezultat": rezultat,
        "din": din.value if din else None,
        "in_stare": la.value,
        "componenta": componenta[:60],
        "actor_tip": "utilizator" if utilizator_id else "componenta",
        "utilizator_id": utilizator_id,
        "motiv": _limita(motiv),
        "detalii": detalii or {},
        "versiune": livrabil.versiune,
    }


def _scrie_istoric(db: Session, livrabil: Livrabil, **kw: Any) -> None:
    db.execute(insert(Tranzitie).values(**_valori_istoric(livrabil, **kw)))


def _inregistreaza_refuz(db: Session, livrabil: Livrabil, cod: str, motiv: str, cerere: Cerere) -> None:
    """Scrie refuzul într-o tranzacție SEPARATĂ, încheiată (commit) înainte să se arunce excepția: refuzul
    supraviețuiește rollback-ului tranzacției apelantului. Nu poate strica excepția originală."""
    ctx = db.info.get(CTX_KEY)
    utilizator = cerere.utilizator_id or (ctx.user_id if ctx else None)
    try:
        with sesiune(ContextDb(tenant_id=livrabil.tenant_id, user_id=utilizator)) as s2:
            _scrie_istoric(
                s2,
                livrabil,
                din=cerere.din,
                la=cerere.la,
                rezultat="refuzata",
                componenta=cerere.componenta,
                utilizator_id=cerere.utilizator_id,
                motiv=motiv,
                detalii={"cod": cod},
            )
            evenimente.emite(
                s2,
                "livrabil.tranzitie_refuzata",
                sursa="productie",
                obiect_tip="livrabil",
                obiect_id=livrabil.id,
                tenant_id=livrabil.tenant_id,
                utilizator_id=cerere.utilizator_id,
                date={
                    "felul": cod,
                    "din": cerere.din.value,
                    "la": cerere.la.value,
                    "componenta": cerere.componenta,
                },
            )
    except Exception as exc:
        log.error("refuzul nu a putut fi înregistrat", extra={"tip_eroare": type(exc).__name__})


def refuza(
    db: Session,
    livrabil: Livrabil,
    exceptie: type[TranzitieRefuzata],
    cod: str,
    mesaj: str,
    cerere: Cerere,
) -> TranzitieRefuzata:
    """Înregistrează refuzul (tranzacție separată) și întoarce excepția de aruncat."""
    _inregistreaza_refuz(db, livrabil, cod, mesaj, cerere)
    return exceptie(cod, mesaj, din=cerere.din, la=cerere.la)


# --- mutarea ---------------------------------------------------------


def muta(
    db: Session,
    livrabil_id: uuid.UUID,
    din: Stare,
    la: Stare,
    *,
    componenta: str,
    motiv: str = "",
    utilizator_id: uuid.UUID | None = None,
    versiune: int | None = None,
    detalii: dict[str, Any] | None = None,
) -> Rezultat:
    """Mută livrabilul din `din` în `la`. `din` este starea pe care apelantul o crede curentă (verificare
    optimistă, sub blocare). `componenta`: cine mută (D5, G1, ...). `utilizator_id`: dacă a decis un om.

    Aruncă `LivrabilInexistent`, `ConflictStare`, `VersiuneNepotrivita` sau `TranzitieNepermisa`; ultimele
    trei sunt înregistrate în istoric înainte de a fi aruncate."""
    livrabil = _blocheaza(db, livrabil_id)
    cerere = Cerere(din, la, componenta, utilizator_id)
    curenta = Stare(livrabil.stare)
    if curenta != din:
        raise refuza(
            db,
            livrabil,
            ConflictStare,
            "conflict",
            f"starea este „{stari.ETICHETE[curenta]}”, nu „{stari.ETICHETE[din]}” (mutat de altcineva)",
            cerere,
        )
    if versiune is not None and livrabil.versiune != versiune:
        raise refuza(
            db,
            livrabil,
            VersiuneNepotrivita,
            "versiune",
            f"versiunea este {livrabil.versiune}, nu {versiune}",
            cerere,
        )
    anterioara = Stare(livrabil.stare_anterioara) if livrabil.stare_anterioara else None
    motiv_refuz = stari.motiv_refuz(curenta, la, anterioara)
    if motiv_refuz:
        raise refuza(db, livrabil, TranzitieNepermisa, "nepermisa", motiv_refuz, cerere)
    if curenta in stari.DOAR_OM and utilizator_id is None and la != Stare.COADA_DE_ERORI:
        raise refuza(
            db,
            livrabil,
            TranzitieNepermisa,
            "doar_om",
            f"din „{stari.ETICHETE[curenta]}” iese doar un om",
            cerere,
        )
    _aplica(db, livrabil, cerere, motiv=motiv, detalii=detalii)
    return Rezultat(livrabil=livrabil, cerut=la, stare=la)


def _aplica(
    db: Session, livrabil: Livrabil, cerere: Cerere, *, motiv: str, detalii: dict[str, Any] | None
) -> None:
    """Scrie mutarea (stare, istoric, eveniment). Presupune rândul blocat și verificările făcute."""
    din, la = cerere.din, cerere.la
    # Declanșatorul din bază acceptă schimbarea stării doar cu acest marcaj (local tranzacției). Se pune
    # ÎNAINTE de modificări: o interogare face autoflush, iar UPDATE-ul trebuie să găsească marcajul.
    db.execute(text("SELECT set_config('app.muta_livrabil', :i, true)"), {"i": str(livrabil.id)})
    try:
        if la in (Stare.ESEC_TEMPORAR, Stare.COADA_DE_ERORI, Stare.CARANTINA):
            pastreaza = din in (Stare.ESEC_TEMPORAR, Stare.CARANTINA) and la == Stare.COADA_DE_ERORI
            livrabil.stare_anterioara = livrabil.stare_anterioara if pastreaza else din.value
        elif din in (Stare.ESEC_TEMPORAR, Stare.COADA_DE_ERORI, Stare.CARANTINA):
            livrabil.stare_anterioara = None
        livrabil.stare = la.value
        livrabil.actualizat_la = func.now()
        db.flush()
    finally:
        db.execute(text("SELECT set_config('app.muta_livrabil', '', true)"))
    _scrie_istoric(
        db,
        livrabil,
        din=din,
        la=la,
        rezultat="aplicata",
        componenta=cerere.componenta,
        utilizator_id=cerere.utilizator_id,
        motiv=motiv,
        detalii=detalii,
    )
    evenimente.emite(
        db,
        "livrabil.tranzitie",
        sursa="productie",
        obiect_tip="livrabil",
        obiect_id=livrabil.id,
        tenant_id=livrabil.tenant_id,
        utilizator_id=cerere.utilizator_id,
        date={
            "din": din.value,
            "la": la.value,
            "componenta": cerere.componenta,
            "versiune": livrabil.versiune,
        },
    )


# --- versiunea conținutului ------------------------------------------

STARI_CU_CONTINUT_MUTABIL = frozenset(
    {Stare.IN_SCRIERE, Stare.IN_REPARATIE, Stare.VALIDAT, Stare.ASTEAPTA_APROBARE}
)


def versiune_noua(
    db: Session,
    livrabil_id: uuid.UUID,
    *,
    componenta: str,
    motiv: str = "",
    utilizator_id: uuid.UUID | None = None,
) -> int:
    """Conținutul s-a schimbat: versiunea crește. Orice decizie legată de versiunea veche (o aprobare) nu mai
    este valabilă pentru cea nouă. Conținutul vine în F4–F6; aici doar legătura de versiune."""
    livrabil = _blocheaza(db, livrabil_id)
    curenta = Stare(livrabil.stare)
    if curenta not in STARI_CU_CONTINUT_MUTABIL:
        raise TranzitieNepermisa(
            "nepermisa",
            f"în starea „{stari.ETICHETE[curenta]}” conținutul nu se mai schimbă",
            din=curenta,
            la=curenta,
        )
    livrabil.versiune += 1
    livrabil.actualizat_la = func.now()
    db.flush()
    evenimente.emite(
        db,
        "livrabil.versiune_noua",
        sursa="productie",
        obiect_tip="livrabil",
        obiect_id=livrabil.id,
        tenant_id=livrabil.tenant_id,
        utilizator_id=utilizator_id,
        date={"versiune": livrabil.versiune, "componenta": componenta, "motiv": motiv[:200]},
    )
    return livrabil.versiune
