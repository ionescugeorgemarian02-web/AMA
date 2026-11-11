"""Ajutor pentru migrări: politica standard de izolare pe client (21.1).

Un tabel nou cu date de client se face așa, într-o migrare:

    op.create_table("exemplu", sa.Column("id", ...), sa.Column("tenant_id", ..., sa.ForeignKey("clienti.id")), ...)
    activeaza_rls_tenant(op.execute, "exemplu")

Meta-testul din `tests/isolation/test_meta_rls.py` pică dacă un tabel cu `tenant_id` nu are RLS.
"""

import re
from collections.abc import Callable

NUME_SIGUR = re.compile(r"^[a-z][a-z0-9_]*$")

# Clientul curent sau scopul de agenție. Subinterogările fac ca funcțiile să se evalueze o singură dată.
CONDITIE_TENANT = "(tenant_id = (SELECT ama_tenant_id()) OR (SELECT ama_agency()))"


def _nume(valoare: str) -> str:
    if not NUME_SIGUR.match(valoare):
        raise ValueError(f"nume SQL nesigur: {valoare!r}")
    return valoare


def activeaza_rls_tenant(
    executa: Callable[[str], object],
    tabel: str,
    *,
    drepturi: str = "SELECT, INSERT, UPDATE",
    politica: str = "izolare_tenant",
    conditie: str = CONDITIE_TENANT,
) -> None:
    """Activează și forțează RLS, creează politica pe `tenant_id` și dă drepturile minime lui `ama_app`."""
    t = _nume(tabel)
    executa(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
    executa(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
    executa(f"CREATE POLICY {_nume(politica)} ON {t} USING {conditie} WITH CHECK {conditie}")
    for drept in drepturi.split(","):
        if drept.strip() not in {"SELECT", "INSERT", "UPDATE", "DELETE"}:
            raise ValueError(f"drept nepermis: {drept!r}")
    executa(f"GRANT {drepturi} ON {t} TO ama_app")


def activeaza_rls(executa: Callable[[str], object], tabel: str) -> None:
    """Doar ENABLE + FORCE (pentru tabele cu politici proprii, scrise de mână în migrare)."""
    t = _nume(tabel)
    executa(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
    executa(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
