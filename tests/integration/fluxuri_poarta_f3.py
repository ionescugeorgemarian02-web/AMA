"""# SIMULAT: fluxul de probă al porții F3. Un apel la gateway pe un profil; cum reacționează un flux real la ce întoarce gateway-ul:
- `ApelRefuzat("local_doar_pe_coada_greu")`: își mută pasul pe coada `greu` (modelul local se apelează doar de acolo);
- `Amanat`: se reprogramează prin motor pentru momentul cerut (nu eșuează, nu doarme);
- altfel înregistrează rezultatul. Rezultatele se țin în memorie (executorul rulează în procesul testului)."""

import datetime as dt
import threading
import uuid

from app import gateway
from app.db import sesiune_tenant
from app.operare import motor
from app.operare.motor import Coada, Prioritate
from tests.gateway_utile import Clasificare

REZULTATE: list[tuple[str, str, str]] = []  # (scenariu, profil, rezultat final)
ETAPE: list[tuple[str, str, str]] = []  # mutări pe `greu` și amânări
_lock = threading.Lock()


def reseteaza() -> None:
    with _lock:
        REZULTATE.clear()
        ETAPE.clear()


@motor.pas(nume="poarta_f3.pas")
def _apel(tenant: str, prompt: str, accepta: bool) -> str:
    t = uuid.UUID(tenant)
    try:
        with sesiune_tenant(t) as db:
            r = gateway.apeleaza(
                db, prompt=prompt, variabile={"text": "Livrarea a fost rapidă!"}, schema=Clasificare, tenant_id=t,
                componenta="poarta.f3", prioritate=Prioritate.P2, accepta_provizoriu=accepta,
            )  # fmt: skip
    except gateway.Amanat as amanat:
        return f"amanat:{amanat.pana_la.isoformat()}"
    except gateway.ApelRefuzat as exc:
        return f"refuzat:{exc.cod}"
    return f"ok:{r.model}:degradat={int(r.degradat)}:provizoriu={int(r.provizoriu)}:verificare={int(r.verificare_suplimentara)}"


@motor.flux("poarta_f3.flux")
def flux(tenant: str, prompt: str, profil: str, scenariu: str, accepta: bool, pe_greu: bool) -> str:
    rezultat = _apel(tenant, prompt, accepta)
    cheie = f"pf3:{scenariu}:{profil}"
    if rezultat == "refuzat:local_doar_pe_coada_greu" and not pe_greu:
        with _lock:
            ETAPE.append((scenariu, profil, "mutat_pe_greu"))
        motor.trimite(
            flux, tenant, prompt, profil, scenariu, accepta, True, coada=Coada.GREU, prioritate=Prioritate.P2,
            cheie=cheie + ":greu",
        )  # fmt: skip
        return rezultat
    if rezultat.startswith("amanat:"):
        amanat = gateway.Amanat(dt.datetime.fromisoformat(rezultat.split(":", 1)[1]), "cotă sau furnizor")
        gateway.reprogrameaza(
            amanat, flux, tenant, prompt, profil, scenariu, accepta, pe_greu, cheie=cheie + ":amanat",
            coada=Coada.GREU if pe_greu else Coada.IO,
        )  # fmt: skip
        with _lock:
            ETAPE.append((scenariu, profil, "reprogramat"))
        rezultat = "amanat"
    with _lock:
        REZULTATE.append((scenariu, profil, rezultat))
    return rezultat
