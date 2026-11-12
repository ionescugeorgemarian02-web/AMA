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
    definitii_cozi,
    flux,
    inchide_client,
    nume_flux,
    pas,
    reincercari_pas,
    stare_flux,
    timp_maxim_flux,
    trimite,
)
from app.operare.motor.inspectie import (
    AdancimeCoada,
    DetaliiJob,
    JobNereluabil,
    PasJob,
    adancime_cozi,
    anuleaza_job,
    detalii_job,
    joburi_esuate,
    joburi_in_lucru,
    joburi_pentru,
    opreste_si_reia,
    pasi_job,
    reia_job,
    ultimul_progres,
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
    "AdancimeCoada",
    "ArgumentNepermis",
    "Coada",
    "DefinitieCoada",
    "DetaliiJob",
    "EroareAutentificare",
    "EroareDefinitiva",
    "EroareMotor",
    "EroareTemporara",
    "InfoProgramare",
    "JobNereluabil",
    "MotorOprit",
    "PasJob",
    "Prioritate",
    "Programare",
    "ProgramareInvalida",
    "Slot",
    "StareFlux",
    "StareJob",
    "adancime_cozi",
    "anuleaza_job",
    "anuleaza_slot",
    "aplica_programari",
    "asteapta_flux",
    "calculeaza_prioritate",
    "coada_furnizor",
    "coada_platforma",
    "declanseaza_acum",
    "declara_coada",
    "definitii_cozi",
    "detalii_job",
    "flux",
    "inchide_client",
    "joburi_esuate",
    "joburi_in_lucru",
    "joburi_pentru",
    "lista_programari",
    "migreaza_sistem",
    "nume_flux",
    "opreste",
    "opreste_si_reia",
    "pas",
    "pasi_job",
    "porneste",
    "pornit",
    "programari_declarate",
    "programeaza_recurent",
    "programeaza_slot",
    "pune_pe_pauza",
    "recupereaza_ratate",
    "reia_job",
    "reia_programarea",
    "reincercari_pas",
    "sloturi_viitoare",
    "stare_flux",
    "sterge_programarea",
    "timp_maxim_flux",
    "trimite",
    "uita_declaratiile",
    "ultimul_progres",
    "verifica_argumente",
]
