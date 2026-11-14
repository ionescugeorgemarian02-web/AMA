"""Validarea unui text care nu e (încă) un livrabil (F7.9, F7.10): pagina de captare a agenției, un articol
de blog.

Aceeași cascadă și aceeași agregare ca la livrabile (`cascada.evalueaza`), pe clientul dat (faptele lui
aprobate,
regulile lui), fără a salva o rulare. `coduri` restrânge la validatorii ceruți (de exemplu G2, G3, G9).
Pașii care
cer vectori prin gateway și judecătorii (V3 / V4) nu rulează aici: se omit și se spun în rezultat."""

import datetime as dt
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.ids import new_id
from app.validare import cascada, registru
from app.validare.agregare import Decizie
from app.validare.intrare import Continut, Intrare, SituatieLivrabil


@dataclass(frozen=True)
class RezultatIndependent:
    evaluare: cascada.Evaluare
    rulate: tuple[str, ...]
    omise: tuple[str, ...]

    @property
    def trece(self) -> bool:
        return self.evaluare.agregat.decizie is Decizie.TRECE and not self.evaluare.agregat.cere_om

    def blocante(self) -> list[dict[str, Any]]:
        return [
            {
                "validator": v.validator,
                "instructiune": v.instructiune,
                "dovezi": [d.fragment for d in v.dovezi],
            }
            for v in self.evaluare.agregat.blocante
        ]

    def verdicte(self) -> list[dict[str, str]]:
        return [
            {"validator": v.validator, "treapta": v.treapta.value, "rezultat": v.rezultat.value}
            for v in self.evaluare.verdicte
        ]


def evalueaza_text(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    tip: str,
    canal: str,
    text: str,
    campuri: dict[str, Any] | None = None,
    coduri: Iterable[str] | None = None,
    model_autor: str | None = None,
) -> RezultatIndependent:
    cerute = set(coduri) if coduri is not None else None
    pasi, omise = [], []
    for p in registru.pasi_pentru(tip, canal):
        d = p.definitie
        if cerute is not None and d.cod not in cerute:
            continue
        if d.foloseste_vectori:
            omise.append(f"{d.cod}@{d.treapta.value}")
            continue
        pasi.append(p)
    intrare = Intrare(
        livrabil=SituatieLivrabil(
            id=new_id(), tenant_id=tenant_id, tip=tip, canal=canal, versiune=1, runda=0
        ),
        continut=Continut(
            versiune=1, text=text, campuri=dict(campuri or {}), autor="independent", model_autor=model_autor
        ),
        la=dt.datetime.now(dt.UTC),
        db=db,
    )
    ev = cascada.evalueaza(pasi, intrare, prag=get_settings().validare_prag_avertismente)
    return RezultatIndependent(
        ev, tuple(sorted({f"{p.definitie.cod}@{p.definitie.treapta.value}" for p in pasi})), tuple(omise)
    )
