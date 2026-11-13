"""Bucla de validare și reparație, integrată cu mașina de stări (7.2–7.3).

    in_validare ──ruleaza_runda──▶ validat                      (cu aprobare de om dacă avertismentele trec
    pragul)
                               ├─▶ in_reparatie ──ruleaza_repararea──▶ in_validare   (cel mult 2 runde)
                               └─▶ carantina                    (eșec critic: decide un om)

Limita de 2 runde NU este dublată aici: intrarea într-a treia reparație o refuză `productie.muta`, care
trimite
livrabilul în coada de erori cu diagnostic (F2.4); aici doar se raportează (`RezultatRunda.escaladat`).
Toate mutările au temeiul în starea din bază: o rundă reluată după o cădere găsește livrabilul unde l-a
lăsat.
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app import gateway, productie
from app.config import get_settings
from app.logging import get_logger
from app.operare import evenimente
from app.productie import Stare
from app.validare import autor as autori
from app.validare import cascada, continut, depozit, registru
from app.validare.agregare import Decizie
from app.validare.intrare import Intrare, SituatieLivrabil
from app.validare.verdict import Verdict

log = get_logger("app.validare")
COMPONENTA = "validare"


class NuSeValideaza(RuntimeError):
    """Livrabilul nu e în `în validare`."""


@dataclass(frozen=True)
class RezultatRunda:
    decizie: Decizie
    stare: Stare  # starea livrabilului după rundă (poate diferi de cea dorită dacă o limită l-a trimis la om)
    rulare_id: uuid.UUID
    instructiune: str
    cere_om: bool
    escaladat: str | None
    verdicte: tuple[Verdict, ...]


def situatie(livrabil: productie.Livrabil) -> SituatieLivrabil:
    return SituatieLivrabil(
        id=livrabil.id,
        tenant_id=livrabil.tenant_id,
        tip=livrabil.tip,
        canal=livrabil.canal,
        versiune=livrabil.versiune,
        runda=livrabil.runde_reparatie,
        clasa_actiune=livrabil.clasa_actiune,
    )


def intrare_pentru(
    db: Session,
    livrabil: productie.Livrabil,
    *,
    la: dt.datetime | None = None,
    judecatori: bool | None = None,
    v4: bool | None = None,
) -> Intrare:
    """Intrarea cascadei pentru versiunea CURENTĂ (conținutul ei; `FaraContinut` dacă lipsește)."""
    s = get_settings()
    return Intrare(
        livrabil=situatie(livrabil),
        continut=continut.citeste(db, livrabil.id, livrabil.versiune),
        la=la or livrabil.termen_la or gateway.acum(),
        db=db,
        judecatori=s.validare_judecatori if judecatori is None else judecatori,
        v4=s.validare_v4 if v4 is None else v4,
    )


def ruleaza_runda(
    db: Session,
    livrabil_id: uuid.UUID,
    *,
    utilizator_id: uuid.UUID | None = None,
    la: dt.datetime | None = None,
    judecatori: bool | None = None,
    v4: bool | None = None,
) -> RezultatRunda:
    """O trecere a cascadei peste versiunea curentă a unui livrabil `în validare`: salvează rularea și
    verdictele,
    apoi mută livrabilul după decizia agregată. `gateway.Amanat` (un judecător amânat) iese neprins: nu s-a
    salvat și
    nu s-a mutat nimic, apelantul reprogramează."""
    livrabil = productie.blocheaza(db, livrabil_id)
    stare = Stare(livrabil.stare)
    if stare is not Stare.IN_VALIDARE:
        raise NuSeValideaza(f"livrabilul e în „{productie.ETICHETE[stare]}”, nu în „În validare”")
    intrare = intrare_pentru(db, livrabil, la=la, judecatori=judecatori, v4=v4)
    pasi = registru.pasi_pentru(livrabil.tip, livrabil.canal, judecatori=intrare.judecatori, v4=intrare.v4)
    evaluare = cascada.evalueaza(pasi, intrare, prag=get_settings().validare_prag_avertismente)
    ag = evaluare.agregat
    rulare = depozit.salveaza(
        db,
        tenant_id=livrabil.tenant_id,
        livrabil_id=livrabil.id,
        versiune=livrabil.versiune,
        runda=livrabil.runde_reparatie,
        continut=intrare.continut,
        verdicte=list(evaluare.verdicte),
        agregat=ag,
        oprit_la=evaluare.oprit_la,
    )
    evenimente.emite(
        db,
        "validare.rulare",
        sursa="validare",
        obiect_tip="livrabil",
        obiect_id=livrabil.id,
        tenant_id=livrabil.tenant_id,
        utilizator_id=utilizator_id,
        date={
            "decizie": ag.decizie.value,
            "versiune": livrabil.versiune,
            "runda": livrabil.runde_reparatie,
            "verdicte": len(evaluare.verdicte),
            "puncte": ag.puncte,
        },
    )
    detalii: dict[str, Any] = {
        "rulare": str(rulare.id),
        "validatori": sorted({v.validator for v in ag.blocante}),
        "instructiune": ag.instructiune,
    }
    escaladat = None
    if ag.decizie is Decizie.TRECE:
        r = productie.muta(
            db, livrabil.id, Stare.IN_VALIDARE, Stare.VALIDAT, componenta=COMPONENTA,
            motiv="a trecut cascada de validare", utilizator_id=utilizator_id, versiune=livrabil.versiune,
            detalii={"rulare": str(rulare.id), "puncte": ag.puncte},
        )  # fmt: skip
        stare_noua = r.stare
        if ag.cere_om:
            stare_noua = _cere_om(db, livrabil.id, ag.puncte, ag.prag, utilizator_id) or stare_noua
    elif ag.decizie is Decizie.CARANTINA:
        r = productie.muta(
            db, livrabil.id, Stare.IN_VALIDARE, Stare.CARANTINA, componenta=COMPONENTA,
            motiv="eșec critic al unui validator", utilizator_id=utilizator_id, detalii=detalii,
        )  # fmt: skip
        stare_noua = r.stare
    else:  # REPARATIE
        r = productie.muta(
            db, livrabil.id, Stare.IN_VALIDARE, Stare.IN_REPARATIE, componenta=COMPONENTA,
            motiv="blocat de " + ", ".join(detalii["validatori"]),
            utilizator_id=utilizator_id, detalii=detalii,
        )  # fmt: skip
        stare_noua = r.stare
        escaladat = r.escaladat
    return RezultatRunda(
        decizie=ag.decizie,
        stare=stare_noua,
        rulare_id=rulare.id,
        instructiune=ag.instructiune,
        cere_om=ag.cere_om,
        escaladat=escaladat,
        verdicte=evaluare.verdicte,
    )


def _cere_om(
    db: Session, livrabil_id: uuid.UUID, puncte: int, prag: int, utilizator_id: uuid.UUID | None
) -> Stare | None:
    """Avertismentele au trecut pragul: livrabilul merge la om, oricare ar fi nivelul de autonomie. La
    nivelul L0
    (umbră) nu se cere aprobare (livrabilul se produce, dar nu merge mai departe): rămâne `validat`."""
    try:
        productie.aprobari.cere(db, livrabil_id, utilizator_id=utilizator_id, componenta=COMPONENTA)
    except (
        productie.aprobari.NuSeCereAprobare,
        productie.aprobari.NivelUmbra,
        productie.aprobari.TermenTrecut,
    ) as exc:
        log.info(
            "aprobarea cerută de validare nu s-a putut deschide", extra={"tip_eroare": type(exc).__name__}
        )
        return None
    return Stare.ASTEAPTA_APROBARE


def ruleaza_repararea(db: Session, livrabil_id: uuid.UUID) -> str:
    """Cheamă autorul înregistrat cu instrucțiunea unificată, scrie versiunea nouă a conținutului și mută
    livrabilul
    înapoi în `în validare`. Întoarce starea de după: `in_validare`; `fara_autor` (niciun autor înregistrat:
    livrabilul
    așteaptă în reparație, F6 înregistrează autorii) sau starea în care e livrabilul dacă nu e în
    reparație."""
    livrabil = productie.blocheaza(db, livrabil_id)
    stare = Stare(livrabil.stare)
    if stare is not Stare.IN_REPARATIE:
        return stare.value
    f = autori.curent()
    if f is None:
        return "fara_autor"
    ultima = depozit.ultima_rulare(db, livrabil.id)
    sarcina = autori.SarcinaReparatie(
        livrabil_id=livrabil.id,
        tenant_id=livrabil.tenant_id,
        tip=livrabil.tip,
        canal=livrabil.canal,
        versiune=livrabil.versiune,
        runda=livrabil.runde_reparatie,
        continut=continut.citeste(db, livrabil.id, livrabil.versiune),
        instructiune=ultima.instructiune if ultima else "",
    )
    nou = f(db, sarcina)
    continut.scrie(
        db, livrabil.id, text=nou.text, campuri=nou.campuri, active=nou.active, autor=nou.autor,
        model_autor=nou.model_autor,
    )  # fmt: skip
    productie.muta(
        db, livrabil.id, Stare.IN_REPARATIE, Stare.IN_VALIDARE, componenta=nou.autor[:60],
        motiv=f"reparația {livrabil.runde_reparatie}: conținut corectat",
    )  # fmt: skip
    return Stare.IN_VALIDARE.value
