"""Fluxul de autentificare: parolă, al doilea factor, înrolare. Rulează în contextul `auth` al bazei.

Reguli: același răspuns și aceeași muncă pentru utilizator necunoscut și parolă greșită; limitare pe cont și
pe IP; rotirea sesiunii după fiecare pas; nicio parolă, cod sau jeton în jurnale.
"""

import time
import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.conturi import criptare, limitare, parole, sesiuni, totp
from app.conturi.modele import Apartenenta, CodRecuperare, Utilizator
from app.conturi.roluri import necesita_al_doilea_factor, rol_valid
from app.conturi.sesiuni import SesiuneCurenta
from app.operare import audit


class Rezultat(StrEnum):
    OK = "ok"
    INVALID = "invalid"  # mesaj generic: nu spune ce a fost greșit
    BLOCAT = "blocat"


@dataclass(frozen=True)
class PasulUrmator:
    rezultat: Rezultat
    jeton: str | None = None
    urmator: str | None = None  # "/conturi/2fa", "/conturi/2fa/inrolare" sau None (autentificat complet)
    coduri_recuperare: tuple[str, ...] = ()


def _ceas() -> float:
    """Separat pentru ca testele să poată avansa timpul (coduri TOTP pe pași diferiți)."""
    return time.time()


def normalizeaza_email(email: str) -> str:
    return email.strip().lower()[:254]


def _cheie_cont(email: str) -> bytes:
    return criptare.hmac_valoare("cont", normalizeaza_email(email))


def _inregistreaza_esec(
    db: Session, cheie: bytes, ip: str, tip: str, utilizator_id: uuid.UUID | None
) -> None:
    """Notează eșecul și semnalează în audit trecerea pragului (o singură dată pe prag)."""
    limitare.inregistreaza(db, cheie, ip, tip, reusit=False)
    s = get_settings()
    detalii = {"tip": tip}
    if limitare.esecuri_cont(db, cheie) == s.login_max_failures_account:
        audit.record(
            db,
            "autentificare.blocare_cont",
            rezultat="refuzat",
            utilizator_id=utilizator_id,
            ip=ip,
            tenant_id=None,
            detalii={**detalii, "cont": cheie.hex()[:16], "minute": s.login_window_minutes},
        )
    if limitare.esecuri_ip(db, ip) == s.login_max_failures_ip:
        audit.record(
            db,
            "autentificare.blocare_ip",
            rezultat="refuzat",
            utilizator_id=None,
            ip=ip,
            tenant_id=None,
            detalii={**detalii, "minute": s.login_window_minutes},
        )


def _apartenenta(db: Session, utilizator_id: uuid.UUID) -> Apartenenta | None:
    return db.execute(
        select(Apartenenta).where(Apartenenta.utilizator_id == utilizator_id, Apartenenta.sters_la.is_(None))
    ).scalar_one_or_none()


def _tenant_audit(ap: Apartenenta | None) -> uuid.UUID | None:
    return ap.tenant_id if ap else None


def autentifica_cu_parola(
    db: Session,
    *,
    email: str,
    parola: str,
    ip: str,
    user_agent: str | None,
    sesiune_veche: SesiuneCurenta | None,
) -> PasulUrmator:
    """Pasul 1. La reușită întoarce jetonul unei sesiuni noi (completă sau în așteptarea 2FA)."""
    cheie = _cheie_cont(email)
    utilizator = db.execute(
        select(Utilizator).where(Utilizator.email == normalizeaza_email(email), Utilizator.sters_la.is_(None))
    ).scalar_one_or_none()
    # Aceeași muncă (o verificare argon2) indiferent dacă utilizatorul există.
    parola_buna = parole.verifica(utilizator.parola_hash if utilizator else None, parola)
    if limitare.blocat(db, cheie, ip):
        return PasulUrmator(Rezultat.BLOCAT)  # nu se înregistrează încercări în timpul blocării
    ap = _apartenenta(db, utilizator.id) if utilizator else None
    if not (utilizator and parola_buna and utilizator.stare == "activ" and ap and rol_valid(ap.rol)):
        _inregistreaza_esec(db, cheie, ip, "parola", utilizator.id if utilizator else None)
        audit.record(
            db,
            "autentificare.esec",
            rezultat="esec",
            utilizator_id=utilizator.id if utilizator else None,
            tenant_id=_tenant_audit(ap),
            ip=ip,
            actor_tip="anonim" if utilizator is None else "utilizator",
            detalii={"cont": cheie.hex()[:16]},
        )
        return PasulUrmator(Rezultat.INVALID)

    if parole.necesita_rehash(utilizator.parola_hash):
        utilizator.parola_hash = parole.hash_parola(parola)
    rol = rol_valid(ap.rol)
    if rol is None:  # exclus de verificarea de mai sus; păstrat pentru tipare
        raise RuntimeError("rol necunoscut")
    if sesiune_veche is not None:
        sesiuni.revoca(db, sesiune_veche.sesiune_id)  # nimic din vechea sesiune nu supraviețuiește
    cere_factor = utilizator.totp_activ or necesita_al_doilea_factor(rol)
    jeton = sesiuni.creeaza(db, utilizator.id, mfa_verificat=not cere_factor, ip=ip, user_agent=user_agent)
    if not cere_factor:
        limitare.inregistreaza(db, cheie, ip, "parola", reusit=True)
        audit.record(
            db,
            "autentificare.reusita",
            utilizator_id=utilizator.id,
            tenant_id=ap.tenant_id,
            ip=ip,
            detalii={"al_doilea_factor": False},
        )
        return PasulUrmator(Rezultat.OK, jeton, None)
    audit.record(
        db, "autentificare.parola_acceptata", utilizator_id=utilizator.id, tenant_id=ap.tenant_id, ip=ip
    )
    return PasulUrmator(
        Rezultat.OK, jeton, "/conturi/2fa" if utilizator.totp_activ else "/conturi/2fa/inrolare"
    )


def _utilizator(db: Session, sesiune: SesiuneCurenta) -> Utilizator:
    return db.execute(select(Utilizator).where(Utilizator.id == sesiune.utilizator_id)).scalar_one()


def _secret(utilizator: Utilizator) -> str | None:
    if not utilizator.totp_secret_enc:
        return None
    return criptare.decripteaza(utilizator.totp_secret_enc, aad=utilizator.id.bytes).decode()


def _consuma_pas(db: Session, utilizator_id: uuid.UUID, pas: int) -> bool:
    """Marchează pasul ca folosit, atomic: două cereri paralele cu același cod nu reușesc amândouă."""
    r = db.execute(
        update(Utilizator)
        .where(
            Utilizator.id == utilizator_id,
            (Utilizator.totp_ultim_pas.is_(None)) | (Utilizator.totp_ultim_pas < pas),
        )
        .values(totp_ultim_pas=pas)
    )
    return limitare.rand_afectate(r) == 1


def _finalizeaza(
    db: Session,
    sesiune: SesiuneCurenta,
    cheie: bytes,
    ip: str,
    user_agent: str | None,
    tip: str,
    actiune: str,
) -> str:
    limitare.inregistreaza(db, cheie, ip, tip, reusit=True)
    jeton = sesiuni.roteste(db, sesiune, mfa_verificat=True, ip=ip, user_agent=user_agent)
    audit.record(
        db, actiune, utilizator_id=sesiune.utilizator_id, tenant_id=sesiune.tenant_apartenenta, ip=ip
    )
    return jeton


def verifica_al_doilea_factor(
    db: Session, sesiune: SesiuneCurenta, cod: str, *, ip: str, user_agent: str | None
) -> PasulUrmator:
    """Pasul 2: cod TOTP sau cod de recuperare. Reușita rotește sesiunea într-una completă."""
    cheie = _cheie_cont(sesiune.email)
    if limitare.blocat(db, cheie, ip):
        return PasulUrmator(Rezultat.BLOCAT)
    utilizator = _utilizator(db, sesiune)
    if totp.arata_ca_totp(cod):
        secret = _secret(utilizator) if utilizator.totp_activ else None
        pas = (
            totp.pas_valid(secret, cod, ultim_pas=utilizator.totp_ultim_pas, acum=_ceas()) if secret else None
        )
        if pas is not None and _consuma_pas(db, utilizator.id, pas):
            jeton = _finalizeaza(db, sesiune, cheie, ip, user_agent, "totp", "autentificare.2fa_reusita")
            return PasulUrmator(Rezultat.OK, jeton)
        tip = "totp"
    else:
        h = criptare.hmac_valoare("recuperare", totp.normalizeaza_cod_recuperare(cod))
        folosit = db.execute(
            update(CodRecuperare)
            .where(
                CodRecuperare.utilizator_id == utilizator.id,
                CodRecuperare.cod_hash == h,
                CodRecuperare.folosit_la.is_(None),
            )
            .values(folosit_la=sesiuni.acum())
            .returning(CodRecuperare.id)
        ).first()
        if folosit is not None:
            jeton = _finalizeaza(
                db, sesiune, cheie, ip, user_agent, "recuperare", "autentificare.2fa_recuperare"
            )
            return PasulUrmator(Rezultat.OK, jeton)
        tip = "recuperare"
    _inregistreaza_esec(db, cheie, ip, tip, utilizator.id)
    audit.record(
        db,
        "autentificare.2fa_esec",
        rezultat="esec",
        utilizator_id=utilizator.id,
        tenant_id=sesiune.tenant_apartenenta,
        ip=ip,
        detalii={"tip": tip},
    )
    return PasulUrmator(Rezultat.INVALID)


@dataclass(frozen=True)
class Inrolare:
    secret: str
    uri: str


def incepe_inrolare(db: Session, sesiune: SesiuneCurenta) -> Inrolare | None:
    """Secretul se generează la prima cerere și se reîntoarce până la confirmare; `None` dacă 2FA e activ."""
    utilizator = _utilizator(db, sesiune)
    if utilizator.totp_activ:
        return None
    secret = _secret(utilizator)  # un secret neconfirmat se refolosește: utilizatorul l-a putut deja scana
    if secret is None:
        secret = totp.secret_nou()
        utilizator.totp_secret_enc = criptare.cripteaza(secret.encode(), aad=utilizator.id.bytes)
        utilizator.totp_ultim_pas = None
        db.flush()
        audit.record(
            db,
            "autentificare.2fa_inrolare_inceputa",
            utilizator_id=utilizator.id,
            tenant_id=sesiune.tenant_apartenenta,
        )
    return Inrolare(secret, totp.uri_provizionare(secret, sesiune.email))


def confirma_inrolare(
    db: Session, sesiune: SesiuneCurenta, cod: str, *, ip: str, user_agent: str | None
) -> PasulUrmator:
    """Confirmă secretul cu un cod valid, activează 2FA, emite codurile de recuperare și rotește sesiunea."""
    cheie = _cheie_cont(sesiune.email)
    if limitare.blocat(db, cheie, ip):
        return PasulUrmator(Rezultat.BLOCAT)
    utilizator = _utilizator(db, sesiune)
    secret = None if utilizator.totp_activ else _secret(utilizator)
    pas = totp.pas_valid(secret, cod, ultim_pas=utilizator.totp_ultim_pas, acum=_ceas()) if secret else None
    if pas is None or not _consuma_pas(db, utilizator.id, pas):
        _inregistreaza_esec(db, cheie, ip, "totp", utilizator.id)
        audit.record(
            db,
            "autentificare.2fa_inrolare_esec",
            rezultat="esec",
            utilizator_id=utilizator.id,
            tenant_id=sesiune.tenant_apartenenta,
            ip=ip,
        )
        return PasulUrmator(Rezultat.INVALID)
    utilizator.totp_activ = True
    coduri = totp.coduri_recuperare_noi()
    db.execute(
        update(CodRecuperare)
        .where(CodRecuperare.utilizator_id == utilizator.id, CodRecuperare.folosit_la.is_(None))
        .values(folosit_la=sesiuni.acum())
    )
    for c in coduri:
        db.add(
            CodRecuperare(
                utilizator_id=utilizator.id,
                cod_hash=criptare.hmac_valoare("recuperare", totp.normalizeaza_cod_recuperare(c)),
            )
        )
    db.flush()
    jeton = _finalizeaza(db, sesiune, cheie, ip, user_agent, "totp", "autentificare.2fa_inrolata")
    return PasulUrmator(Rezultat.OK, jeton, coduri_recuperare=tuple(coduri))
