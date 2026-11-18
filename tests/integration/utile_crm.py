"""Tabelele CRM-ului agenției, în ordinea în care se pot șterge (copiii întâi). Comune pe sesiunea de teste:
fiecare pas F12 nou își adaugă aici tabelele, ca testele mai vechi să poată curăța în continuare."""

from sqlalchemy import Engine, text

TABELE_CRM = (
    "crm_conturi_tinta",  # F12.9
    "crm_inbox_raspunsuri",  # F12.8
    "crm_inbox_mesaje", "crm_inbox_canale",  # F12.7
    "crm_oferte",  # F12.6
    "crm_programari",  # F12.5
    "crm_calificari",  # F12.4
    "crm_secvente",  # F12.3
    "crm_trimiteri", "crm_suprimari",  # F12.2
    "crm_sarcini", "crm_activitati", "crm_leaduri", "crm_consimtamant", "crm_contacte", "crm_firme",  # F12.1
)  # fmt: skip


def curata_crm(admin_engine: Engine, *, fara: tuple[str, ...] = ()) -> None:
    with admin_engine.begin() as c:
        for t in TABELE_CRM:
            if t not in fara:
                c.execute(text(f"DELETE FROM {t}"))
