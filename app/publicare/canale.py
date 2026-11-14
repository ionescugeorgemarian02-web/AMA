"""Conturile canalelor și modul de publicare (F9.1, docs/15 §15.1–§15.3).

Fiecare canal al unui client are un mod efectiv, calculat (nu ales orbește):
- **automat**: aplicația agenției are aprobarea platformei pentru permisiunea canalului, contul e autorizat
  (token valabil) și un om nu l-a trecut pe asistat;
- **automat, în modul de test**: aprobarea nu a venit încă, dar contul e AL AGENȚIEI (15.3: „până la
  aprobare, aplicațiile în modul de test lucrează doar pe conturile agenției”);
- **asistat**: în rest (15.2). Pachetul asistat (F6.6) rămâne drumul de rezervă.

Tokenul se ține criptat (AES-GCM, `AMA_MASTER_KEY`, legat de client și canal) și se citește doar la execuție,
de conector (`token_pentru`). Starea OAuth în curs se ține ca HMAC (fără valoarea în clar).
"""

import datetime as dt
import hmac
import json
import secrets
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.contract import Token
from app.conturi import criptare
from app.db import sesiune_tenant
from app.operare import audit
from app.publicare.modele import AprobareApi, ContCanal


class Mod(StrEnum):
    ASISTAT = "asistat"
    AUTOMAT = "automat"


class StareAprobare(StrEnum):
    NECERUTA = "neceruta"
    IN_TEST = "in_test"
    TRIMISA = "trimisa"
    APROBATA = "aprobata"
    RESPINSA = "respinsa"


ETICHETE_APROBARE = {
    StareAprobare.NECERUTA: "Necerută",
    StareAprobare.IN_TEST: "Mod de test (doar conturile agenției)",
    StareAprobare.TRIMISA: "Trimisă, în analiză",
    StareAprobare.APROBATA: "Aprobată",
    StareAprobare.RESPINSA: "Respinsă",
}

# Canalul → permisiunea aplicației de care depinde publicarea automată (platforma, permisiunea). `None`:
# canalul nu cere aprobare de la o platformă (blogul). Lista crește cu fiecare conector (F9.2–F9.9).
CERINTE: dict[str, tuple[str, str] | None] = {
    "facebook": ("meta", "pagini"),
}


def cerinta(canal: str, setari: dict[str, Any] | None = None) -> tuple[str, str] | None:
    """Permisiunea de care depinde canalul; LinkedIn: profilul (self-serve) sau pagina (cu review)."""
    if canal == "linkedin" and (setari or {}).get("tip_cont") == "pagina":
        return ("linkedin", "pagina")
    return CERINTE[canal]


def are_api(canal: str) -> bool:
    return canal in CERINTE


@dataclass(frozen=True)
class ModEfectiv:
    mod: Mod
    motiv: str
    restrans: bool = False  # automat în modul de test: platforma poate ține postarea privată / ciornă

    @property
    def automat(self) -> bool:
        return self.mod is Mod.AUTOMAT


def mod_efectiv(
    *,
    canal: str,
    cont: ContCanal | None,
    aprobare: StareAprobare | None,
    acum: dt.datetime | None = None,
) -> ModEfectiv:
    """Nucleu pur: modul unui canal, din cont și din aprobarea platformei."""
    acum = acum or dt.datetime.now(dt.UTC)
    if not are_api(canal):
        return ModEfectiv(Mod.ASISTAT, "canalul nu are publicare prin API")
    if cont is None or cont.token_criptat is None:
        return ModEfectiv(Mod.ASISTAT, "contul nu este autorizat")
    if cont.cere_reautorizare or (cont.expira_la is not None and cont.expira_la <= acum):
        return ModEfectiv(Mod.ASISTAT, "contul cere reautorizare")
    if cont.mod_ales == Mod.ASISTAT.value:
        return ModEfectiv(Mod.ASISTAT, "trecut pe asistat de un om")
    if aprobare is None or aprobare is StareAprobare.APROBATA:
        return ModEfectiv(Mod.AUTOMAT, "aprobat de platformă" if aprobare else "fără aprobare necesară")
    if cont.cont_agentie:
        return ModEfectiv(Mod.AUTOMAT, "modul de test, pe contul agenției", restrans=True)
    eticheta = ETICHETE_APROBARE[aprobare].lower()
    return ModEfectiv(Mod.ASISTAT, f"aprobarea platformei este „{eticheta}”: pe contul clientului, asistat")


# --- citire ----------------------------------------------------------------------------------------------


def cont(db: Session, tenant_id: uuid.UUID, canal: str) -> ContCanal | None:
    return db.get(ContCanal, (tenant_id, canal))


def conturi(db: Session) -> list[ContCanal]:
    return list(db.execute(select(ContCanal).order_by(ContCanal.tenant_id, ContCanal.canal)).scalars())


def aprobare(db: Session, platforma: str, permisiune: str) -> AprobareApi | None:
    return db.get(AprobareApi, (platforma, permisiune))


def aprobari(db: Session) -> list[AprobareApi]:
    return list(
        db.execute(select(AprobareApi).order_by(AprobareApi.platforma, AprobareApi.permisiune)).scalars()
    )


def stare_aprobare(db: Session, canal: str, setari: dict[str, Any] | None = None) -> StareAprobare | None:
    c = cerinta(canal, setari) if are_api(canal) else None
    if c is None:
        return None
    a = aprobare(db, *c)
    return StareAprobare(a.stare) if a is not None else StareAprobare.NECERUTA


def mod(db: Session, tenant_id: uuid.UUID, canal: str) -> ModEfectiv:
    c = cont(db, tenant_id, canal)
    return mod_efectiv(
        canal=canal,
        cont=c,
        aprobare=stare_aprobare(db, canal, c.setari if c else None) if are_api(canal) else None,
    )


def token_pentru(tenant_id: uuid.UUID, canal: str) -> Token | None:
    """Tokenul decriptat (doar pentru conector, la execuție)."""
    with sesiune_tenant(tenant_id) as db:
        c = cont(db, tenant_id, canal)
        if c is None or c.token_criptat is None:
            return None
        date = json.loads(criptare.decripteaza(c.token_criptat, aad=_aad(tenant_id, canal)))
        return Token(
            date["acces"], c.expira_la, date.get("reimprospatare", ""), c.cont_extern, tuple(c.scopuri or ())
        )


# --- scriere ---------------------------------------------------------------------------------------------


def _aad(tenant_id: uuid.UUID, canal: str) -> bytes:
    return f"publicare:{tenant_id}:{canal}".encode()


def configureaza(
    db: Session,
    tenant_id: uuid.UUID,
    canal: str,
    *,
    cont_extern: str = "",
    nume: str = "",
    cont_agentie: bool = False,
    setari: dict[str, Any] | None = None,
) -> ContCanal:
    c = cont(db, tenant_id, canal)
    if c is None:
        c = ContCanal(tenant_id=tenant_id, canal=canal, setari={}, scopuri=[])
        db.add(c)
    c.cont_extern, c.nume, c.cont_agentie = cont_extern or c.cont_extern, nume or c.nume, cont_agentie
    if setari is not None:
        c.setari = {**(c.setari or {}), **setari}
    c.actualizat_la = dt.datetime.now(dt.UTC)
    db.flush()
    return c


def salveaza_token(
    db: Session, tenant_id: uuid.UUID, canal: str, token: Token, *, utilizator_id: uuid.UUID | None = None
) -> ContCanal:
    c = cont(db, tenant_id, canal) or configureaza(db, tenant_id, canal)
    clar = json.dumps({"acces": token.acces, "reimprospatare": token.reimprospatare}).encode()
    c.token_criptat = criptare.cripteaza(clar, aad=_aad(tenant_id, canal))
    c.expira_la, c.scopuri = token.expira_la, list(token.scopuri)
    if token.cont_extern:
        c.cont_extern = token.cont_extern
    c.autorizat_la = c.actualizat_la = dt.datetime.now(dt.UTC)
    c.cere_reautorizare, c.stare_oauth = False, None
    db.flush()
    audit.record(
        db,
        "publicare.cont_autorizat",
        obiect_tip="canal",
        obiect_id=f"{tenant_id}:{canal}",
        utilizator_id=utilizator_id,
        tenant_id=tenant_id,
        detalii={"canal": canal, "expira_la": token.expira_la.isoformat() if token.expira_la else None},
    )
    return c


def incepe_oauth(db: Session, tenant_id: uuid.UUID, canal: str) -> str:
    """Starea OAuth (anti-CSRF): valoarea pleacă la platformă, în bază rămâne doar HMAC-ul ei."""
    c = cont(db, tenant_id, canal) or configureaza(db, tenant_id, canal)
    stare = f"{canal}.{secrets.token_urlsafe(24)}"
    c.stare_oauth = criptare.hmac_valoare("oauth", stare)
    db.flush()
    return stare


def consuma_oauth(db: Session, tenant_id: uuid.UUID, canal: str, stare: str) -> bool:
    c = cont(db, tenant_id, canal)
    if c is None or c.stare_oauth is None or not stare.startswith(f"{canal}."):
        return False
    bun = hmac.compare_digest(bytes(c.stare_oauth), criptare.hmac_valoare("oauth", stare))
    if bun:
        c.stare_oauth = None
        db.flush()
    return bun


def alege_mod(
    db: Session, tenant_id: uuid.UUID, canal: str, mod_nou: Mod, *, utilizator_id: uuid.UUID, motiv: str = ""
) -> ContCanal:
    """Un om trece canalul pe asistat (sau înapoi pe automat, dacă aprobarea și contul o permit)."""
    c = cont(db, tenant_id, canal) or configureaza(db, tenant_id, canal)
    vechi, c.mod_ales = c.mod_ales, mod_nou.value
    c.actualizat_la = dt.datetime.now(dt.UTC)
    db.flush()
    audit.record(
        db,
        "publicare.mod_ales",
        obiect_tip="canal",
        obiect_id=f"{tenant_id}:{canal}",
        utilizator_id=utilizator_id,
        tenant_id=tenant_id,
        detalii={"canal": canal, "din": vechi, "in": mod_nou.value, "motiv": motiv[:200]},
    )
    return c


def cere_reautorizare(db: Session, tenant_id: uuid.UUID, canal: str, motiv: str) -> bool:
    """Steagul de reautorizare (F9.8). Întoarce True dacă e nou."""
    c = cont(db, tenant_id, canal)
    if c is None or c.cere_reautorizare:
        return False
    c.cere_reautorizare = True
    c.actualizat_la = dt.datetime.now(dt.UTC)
    db.flush()
    audit.record(
        db,
        "publicare.reautorizare_ceruta",
        obiect_tip="canal",
        obiect_id=f"{tenant_id}:{canal}",
        tenant_id=tenant_id,
        actor_tip="sistem",
        detalii={"canal": canal, "motiv": motiv[:200]},
    )
    return True
