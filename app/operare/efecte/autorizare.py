"""Ușa executorului spre partea de cont a conectorilor de publicare (F9.1): autorizarea OAuth,
reîmprospătarea tokenului, starea unei postări și limitele. Conectorii se cheamă DOAR din `app/operare/efecte`
(garda `check_efecte`), deci și aceste apeluri trec pe aici, nu direct din `app.publicare`.

    from app.operare.efecte import autorizare
    url = autorizare.url_autorizare(db, tenant, "facebook", redirect=...)
    autorizare.finalizeaza(db, tenant, "facebook", cod=..., stare=..., redirect=..., utilizator_id=om)
"""

import uuid

from sqlalchemy.orm import Session

from app.connectors import registru
from app.connectors.contract import Limite, StarePostare
from app.connectors.publicare import ConectorPublicare
from app.operare import audit
from app.operare.efecte import executor
from app.publicare import canale


class AutorizareRefuzata(RuntimeError):
    """Starea OAuth nu se potrivește sau canalul nu are conector de publicare."""


def conector(canal: str) -> ConectorPublicare:
    try:
        c = registru.conector_pentru(canal)
    except registru.ConectorNecunoscut:
        raise AutorizareRefuzata(f"canalul „{canal}” nu are conector de publicare") from None
    if not isinstance(c, ConectorPublicare):
        raise AutorizareRefuzata(f"conectorul canalului „{canal}” nu este unul de publicare")
    return c


def url_autorizare(db: Session, tenant_id: uuid.UUID, canal: str, *, redirect: str) -> str:
    c = conector(canal)
    return c.url_autorizare(canale.incepe_oauth(db, tenant_id, canal), redirect)


def finalizeaza(
    db: Session, tenant_id: uuid.UUID, canal: str, *, cod: str, stare: str, redirect: str,
    utilizator_id: uuid.UUID | None,
) -> None:  # fmt: skip
    """Platforma a întors codul: se verifică starea, se schimbă codul pe token (criptat în bază) și, dacă
    canalul era pe pauză după o eroare de autentificare, pauza se ridică și efectele ținute pe loc pleacă."""
    if not canale.consuma_oauth(db, tenant_id, canal, stare):
        audit.record(
            db, "publicare.oauth_refuzat", obiect_tip="canal", obiect_id=f"{tenant_id}:{canal}",
            tenant_id=tenant_id, utilizator_id=utilizator_id, rezultat="esec", detalii={"canal": canal},
        )  # fmt: skip
        raise AutorizareRefuzata("starea autorizării nu se potrivește; reia autorizarea")
    token = conector(canal).schimba_cod(cod, redirect)
    canale.salveaza_token(db, tenant_id, canal, token, utilizator_id=utilizator_id)
    executor.reia_conectorul(db, tenant_id, canal, utilizator_id=utilizator_id)


def reimprospateaza(db: Session, tenant_id: uuid.UUID, canal: str) -> bool:
    """Reîmprospătarea tokenului fără om (unde platforma o permite). False: cere reautorizare."""
    vechi = canale.token_pentru(tenant_id, canal)
    if vechi is None or not vechi.reimprospatare:
        return False
    try:
        nou = conector(canal).reimprospateaza(vechi)
    except Exception:
        return False
    canale.salveaza_token(db, tenant_id, canal, nou)
    return True


def stare_postare(tenant_id: uuid.UUID, canal: str, id_extern: str) -> StarePostare:
    return conector(canal).stare(tenant_id, id_extern)


def limite(tenant_id: uuid.UUID, canal: str) -> Limite:
    return conector(canal).limite(tenant_id)
