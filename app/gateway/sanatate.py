"""Starea de sănătate a furnizorilor în baza de date: întrerupătorul și pauza după o eroare de autentificare.

Fiecare operație este o singură instrucțiune atomică, în tranzacție proprie (sesiune de agenție): doi
workeri care
văd aceeași cădere nu își calcă pe picioare. Oglinda în Python a regulii este `intrerupator` (testată
împotriva ei).
"""

import datetime as dt
import uuid

from sqlalchemy import text

from app.config import get_settings
from app.db import sesiune_agentie
from app.gateway import ceas
from app.gateway.intrerupator import StareSanatate
from app.logging import get_logger
from app.operare import audit

log = get_logger("app.gateway")

ESEC = text(
    """
    UPDATE gateway_furnizori
       SET erori_consecutive = erori_consecutive + 1,
           ultima_eroare_la = :acum,
           intrerupt_pana_la = CASE WHEN erori_consecutive + 1 >= :prag
                                    THEN CAST(:acum AS timestamptz) + make_interval(secs => :pauza)
                                    ELSE intrerupt_pana_la END
     WHERE id = :id
 RETURNING erori_consecutive, intrerupt_pana_la
    """
)


def inregistreaza_esec(furnizor_id: uuid.UUID, *, acum: dt.datetime | None = None) -> StareSanatate:
    s = get_settings()
    with sesiune_agentie() as db:
        r = db.execute(
            ESEC,
            {
                "id": furnizor_id,
                "acum": acum or ceas.acum(),
                "prag": s.gateway_intrerupator_prag,
                "pauza": s.gateway_intrerupator_pauza_sec,
            },
        ).one()
    return StareSanatate(int(r[0]), r[1])


def inregistreaza_succes(furnizor_id: uuid.UUID, *, acum: dt.datetime | None = None) -> None:
    with sesiune_agentie() as db:
        db.execute(
            text(
                "UPDATE gateway_furnizori SET erori_consecutive = 0, intrerupt_pana_la = NULL, "
                "ultimul_succes_la = :acum WHERE id = :id"
            ),
            {"id": furnizor_id, "acum": acum or ceas.acum()},
        )


def citeste_starea(furnizor_id: uuid.UUID, acum: dt.datetime) -> StareSanatate:
    """Starea întrerupătorului acum, din bază (doi workeri pot fi în același loc); un deschis expirat nu
    se arată."""
    with sesiune_agentie() as db:
        r = db.execute(
            text("SELECT erori_consecutive, intrerupt_pana_la FROM gateway_furnizori WHERE id = :i"),
            {"i": furnizor_id},
        ).one()
    return StareSanatate(int(r[0]), r[1] if r[1] is not None and r[1] > acum else None)


def pune_pe_pauza(furnizor_id: uuid.UUID, cod: str, *, motiv: str) -> bool:
    """Eroare de autentificare (7.5): furnizorul trece pe pauză până îl activează un om, cu audit și alertă.
    Întoarce `False` dacă era deja pe pauză (alerta nu se repetă la fiecare apel concurent)."""
    with sesiune_agentie() as db:
        r = db.execute(
            text(
                "UPDATE gateway_furnizori SET stare = 'pauza', stare_motiv = :motiv, actualizat_la = now() "
                "WHERE id = :id AND stare <> 'pauza' RETURNING id"
            ),
            {"id": furnizor_id, "motiv": motiv[:300]},
        ).first()
        if r is None:
            return False
        audit.record(
            db, "gateway.furnizor_pauza", obiect_tip="furnizor", obiect_id=cod, rezultat="refuzat",
            tenant_id=None, actor_tip="sistem", detalii={"furnizor": cod, "motiv": motiv[:200]},
        )  # fmt: skip
    _alerteaza(cod)
    return True


def _alerteaza(cod: str) -> None:
    from app.operare import notificari

    try:
        notificari.notifica(
            notificari.Nivel.IMPORTANT,
            "Furnizor de modele pe pauză",
            f"{cod}: eroare de autentificare. Verifică cheia și reactivează furnizorul în Modele.",
            url="/gateway/registru",
        )
    except Exception as exc:  # o alertă care nu pleacă nu are voie să strice apelul
        log.warning("alerta de autentificare nu a plecat", extra={"tip_eroare": type(exc).__name__})
