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
- Limitele anti-buclă (F2.4, 7.3) trăiesc tot aici, ca să nu existe ocolire: intrarea într-o a treia rundă de
  reparație sau într-a 13-a predare nu se face; livrabilul trece în `coada_de_erori`, cu diagnostic și o
  intrare în coada de erori (`escaleaza`). Pornirea producției noi (`planificat → briefat`) respectă
  oprirea globală a producției (întrerupătorul) și oprirea pe client.
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
from app.operare import audit, coada_erori, evenimente, opriri
from app.operare.notificari import Nivel
from app.operare.opriri import Oprire
from app.productie import limite, stari
from app.productie.anunturi import anunta
from app.productie.limite import Depasire
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


class LimitaDepasita(TranzitieRefuzata):
    """O limită anti-buclă s-a depășit, iar livrabilul nu poate fi trimis la om din starea în care e."""


class ProductieOprita(EroareProductie):
    """Producția nouă este oprită (global sau pe client): livrabilul rămâne `planificat`, nu se pierde nimic.
    Nu se scrie în istoric (nu e o tranziție greșită, ci o pauză); reîncearcă după repornire."""


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


def blocheaza(db: Session, livrabil_id: uuid.UUID) -> Livrabil:
    """Rândul livrabilului, blocat pentru restul tranzacției (cu valorile proaspete din bază)."""
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
    livrabil = blocheaza(db, livrabil_id)
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
    if curenta == Stare.PLANIFICAT and la == Stare.BRIEFAT:
        _respecta_opririle(db, livrabil)
    depasire = limite.depasire_la_intrare(
        la, livrabil.runde_reparatie, livrabil.predari, _limite_configurate()
    )
    if depasire is not None:
        if not stari.este_permisa(curenta, Stare.COADA_DE_ERORI):
            raise refuza(
                db,
                livrabil,
                LimitaDepasita,
                "limita",
                f"{limite.ETICHETE[depasire]} e depășită; din „{stari.ETICHETE[curenta]}” nu se escaladează",
                cerere,
            )
        return escaleaza(
            db,
            livrabil,
            depasire,
            cerut=la,
            componenta=componenta,
            utilizator_id=utilizator_id,
            diagnostic=detalii,
        )
    _aplica(db, livrabil, cerere, motiv=motiv, detalii=detalii)
    return Rezultat(livrabil=livrabil, cerut=la, stare=la)


def _limite_configurate() -> limite.Limite:
    s = get_settings()
    return limite.Limite(runde_reparatie=s.productie_runde_reparatie, predari=s.productie_predari_max)


def _respecta_opririle(db: Session, livrabil: Livrabil) -> None:
    """Pornirea de lucru nou respectă oprirea globală a producției (întrerupătorul) și oprirea pe client."""
    if opriri.este_oprit(db, Oprire.PRODUCTIE, tenant_id=livrabil.tenant_id):
        raise ProductieOprita("producția nouă este oprită (global sau pentru acest client)")


def _aplica(
    db: Session,
    livrabil: Livrabil,
    cerere: Cerere,
    *,
    motiv: str,
    detalii: dict[str, Any] | None,
    escaladare: bool = False,
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
        if la == Stare.IN_REPARATIE:
            livrabil.runde_reparatie += 1
        if la in stari.STARI_DE_LUCRU:
            livrabil.predari += 1
        if escaladare:
            livrabil.escaladari += 1
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


# --- escaladarea la om (F2.4) -----------------------------------------------------------------


def _text_scurt(valoare: object) -> str:
    return str(valoare)[:200]


def _diagnostic(
    db: Session,
    livrabil: Livrabil,
    depasire: Depasire,
    *,
    din: Stare,
    cerut: Stare,
    suplimentar: dict[str, Any] | None,
) -> dict[str, Any]:
    """Ce are nevoie un om ca să decidă: ce limită, unde era livrabilul, contoarele, ultimele mutări și ce a
    adăugat componenta (verdictul validatorului, de exemplu). Fără conținut și fără date personale."""
    limite_cfg = _limite_configurate()
    ultimele = istoric(db, livrabil.id)[-10:]
    return {
        "tip_sursa": "livrabil",
        "livrabil_id": str(livrabil.id),
        "tip": livrabil.tip,
        "canal": livrabil.canal,
        "clasa_actiune": livrabil.clasa_actiune,
        "versiune": livrabil.versiune,
        "limita_depasita": depasire.value,
        "limita": limite.ETICHETE[depasire],
        "stare_la_oprire": din.value,
        "mutare_ceruta": cerut.value,
        "contoare": {
            "runde_reparatie": livrabil.runde_reparatie,
            "predari": livrabil.predari,
            "apeluri_llm": livrabil.apeluri_llm,
            "timp_sec": round(livrabil.timp_sec, 1),
            "escaladari_anterioare": livrabil.escaladari,
        },
        "limite": {
            "runde_reparatie": limite_cfg.runde_reparatie,
            "predari": limite_cfg.predari,
            "buget_apeluri_llm": livrabil.buget_apeluri_llm,
            "buget_timp_sec": livrabil.buget_timp_sec,
        },
        "ultimele_tranzitii": [
            {
                "din": t.din,
                "in": t.in_stare,
                "rezultat": t.rezultat,
                "componenta": t.componenta,
                "motiv": _text_scurt(t.motiv),
                "la": t.creat_la.isoformat() if t.creat_la else None,
            }
            for t in ultimele
        ],
        "de_la_componenta": {
            _text_scurt(k): _text_scurt(v) for k, v in list((suplimentar or {}).items())[:20]
        },
    }


def escaleaza(
    db: Session,
    livrabil: Livrabil,
    depasire: Depasire,
    *,
    cerut: Stare,
    componenta: str,
    utilizator_id: uuid.UUID | None = None,
    diagnostic: dict[str, Any] | None = None,
) -> Rezultat:
    """Trimite livrabilul la om: `coada_de_erori` + o intrare în coada de erori existentă, cu diagnostic +
    un anunț (după commit). Presupune rândul blocat și mutarea în `coada_de_erori` permisă."""
    din = Stare(livrabil.stare)
    motiv = f"limită depășită: {limite.ETICHETE[depasire]}"
    context = _diagnostic(db, livrabil, depasire, din=din, cerut=cerut, suplimentar=diagnostic)
    cerere = Cerere(din, Stare.COADA_DE_ERORI, componenta, utilizator_id)
    _aplica(
        db,
        livrabil,
        cerere,
        motiv=motiv,
        detalii={"cerut": cerut.value, "limita": depasire.value},
        escaladare=True,
    )
    intrare = coada_erori.inregistreaza_escaladare(
        db,
        tenant_id=livrabil.tenant_id,
        cheie=cheie_escaladare(livrabil.id, livrabil.escaladari),
        flux="livrabil",
        pas=din.value,
        eroare_tip=f"Limita:{depasire.value}",
        mesaj=f"{motiv}; livrabilul ({livrabil.tip}, {livrabil.canal}) oprit în „{stari.ETICHETE[din]}”",
        context=context,
    )
    anunta(
        db,
        Nivel.IMPORTANT,
        "Un livrabil cere intervenție",
        f"Un livrabil ({livrabil.tip}, {livrabil.canal}) s-a oprit la {limite.ETICHETE[depasire]}.",
        url=f"/alerte/{intrare.id}",
    )
    return Rezultat(
        livrabil=livrabil,
        cerut=cerut,
        stare=Stare.COADA_DE_ERORI,
        escaladat=depasire.value,
        intrare_eroare_id=intrare.id,
    )


def cheie_escaladare(livrabil_id: uuid.UUID, numar: int) -> str:
    """Cheia intrării din coada de erori pentru a `numar`-a escaladare a livrabilului."""
    return f"livrabil:{livrabil_id}:{numar}"


def reia_de_om(
    db: Session,
    livrabil_id: uuid.UUID,
    *,
    utilizator_id: uuid.UUID,
    motiv: str,
    componenta: str = "om",
) -> Rezultat:
    """Un om reia un livrabil din `coada_de_erori` în starea de dinainte. Primește rânduri noi: rundele de
    reparație și predările se resetează, iar bugetul crește cu încă unul implicit (altfel s-ar opri imediat la
    aceeași limită). Intrarea din coada de erori se închide; decizia intră în istoric și în audit."""
    motiv = motiv.strip()
    if len(motiv) < 3:
        raise ValueError("reluarea de către om cere un motiv (cel puțin 3 caractere)")
    livrabil = blocheaza(db, livrabil_id)
    curenta = Stare(livrabil.stare)
    tinta = Stare(livrabil.stare_anterioara) if livrabil.stare_anterioara else None
    cerere = Cerere(curenta, tinta or Stare.BRIEFAT, componenta, utilizator_id)
    if curenta != Stare.COADA_DE_ERORI or tinta is None:
        raise refuza(
            db,
            livrabil,
            TranzitieNepermisa,
            "nepermisa",
            f"se reia doar din coada de erori; livrabilul e în „{stari.ETICHETE[curenta]}”",
            cerere,
        )
    cfg = get_settings()
    # Contoarele se resetează în aceeași mutare (declanșatorul permite UPDATE-ul pe marcajul din `_aplica`).
    livrabil.runde_reparatie = 0
    livrabil.predari = 0
    livrabil.buget_apeluri_llm += cfg.productie_buget_apeluri_llm
    livrabil.buget_timp_sec += cfg.productie_buget_timp_sec
    _aplica(db, livrabil, cerere, motiv=motiv, detalii={"reluat_de_om": True})
    intrare = coada_erori.dupa_cheie(db, cheie_escaladare(livrabil.id, livrabil.escaladari))
    if intrare is not None and intrare.stare != coada_erori.Stare.INCHISA.value:
        coada_erori.inchide(db, intrare, motiv=f"reluat de om: {motiv}", utilizator_id=utilizator_id)
    audit.record(
        db,
        "livrabil.reluat_de_om",
        obiect_tip="livrabil",
        obiect_id=livrabil.id,
        utilizator_id=utilizator_id,
        tenant_id=livrabil.tenant_id,
        detalii={"in_starea": tinta.value, "motiv": motiv},
    )
    return Rezultat(livrabil=livrabil, cerut=tinta, stare=tinta)


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
    livrabil = blocheaza(db, livrabil_id)
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
