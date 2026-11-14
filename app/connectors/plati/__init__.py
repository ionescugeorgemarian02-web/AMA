"""Conectorul procesatorului de plăți (F7.6, docs/19 §19.5): adaptor. Se cheamă DOAR din executorul de efecte.

Platforma nu vede și nu stochează date de card: creează abonamentul prin API-ul de abonamente al
procesatorului și
primește un link spre pagina lui de plată; schimbările vin înapoi prin webhook-uri semnate.

`ProcesatorSimulat` (# SIMULAT) e mediul de probă: abonamentele stau în proces, iar `plateste`,
`reinnoieste` și
`esueaza` produc webhook-urile semnate pe care le-ar trimite procesatorul real. Adaptorul real (de ales la
migrare: cont, chei, domeniul pentru webhook) se adaugă aici, ales prin `AMA_PLATI_PROCESATOR`."""

import datetime as dt
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.connectors.contract import EfectSistem, RezultatPlatforma
from app.operare.motor import EroareDefinitiva

TIP = "plata"
ANTET_SEMNATURA = "x-semnatura"


def semneaza(corp: bytes, secret: str, t: int | None = None) -> str:
    """Antetul de semnătură: `t=<secunde>,v1=<hmac-sha256 hex al lui "t.corp">`."""
    t = int(time.time()) if t is None else t
    v1 = hmac.new(secret.encode(), f"{t}.".encode() + corp, hashlib.sha256).hexdigest()
    return f"t={t},v1={v1}"


@dataclass
class AbonamentSimulat:
    id: str
    referinta: str  # abonamentul nostru
    plan: str
    suma: int
    stare: str = "incomplet"
    perioada_pana_la: dt.datetime | None = None
    idem: str = ""


@dataclass
class ProcesatorSimulat:
    """# SIMULAT: mediul de probă al procesatorului."""

    abonamente: dict[str, AbonamentSimulat] = field(default_factory=dict)
    secret: str = ""
    _nr: int = 0

    def trimite(self, efect: EfectSistem) -> RezultatPlatforma:
        p = efect.payload
        for a in self.abonamente.values():
            if a.idem == efect.idem:  # idempotent pe cheie
                return RezultatPlatforma(
                    id_extern=a.id, link=f"https://plati.example.invalid/checkout/{a.id}"
                )
        if p.get("op") == "abonament_nou":
            self._nr += 1
            a = AbonamentSimulat(
                f"sub_sim_{uuid.uuid4().hex[:12]}",
                str(p["abonament"]),
                str(p["plan"]),
                int(p["suma"]),
                idem=efect.idem,
            )
            self.abonamente[a.id] = a
            return RezultatPlatforma(id_extern=a.id, link=f"https://plati.example.invalid/checkout/{a.id}")
        if p.get("op") == "anuleaza":
            existent = self.abonamente.get(str(p.get("id_extern")))
            if existent is None:
                raise EroareDefinitiva("abonament necunoscut la procesator")
            existent.stare = "anulat"
            return RezultatPlatforma(id_extern=existent.id)
        raise EroareDefinitiva(f"operație necunoscută: {p.get('op')}")

    # --- ce face clientul / procesatorul în mediul de probă: webhook-uri semnate ---------------------------
    def _eveniment(self, tip: str, a: AbonamentSimulat, **date: Any) -> tuple[bytes, dict[str, str]]:
        corp = json.dumps(
            {
                "id": f"evt_{uuid.uuid4().hex}",
                "tip": tip,
                "abonament": a.id,
                "referinta": a.referinta,
                **date,
            },
            default=str,
        ).encode()
        return corp, {ANTET_SEMNATURA: semneaza(corp, self.secret), "content-type": "application/json"}

    def plateste(
        self, id_extern: str, *, acum: dt.datetime | None = None
    ) -> list[tuple[bytes, dict[str, str]]]:
        """Clientul plătește pe pagina procesatorului: abonamentul devine activ și prima factură e plătită."""
        a = self.abonamente[id_extern]
        acum = acum or dt.datetime.now(dt.UTC)
        a.stare, a.perioada_pana_la = "activ", acum + dt.timedelta(days=30)
        return [
            self._eveniment("abonament.activ", a, perioada_pana_la=a.perioada_pana_la.isoformat()),
            self._factura("factura.platita", a, acum, acum + dt.timedelta(days=30)),
        ]

    def _factura(
        self, tip: str, a: AbonamentSimulat, de_la: dt.datetime, pana_la: dt.datetime
    ) -> tuple[bytes, dict[str, str]]:
        return self._eveniment(
            tip,
            a,
            factura=f"in_sim_{uuid.uuid4().hex[:10]}",
            suma=a.suma,
            moneda="RON",
            perioada_de_la=de_la.isoformat(),
            perioada_pana_la=pana_la.isoformat(),
        )

    def reinnoieste(self, id_extern: str, *, reusita: bool) -> tuple[bytes, dict[str, str]]:
        """Reînnoirea automată la sfârșitul perioadei: factura plătită sau eșuată."""
        a = self.abonamente[id_extern]
        de_la = a.perioada_pana_la or dt.datetime.now(dt.UTC)
        if reusita:
            a.perioada_pana_la = de_la + dt.timedelta(days=30)
            return self._factura("factura.platita", a, de_la, a.perioada_pana_la)
        a.stare = "restant"
        return self._factura("factura.esuata", a, de_la, de_la + dt.timedelta(days=30))


PROCESATOR = ProcesatorSimulat()
