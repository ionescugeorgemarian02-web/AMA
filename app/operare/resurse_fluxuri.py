"""Ticul de resurse (F15.1, docs/25 §25.3): la 5 minute, discul și memoria, cu curățare și alertă."""

import datetime as dt
from typing import Any

from app.operare import motor, resurse
from app.operare.motor import Coada

NUME = "operare.resurse"


@motor.pas(nume="operare.resurse_pas")
def _verifica() -> str:
    r = resurse.verifica()
    inregistreaza_urma(r)
    return f"disc {r['disc_pct']:.0f}% memorie {r['memorie_pct']:.0f}% sterse {r['sterse']}"


def inregistreaza_urma(r: dict[str, Any]) -> None:
    """Urma ticului (F15.6): lista de go-live citește din urme limitele și backup-ul verde, pe zile."""
    from app.operare import backup, urme

    peste = float(r["disc_pct"]) >= resurse.PRAG_DISC or float(r["memorie_pct"]) >= resurse.PRAG_MEMORIE
    urme.emite(
        "resurse", "verifica", rezultat="esec" if peste else "ok", cod="peste_limita" if peste else "",
        iesiri={"disc_pct": round(float(r["disc_pct"]), 1), "memorie_pct": round(float(r["memorie_pct"]), 1),
                "backup_bun": backup.citeste_stare().bun},
    )  # fmt: skip


@motor.flux(NUME)
def tic_resurse(moment: dt.datetime, context: dict[str, Any] | None) -> str:
    return _verifica()


def declara_programari() -> None:
    motor.programeaza_recurent(NUME, "*/5 * * * *", tic_resurse, coada=Coada.URGENT)


declara_programari()
