"""Motorul de execuție: fluxuri durabile, cozi și programare peste Postgres (ADR-03, secțiunile 6.3 și 7.5).

Restul aplicației importă DOAR de aici; biblioteca de workflow-uri (`dbos`) nu se importă nicăieri altundeva
(garda `scripts/check_motor.py`). Exemplu:

    from app.operare import motor

    @motor.pas(reincercari=3)
    def descarca(tenant_id: str, sursa_id: str) -> str: ...

    @motor.flux("cercetare.sursa")
    def cerceteaza(tenant_id: str, sursa_id: str) -> str:
        return descarca(tenant_id, sursa_id)

    # în procesul web:
    job = motor.trimite(cerceteaza, str(tenant_id), str(sursa_id), cheie=f"sursa:{sursa_id}")

Fluxurile primesc doar identificatori (vezi `argumente`); pașii care ating date de client deschid sesiuni din
`app.db` (RLS rămâne în vigoare) cu `tenant_id`-ul primit.
"""

from app.operare.motor.argumente import verifica as verifica_argumente
from app.operare.motor.ciclu import opreste, porneste, pornit
from app.operare.motor.erori import (
    ArgumentNepermis,
    EroareAutentificare,
    EroareDefinitiva,
    EroareMotor,
    EroareTemporara,
    MotorOprit,
)
from app.operare.motor.executie import (
    StareFlux,
    StareJob,
    asteapta_flux,
    flux,
    inchide_client,
    nume_flux,
    pas,
    stare_flux,
    trimite,
)
from app.operare.motor.migrare import migreaza_sistem

__all__ = [
    "ArgumentNepermis",
    "EroareAutentificare",
    "EroareDefinitiva",
    "EroareMotor",
    "EroareTemporara",
    "MotorOprit",
    "StareFlux",
    "StareJob",
    "asteapta_flux",
    "flux",
    "inchide_client",
    "migreaza_sistem",
    "nume_flux",
    "opreste",
    "pas",
    "porneste",
    "pornit",
    "stare_flux",
    "trimite",
    "verifica_argumente",
]
