"""Executorul de efecte externe (B7, F2.5, 7.3 și 7.5): singura ușă spre exterior.

Fluxul, pe scurt:
1. O componentă cere efectul în aceeași tranzacție cu schimbarea de stare care îl justifică (`cere`): rând în
   `efecte_de_trimis`, cu cheie de idempotență unică. După commit, un flux durabil (`efecte.executa`)
   îl preia, pe coada
   canalului.
2. `incearca_efect` face o încercare: verifică valabilitatea (aceeași versiune, livrabilul încă în
  publicare), pauza
   conectorului și opririle (chiar înainte de trimitere, nu doar la programare), notează `în trimitere`
   ÎNAINTE să cheme
   conectorul și notează rezultatul DUPĂ. Dacă procesul moare între cele două, efectul rămâne `în
   trimitere`: rezultat
   necunoscut. Orice încercare de după o eroare sau un rezultat necunoscut începe cu `verifica` (7.3).
3. Rezultatul: `trimis` (și livrabilul `în publicare` → `publicat`, în aceeași tranzacție), reîncercare (erori
   temporare, cu pauză crescătoare), pauză pe conector (autentificare) sau `eșuat` (livrabilul merge în
   coada de erori).
4. Efectul oprit (oprire globală sau pe client) rămâne `în așteptare`: nu se pierde și nu se marchează
  eșuat. Jobul
   programat `efecte.tic` îl repune în coadă după repornire; dacă între timp nu mai e valabil, se
   anulează cu motiv.

O singură încercare rulează odată pe un efect (încuietoare de sesiune în Postgres, `servicii.incuietoare`).
"""

import contextlib
import datetime as dt
import uuid
from typing import Any

from sqlalchemy import event, or_, select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app import productie
from app.config import get_settings
from app.connectors import registru
from app.connectors.contract import EfectDeTrimis, RezultatPlatforma
from app.db import sesiune_agentie, sesiune_tenant
from app.logging import get_logger
from app.operare import audit, coada_erori, motor, notificari
from app.operare.efecte import servicii
from app.operare.efecte.modele import Efect
from app.operare.efecte.stari import DESCHISE, FINALE, Stare, Tip
from app.operare.notificari import Nivel

log = get_logger("app.efecte")

NUME_TIC = "efecte.tic"
COMPONENTA = "B7"
LIMITA_TIC = 200
_REINCERCARI = get_settings().efecte_reincercari
_PAUZA = get_settings().efecte_pauza_sec


def _dupa_commit(db: Session, actiune: Any) -> None:
    def ruleaza(_sesiune: Session) -> None:
        try:
            actiune()
        except Exception as exc:  # un canal sau o coadă căzută nu strică lucrul terminat; "tic"-ul reia
            log.warning("acțiune după commit nereușită", extra={"tip_eroare": type(exc).__name__})

    event.listen(db, "after_commit", ruleaza, once=True)


def _anunta(db: Session, nivel: Nivel, titlu: str, text: str, url: str = "/operare") -> None:
    _dupa_commit(db, lambda: notificari.notifica(nivel, titlu, text, url=url))


def _spec(e: Efect) -> EfectDeTrimis:
    return EfectDeTrimis(
        id=e.id,
        tenant_id=e.tenant_id,
        livrabil_id=e.livrabil_id,
        canal=e.canal,
        versiune=e.versiune,
        tip=e.tip,
        idem=e.cheia,
        payload=dict(e.payload),
    )


# --- cererea (partea tranzacțională)
# ---------------------------------------------------------------------------------


def cere(
    db: Session,
    livrabil_id: uuid.UUID,
    *,
    tip: Tip = Tip.PUBLICARE,
    payload: dict[str, Any] | None = None,
    porneste: bool = True,
) -> servicii.Cerere:
    """Cere un efect extern. Se apelează în aceeași sesiune (tranzacție) cu `productie.muta(...
    IN_PUBLICARE)`.
    Același efect cerut a doua oară întoarce rândul primei cereri (`nou=False`) și nu pornește nimic.
    După commit, efectul este pus pe coada canalului (`porneste=False`: doar în teste)."""
    cerere = servicii.inregistreaza(db, livrabil_id, tip=tip, payload=payload)
    e = cerere.efect
    # nou, sau cerut deja dar fără job viu (pas repetat după o cădere între commit și coadă)
    de_pornit = cerere.nou or (Stare(e.stare) in DESCHISE and e.programat_la is None)
    if de_pornit and porneste:
        efect_id = e.id
        _dupa_commit(db, lambda: porneste_executia(efect_id))
    return cerere


def porneste_executia(efect_id: uuid.UUID) -> str | None:
    """Pune efectul pe coada canalului lui, ca job durabil. Numărul rulării intră în cheia jobului,
    deci o repunere
    (după oprire sau după un job pierdut) nu se confundă cu un job vechi încheiat. Întoarce id-ul jobului."""
    with sesiune_agentie() as db:
        r = db.execute(
            update(Efect)
            .where(Efect.id == efect_id, Efect.stare.in_([s.value for s in DESCHISE]))
            .values(rulari=Efect.rulari + 1, programat_la=func.now())
            .returning(Efect.tenant_id, Efect.rulari, Efect.canal)
        ).first()
    if r is None:
        return None
    tenant_id, rulari, canal = r
    return motor.trimite(
        executa,
        str(tenant_id),
        str(efect_id),
        coada=registru.coada_pentru(canal),
        cheie=f"efect:{efect_id}:{rulari}",
    )


# --- o încercare
# ---------------------------------------------------------------------------------------------------


def incearca_efect(tenant_id: uuid.UUID, efect_id: uuid.UUID) -> str:
    """O încercare de trimitere. Întoarce: `trimis`, `anulat`, `oprit`, `pauza`, `autentificare`,
    `esuat` sau `ocupat`
    (altă încercare e în curs). Aruncă `EroareTemporara` când trebuie reîncercat (rezultatul poate fi
    necunoscut)."""
    with servicii.incuietoare(efect_id) as luata:
        if not luata:
            return "ocupat"
        return _incearca(tenant_id, efect_id)


def _tine_pe_loc(db: Session, e: Efect, motiv: str) -> None:
    e.motiv = motiv[:300]
    e.programat_la = None
    e.actualizat_la = func.now()
    db.flush()


def _incearca(tenant_id: uuid.UUID, efect_id: uuid.UUID) -> str:
    with sesiune_tenant(tenant_id) as db:
        e = servicii.blocheaza(db, efect_id)
        stare = Stare(e.stare)
        if stare in FINALE:
            return stare.value
        if stare is Stare.ESUAT_DEFINITIV:
            return "esuat"  # îl reia un om
        nevalabil = servicii.motiv_nevalabil(db, e)
        if nevalabil:
            servicii.muta_efect(db, e, Stare.ANULAT, motiv=nevalabil)
            audit.record(
                db, "efect.anulat", obiect_tip="efect", obiect_id=e.id, tenant_id=e.tenant_id,
                actor_tip="sistem", detalii={"motiv": nevalabil},
            )  # fmt: skip
            return "anulat"
        if servicii.pauza(db, e.tenant_id, e.canal) is not None:
            _tine_pe_loc(db, e, "pauză: canalul cere reautorizare")
            return "pauza"
        oprit = servicii.motiv_oprit(db, e)
        if oprit:
            _tine_pe_loc(db, e, oprit)
            return "oprit"
        cu_verificare = e.incercari > 0  # a mai fost o încercare: rezultatul ei poate fi necunoscut
        if stare is Stare.IN_TRIMITERE:
            e.incercari += 1
            e.actualizat_la = func.now()
            db.flush()
        else:
            servicii.muta_efect(db, e, Stare.IN_TRIMITERE, incercari=e.incercari + 1, motiv="")
        audit.record(
            db, "efect.incercare", obiect_tip="efect", obiect_id=e.id, tenant_id=e.tenant_id,
            actor_tip="sistem",
            detalii={"incercare": e.incercari, "verificare": cu_verificare, "canal": e.canal},
        )  # fmt: skip
        spec = _spec(e)
    try:
        conector = registru.conector_pentru(spec.canal)
    except registru.ConectorNecunoscut:
        return _esec_definitiv(
            tenant_id, efect_id, "ConectorNecunoscut", f"niciun conector pentru „{spec.canal}”"
        )
    try:
        rezultat = conector.verifica(spec) if cu_verificare else None
        if rezultat is None:
            rezultat = conector.trimite(spec)
    except motor.EroareAutentificare:
        return _autentificare(tenant_id, efect_id)
    except motor.EroareDefinitiva as exc:
        return _esec_definitiv(tenant_id, efect_id, type(exc).__name__, str(exc))
    except Exception as exc:  # temporară sau necunoscută (timeout …): rezultatul poate exista la platformă
        _esec_temporar(tenant_id, efect_id, exc)
        raise motor.EroareTemporara(f"{type(exc).__name__}: {exc}"[:300]) from exc
    return _succes(tenant_id, efect_id, rezultat)


def _succes(tenant_id: uuid.UUID, efect_id: uuid.UUID, rezultat: RezultatPlatforma) -> str:
    with sesiune_tenant(tenant_id) as db:
        e = servicii.blocheaza(db, efect_id)
        if Stare(e.stare) is Stare.TRIMIS:
            return "trimis"
        servicii.muta_efect(
            db, e, Stare.TRIMIS, id_extern=rezultat.id_extern, link=rezultat.link or None,
            trimis_la=func.now(), eroare_cod=None, eroare_mesaj=None, motiv="",
        )  # fmt: skip
        audit.record(
            db, "efect.trimis", obiect_tip="efect", obiect_id=e.id, tenant_id=e.tenant_id, actor_tip="sistem",
            detalii={"id_extern": rezultat.id_extern, "link": rezultat.link, "incercari": e.incercari},
        )  # fmt: skip
        try:
            productie.muta(
                db, e.livrabil_id, productie.Stare.IN_PUBLICARE, productie.Stare.PUBLICAT,
                componenta=COMPONENTA, motiv="publicat la platformă",
                detalii={"id_extern": rezultat.id_extern, "link": rezultat.link, "efect": str(e.id)},
            )  # fmt: skip
        except productie.TranzitieRefuzata as exc:
            # Platforma are efectul, dar livrabilul nu mai e unde trebuia: o abatere pentru un om, nu o
            # pierdere.
            audit.record(
                db, "efect.livrabil_nealiniat", obiect_tip="efect", obiect_id=e.id, tenant_id=e.tenant_id,
                actor_tip="sistem", rezultat="esec", detalii={"motiv": str(exc)},
            )  # fmt: skip
            _anunta(
                db,
                Nivel.IMPORTANT,
                "Efect trimis, livrabil nealiniat",
                "Un efect a ajuns la platformă, dar livrabilul nu era în publicare.",
            )
    return "trimis"


def _esec_temporar(tenant_id: uuid.UUID, efect_id: uuid.UUID, exc: BaseException) -> None:
    with sesiune_tenant(tenant_id) as db:
        e = servicii.blocheaza(db, efect_id)
        if Stare(e.stare) is Stare.IN_TRIMITERE:
            servicii.muta_efect(
                db, e, Stare.ESUAT_TEMPORAR, eroare_cod=type(exc).__name__, eroare_mesaj=str(exc)[:500]
            )
        audit.record(
            db, "efect.esec_temporar", obiect_tip="efect", obiect_id=e.id, tenant_id=e.tenant_id,
            actor_tip="sistem", rezultat="esec",
            detalii={"tip_eroare": type(exc).__name__, "incercare": e.incercari},
        )  # fmt: skip


def _autentificare(tenant_id: uuid.UUID, efect_id: uuid.UUID) -> str:
    """Tokenul canalului a expirat: efectul rămâne în așteptare, canalul intră pe pauză și apare cererea de
    reautorizare (steag + alertă; reautorizarea propriu-zisă e a conectorului real, F9)."""
    with sesiune_tenant(tenant_id) as db:
        e = servicii.blocheaza(db, efect_id)
        if Stare(e.stare) is Stare.IN_TRIMITERE:
            servicii.muta_efect(db, e, Stare.IN_ASTEPTARE)
        _tine_pe_loc(db, e, "pauză: canalul cere reautorizare")
        nou = servicii.pune_pauza(db, e.tenant_id, e.canal, "eroare de autentificare")
        audit.record(
            db, "conector.pauza", obiect_tip="conector", obiect_id=f"{e.tenant_id}:{e.canal}",
            tenant_id=e.tenant_id, actor_tip="sistem", rezultat="esec",
            detalii={"canal": e.canal, "motiv": "autentificare", "nou": nou},
        )  # fmt: skip
        if nou:
            _anunta(
                db,
                Nivel.IMPORTANT,
                "Reautorizare necesară",
                f"Canalul „{e.canal}” a fost pus pe pauză: autentificarea a expirat.",
            )
    return "autentificare"


def _esec_definitiv(tenant_id: uuid.UUID, efect_id: uuid.UUID, tip_eroare: str, mesaj: str) -> str:
    """Refuzat sau încercări epuizate: efectul e `eșuat`, livrabilul merge în coada de erori cu context
    complet."""
    with sesiune_tenant(tenant_id) as db:
        e = servicii.blocheaza(db, efect_id)
        if Stare(e.stare) in FINALE:
            return Stare(e.stare).value
        servicii.muta_efect(db, e, Stare.ESUAT_DEFINITIV, eroare_cod=tip_eroare, eroare_mesaj=mesaj[:500])
        audit.record(
            db, "efect.esuat", obiect_tip="efect", obiect_id=e.id, tenant_id=e.tenant_id, actor_tip="sistem",
            rezultat="esec", detalii={"tip_eroare": tip_eroare, "incercari": e.incercari},
        )  # fmt: skip
        with contextlib.suppress(productie.TranzitieRefuzata):  # nu mai e în publicare: efectul rămâne eșuat
            productie.muta(
                db, e.livrabil_id, productie.Stare.IN_PUBLICARE, productie.Stare.COADA_DE_ERORI,
                componenta=COMPONENTA, motiv=f"efect extern eșuat: {tip_eroare}",
            )  # fmt: skip
        coada_erori.inregistreaza_escaladare(
            db,
            tenant_id=e.tenant_id,
            cheie=cheie_esec(e),
            flux="efect",
            pas=e.tip,
            eroare_tip=tip_eroare,
            mesaj=f"efect „{e.tip}” pe „{e.canal}” eșuat după {e.incercari} încercări: {mesaj}",
            context={
                "tip_sursa": "efect",
                "efect_id": str(e.id),
                "livrabil_id": str(e.livrabil_id),
                "canal": e.canal,
                "tip": e.tip,
                "versiune": e.versiune,
                "incercari": e.incercari,
                "eroare_tip": tip_eroare,
                "eroare_mesaj": mesaj[:300],
                "cheia": e.cheia,
            },
        )
        _anunta(
            db,
            Nivel.IMPORTANT,
            "Un efect extern a eșuat",
            f"Efectul „{e.tip}” pe „{e.canal}” cere intervenție.",
            f"/productie/{e.livrabil_id}",
        )
    return "esuat"


def cheie_esec(e: Efect) -> str:
    """Cheia intrării din coada de erori pentru eșecul curent al efectului (una per eșec)."""
    return f"efect-esec:{e.id}:{e.incercari}"


def epuizeaza_efect(tenant_id: uuid.UUID, efect_id: uuid.UUID) -> str:
    """Reîncercările s-au terminat. O ultimă întrebare la platformă (poate efectul totuși există);
    altfel, eșuat."""
    with servicii.incuietoare(efect_id) as luata:
        if not luata:
            return "ocupat"
        with sesiune_tenant(tenant_id) as db:
            e = servicii.blocheaza(db, efect_id)
            if Stare(e.stare) in FINALE or Stare(e.stare) is Stare.ESUAT_DEFINITIV:
                return e.stare
            spec = _spec(e)
        try:
            gasit = registru.conector_pentru(spec.canal).verifica(spec)
        except Exception:
            gasit = None
        if gasit is not None:
            return _succes(tenant_id, efect_id, gasit)
        return _esec_definitiv(
            tenant_id, efect_id, "IncercariEpuizate", "reîncercările au fost epuizate fără rezultat"
        )


# --- fluxul durabil
# -------------------------------------------------------------------------------------------------


@motor.pas("efecte.incearca", reincercari=_REINCERCARI, pauza_sec=_PAUZA, factor=2.0)
def incearca(tenant_id: str, efect_id: str) -> str:
    return incearca_efect(uuid.UUID(tenant_id), uuid.UUID(efect_id))


@motor.pas("efecte.epuizeaza")
def epuizeaza(tenant_id: str, efect_id: str) -> str:
    return epuizeaza_efect(uuid.UUID(tenant_id), uuid.UUID(efect_id))


@motor.flux("efecte.executa")
def executa(tenant_id: str, efect_id: str) -> str:
    """Un efect, pe coada canalului lui. Erorile temporare sunt reîncercate de pas, cu pauză crescătoare, iar
    fiecare reîncercare începe cu `verifica`; la epuizare, o ultimă verificare și apoi coada de erori."""
    try:
        return incearca(tenant_id, efect_id)
    except Exception:
        return epuizeaza(tenant_id, efect_id)


# --- plasa de siguranță: „tic”-ul
# -----------------------------------------------------------------------------------


def redistribuie() -> int:
    """Repune în coadă efectele deschise care nu au un job viu: cele ținute pe loc de o oprire sau o
    pauză care s-au
    terminat, cele al căror job s-a pierdut (după `AMA_EFECTE_REDISTRIBUIRE_SEC`). Cele oprite acum
    rămân pe loc."""
    prag = get_settings().efecte_redistribuire_sec
    de_pornit: list[uuid.UUID] = []
    with sesiune_agentie() as db:
        candidati = (
            db.execute(
                select(Efect)
                .where(
                    Efect.stare.in_([s.value for s in DESCHISE]),
                    or_(
                        Efect.programat_la.is_(None),
                        Efect.programat_la < func.now() - dt.timedelta(seconds=prag),
                    ),
                )
                .order_by(Efect.creat_la)
                .limit(LIMITA_TIC)
            )
            .scalars()
            .all()
        )
        for e in candidati:
            if servicii.pauza(db, e.tenant_id, e.canal) is None and servicii.motiv_oprit(db, e) is None:
                de_pornit.append(e.id)
    return sum(1 for i in de_pornit if porneste_executia(i) is not None)


@motor.pas("efecte.pas_redistribuie")
def _redistribuie_pas() -> str:
    return f"repuse={redistribuie()}"


@motor.flux(NUME_TIC)
def tic(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _redistribuie_pas()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME_TIC, "* * * * *", tic)


declara_programari()


# --- acțiunile oamenilor
# --------------------------------------------------------------------------------------------


def reia_conectorul(
    db: Session, tenant_id: uuid.UUID, canal: str, *, utilizator_id: uuid.UUID | None
) -> bool:
    """Canalul a fost reautorizat: pauza se ridică, iar efectele ținute pe loc pleacă (după commit)."""
    ridicat = servicii.ridica_pauza(db, tenant_id, canal, utilizator_id=utilizator_id)
    if ridicat:
        _dupa_commit(db, redistribuie)
    return ridicat


def reia_livrabilul(
    db: Session, livrabil_id: uuid.UUID, *, utilizator_id: uuid.UUID, motiv: str
) -> productie.Rezultat:
    """Un om reia un livrabil din coada de erori (`productie.reia_de_om`) și, dacă motivul era un efect
    extern eșuat,
    reia și efectul: înapoi în așteptare, iar înainte de trimitere executorul întreabă `verifica`."""
    rezultat = productie.reia_de_om(db, livrabil_id, utilizator_id=utilizator_id, motiv=motiv)
    repuse: list[uuid.UUID] = []
    for e in servicii.ale_livrabilului(db, livrabil_id):
        if Stare(e.stare) is not Stare.ESUAT_DEFINITIV:
            continue
        intrare = coada_erori.dupa_cheie(db, cheie_esec(e))
        if servicii.motiv_nevalabil(db, e) is None:
            servicii.repune_in_asteptare(db, e.id, motiv=motiv, utilizator_id=utilizator_id)
            repuse.append(e.id)
        if intrare is not None and intrare.stare != coada_erori.Stare.INCHISA.value:
            coada_erori.inchide(db, intrare, motiv=f"reluat de om: {motiv}", utilizator_id=utilizator_id)
    for i in repuse:
        _dupa_commit(db, lambda i=i: porneste_executia(i))
    return rezultat
