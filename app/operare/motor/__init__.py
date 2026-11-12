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
from app.operare.motor.cozi import (
    Coada,
    DefinitieCoada,
    Prioritate,
    calculeaza_prioritate,
    coada_furnizor,
    coada_platforma,
)
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
    declara_coada,
    flux,
    inchide_client,
    nume_flux,
    pas,
    stare_flux,
    trimite,
)
from app.operare.motor.migrare import migreaza_sistem
from app.operare.motor.programare import (
    InfoProgramare,
    Programare,
    ProgramareInvalida,
    Slot,
    anuleaza_slot,
    aplica_programari,
    declanseaza_acum,
    lista_programari,
    programari_declarate,
    programeaza_recurent,
    programeaza_slot,
    pune_pe_pauza,
    recupereaza_ratate,
    reia_programarea,
    sloturi_viitoare,
    sterge_programarea,
    uita_declaratiile,
)

__all__ = [
    "ArgumentNepermis",
    "Coada",
    "DefinitieCoada",
    "EroareAutentificare",
    "EroareDefinitiva",
    "EroareMotor",
    "EroareTemporara",
    "InfoProgramare",
    "MotorOprit",
    "Prioritate",
    "Programare",
    "ProgramareInvalida",
    "Slot",
    "StareFlux",
    "StareJob",
    "anuleaza_slot",
    "aplica_programari",
    "asteapta_flux",
    "calculeaza_prioritate",
    "coada_furnizor",
    "coada_platforma",
    "declanseaza_acum",
    "declara_coada",
    "flux",
    "inchide_client",
    "lista_programari",
    "migreaza_sistem",
    "nume_flux",
    "opreste",
    "pas",
    "porneste",
    "pornit",
    "programari_declarate",
    "programeaza_recurent",
    "programeaza_slot",
    "pune_pe_pauza",
    "recupereaza_ratate",
    "reia_programarea",
    "sloturi_viitoare",
    "stare_flux",
    "sterge_programarea",
    "trimite",
    "uita_declaratiile",
    "verifica_argumente",
]
