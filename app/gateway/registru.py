"""Registrul de furnizori și modele (8.1): citire, activare / dezactivare, cheile.

Decizia despre chei (F3.1): în bază stă doar NUMELE variabilei de mediu (`AMA_CHEIE_*`), nu cheia, nici
criptată.
Motive: 8.1 și 21.2 cer ca cheile de modele să stea în fișierele de mediu ale serverului; o copie de
siguranță a
bazei nu trebuie să poată scurge chei de furnizori; rotația (reamintire la 90 de zile) înseamnă schimbarea
unui
fișier de mediu, nu a unui rând; iar baza refuză orice nume în afara prefixului `AMA_CHEIE_` (gateway-ul nu
poate fi
îndreptat spre `AMA_MASTER_KEY` sau spre parola bazei). Valoarea cheii se citește numai în `citeste_cheie`,
folosită
de client; nu ajunge în jurnale, audit, erori sau HTML (în panou apare doar „configurată / lipsește”).
"""

import datetime as dt
import os
import re
import uuid
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.gateway.candidat import Candidat, din_randuri
from app.gateway.erori import NuSePoateActiva
from app.gateway.modele import Furnizor, ModelLlm, ProfilSarcina
from app.gateway.profiluri import Profil
from app.operare import audit

NUME_VARIABILA = re.compile(r"^AMA_CHEIE_[A-Z0-9_]{1,40}$")
MOTIV_MAXIM = 300


def furnizori(db: Session) -> list[Furnizor]:
    return list(db.execute(select(Furnizor).order_by(Furnizor.cod)).scalars())


def furnizor(db: Session, id_sau_cod: uuid.UUID | str) -> Furnizor | None:
    if isinstance(id_sau_cod, uuid.UUID):
        return db.get(Furnizor, id_sau_cod)
    return db.execute(select(Furnizor).where(Furnizor.cod == id_sau_cod)).scalar_one_or_none()


def modele(db: Session, *, furnizor_id: uuid.UUID | None = None) -> list[ModelLlm]:
    q = select(ModelLlm).order_by(ModelLlm.furnizor_id, ModelLlm.nivel, ModelLlm.identificator)
    if furnizor_id is not None:
        q = q.where(ModelLlm.furnizor_id == furnizor_id)
    return list(db.execute(q).scalars())


def candidati(db: Session) -> list[Candidat]:
    """Toate modelele din registru, ca date înghețate pentru rutare și limitatoare."""
    f = {x.id: x for x in db.execute(select(Furnizor)).scalars()}
    return [din_randuri(f[m.furnizor_id], m) for m in db.execute(select(ModelLlm)).scalars()]


def candidat(db: Session, model_id: uuid.UUID) -> Candidat | None:
    m = db.get(ModelLlm, model_id)
    if m is None:
        return None
    f = db.get(Furnizor, m.furnizor_id)
    return None if f is None else din_randuri(f, m)


def profil(db: Session, nume: str) -> Profil | None:
    p = db.get(ProfilSarcina, nume)
    if p is None:
        return None
    return Profil(
        nume=p.nume,
        eticheta=p.eticheta,
        descriere=p.descriere,
        nivel_min=p.nivel_min,
        capabilitati=frozenset(p.capabilitati or ()),
        lant=tuple(p.lant),
        la_epuizare=p.la_epuizare,
        lant_degradare=tuple(p.lant_degradare or ()),
        verificare_in_plus=p.verificare_in_plus,
    )


def nume_profiluri(db: Session) -> list[str]:
    return list(db.execute(select(ProfilSarcina.nume).order_by(ProfilSarcina.nume)).scalars())


def citeste_cheie_env(nume_variabila: str) -> str | None:
    """Valoarea cheii dintr-o variabilă `AMA_CHEIE_*`; orice alt nume e refuzat (nu se citește mediul la
    întâmplare)."""
    if not NUME_VARIABILA.match(nume_variabila):
        return None
    valoare = os.environ.get(nume_variabila, "").strip()
    return valoare or None


def citeste_cheie(f: Furnizor) -> str | None:
    """Valoarea cheii din mediu, sau `None` dacă lipsește. DOAR pentru client: nu se loghează, nu se "
    "afișează."""
    return citeste_cheie_env(f.cheie_env)


def cheie_configurata(f: Furnizor) -> bool:
    """Serverul local nu cere cheie (rețea internă); ceilalți furnizori, da."""
    return f.tip_api == "local" or citeste_cheie(f) is not None


def poate_fi_activat(f: Furnizor) -> str | None:
    """Motivul pentru care furnizorul NU poate fi activat, sau `None` dacă poate (8.1)."""
    if f.uz_comercial is not True:
        return (
            "Uzul comercial nu este confirmat: un furnizor fără uz comercial permis nu poate fi activat "
            "pentru producția clienților."
            if f.uz_comercial is False
            else "Uzul comercial nu este verificat încă: confirmă termenii furnizorului în inventar."
        )
    if not cheie_configurata(f):
        return f"Cheia lipsește: setează variabila {f.cheie_env} în mediul serverului, apoi activează."
    return None


def activeaza(db: Session, id_furnizor: uuid.UUID, *, utilizator_id: uuid.UUID | None) -> Furnizor:
    f = db.get(Furnizor, id_furnizor)
    if f is None:
        raise LookupError("furnizor necunoscut")
    motiv = poate_fi_activat(f)
    if motiv:
        audit.record(
            db, "gateway.furnizor_activare_refuzata", obiect_tip="furnizor", obiect_id=f.cod,
            rezultat="refuzat", utilizator_id=utilizator_id, tenant_id=None, detalii={"furnizor": f.cod},
        )  # fmt: skip
        raise NuSePoateActiva(motiv)
    return _schimba(db, f, "activ", "", utilizator_id)


def dezactiveaza(
    db: Session, id_furnizor: uuid.UUID, *, motiv: str = "", utilizator_id: uuid.UUID | None
) -> Furnizor:
    f = db.get(Furnizor, id_furnizor)
    if f is None:
        raise LookupError("furnizor necunoscut")
    return _schimba(db, f, "inactiv", motiv, utilizator_id)


def _schimba(db: Session, f: Furnizor, stare: str, motiv: str, utilizator_id: uuid.UUID | None) -> Furnizor:
    anterior = f.stare
    f.stare, f.stare_motiv = stare, motiv.strip()[:MOTIV_MAXIM]
    f.actualizat_la = func.now()
    if stare == "activ":  # o activare de om ridică și întrerupătorul
        f.erori_consecutive, f.intrerupt_pana_la = 0, None
    db.flush()
    audit.record(
        db, "gateway.furnizor_activat" if stare == "activ" else "gateway.furnizor_dezactivat",
        obiect_tip="furnizor", obiect_id=f.cod, utilizator_id=utilizator_id, tenant_id=None,
        detalii={"furnizor": f.cod, "din": anterior, "in": stare, "motiv": f.stare_motiv},
    )  # fmt: skip
    return f


# --- editare de către proprietar (F3.10): limite și termeni, cu audit


class RegistruInvalid(ValueError):
    """Valoare nepermisă la editarea registrului (limită negativă, termeni care contrazic starea
    furnizorului)."""


CAMPURI_LIMITE = ("cereri_minut", "cereri_zi", "tokeni_minut", "tokeni_zi")
MARCAJE = ("V", "S", "I")


def _nume_audit(camp: str) -> str:
    """Auditul refuză cheile cu „token” (le ia drept secrete): tokenii apar ca „jetoane”."""
    return camp.replace("tokeni", "jetoane")


def _intreg_optional(nume: str, valoare: object, maxim: int = 10**12) -> int | None:
    if valoare is None or str(valoare).strip() == "":
        return None
    try:
        n = int(str(valoare).strip().replace(".", "").replace(" ", ""))
    except ValueError:
        raise RegistruInvalid(f"{nume}: nu e un număr întreg") from None
    if not 1 <= n <= maxim:
        raise RegistruInvalid(f"{nume}: trebuie să fie un număr pozitiv (gol = fără limită)")
    return n


def seteaza_limite(
    db: Session,
    tip: Literal["furnizor", "model"],
    obiect_id: uuid.UUID,
    valori: dict[str, Any],
    *,
    reset_zi_ora: object = None,
    utilizator_id: uuid.UUID | None,
) -> None:
    """Schimbă limitele unui furnizor (comune contului) sau ale unui model: cereri / tokeni pe minut și pe
    zi (gol = fără limită) și, la furnizor, ora UTC de resetare a zilei. Cu audit. Se aplică de la
    următorul apel."""
    obiect: Furnizor | ModelLlm | None = (
        db.get(Furnizor, obiect_id) if tip == "furnizor" else db.get(ModelLlm, obiect_id)
    )
    if obiect is None:
        raise LookupError(f"{tip} necunoscut")
    nou = {k: _intreg_optional(k, valori.get(k)) for k in CAMPURI_LIMITE if k in valori}
    inainte = {k: getattr(obiect, k) for k in nou}
    ora: int | None = None
    if tip == "furnizor" and reset_zi_ora not in (None, ""):
        try:
            ora = int(str(reset_zi_ora))
        except ValueError:
            raise RegistruInvalid("reset_zi_ora: nu e un număr") from None
        if not 0 <= ora <= 23:
            raise RegistruInvalid("reset_zi_ora: ora UTC trebuie să fie între 0 și 23")
    for k, v in nou.items():
        setattr(obiect, k, v)
    if ora is not None and isinstance(obiect, Furnizor):
        obiect.reset_zi_ora = ora
    obiect.actualizat_la = func.now()
    db.flush()
    cod = obiect.cod if isinstance(obiect, Furnizor) else f"{obiect.furnizor_id}/{obiect.identificator}"
    audit.record(
        db, "gateway.limite_setate", obiect_tip=tip, obiect_id=cod,
        utilizator_id=utilizator_id, tenant_id=None,
        detalii={
            "inainte": {_nume_audit(k): v for k, v in inainte.items()},
            "dupa": {_nume_audit(k): v for k, v in nou.items()},
            "reset_zi_ora": ora,
        },
    )  # fmt: skip


def seteaza_termeni(
    db: Session,
    furnizor_id: uuid.UUID,
    *,
    uz_comercial: bool | None,
    antrenare_pe_date: bool | None,
    restrictii_regionale: str,
    marcaj: str,
    verificat_la: dt.date | None,
    utilizator_id: uuid.UUID | None,
) -> Furnizor:
    """Termenii de folosire ai unui furnizor (8.1), așa cum i-a confirmat proprietarul. Un furnizor ACTIV
    nu poate primi `uz_comercial` diferit de „da” (întâi se dezactivează); marcajul `V` cere data
    verificării. Cu audit."""
    f = db.get(Furnizor, furnizor_id)
    if f is None:
        raise LookupError("furnizor necunoscut")
    if marcaj not in MARCAJE:
        raise RegistruInvalid("marcaj necunoscut (V, S sau I)")
    if marcaj == "V" and verificat_la is None:
        raise RegistruInvalid("marcajul „verificat” cere data verificării")
    if f.stare == "activ" and uz_comercial is not True:
        raise RegistruInvalid(
            "furnizorul este activ: dezactivează-l înainte să-i retragi confirmarea uzului comercial"
        )
    inainte = {"uz_comercial": f.uz_comercial, "antrenare_pe_date": f.antrenare_pe_date, "marcaj": f.marcaj}
    f.uz_comercial, f.antrenare_pe_date = uz_comercial, antrenare_pe_date
    f.restrictii_regionale = restrictii_regionale.strip()[:500]
    f.marcaj, f.verificat_la = marcaj, verificat_la
    f.actualizat_la = func.now()
    db.flush()
    audit.record(
        db, "gateway.termeni_setati", obiect_tip="furnizor", obiect_id=f.cod, utilizator_id=utilizator_id,
        tenant_id=None,
        detalii={
            "inainte": inainte,
            "dupa": {"uz_comercial": uz_comercial, "antrenare_pe_date": antrenare_pe_date, "marcaj": marcaj},
        },
    )  # fmt: skip
    return f
