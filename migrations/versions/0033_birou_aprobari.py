"""Biroul de aprobări: editarea pe loc readuce livrabilul în validare (F5.9, docs/18 §18.3)

Revizia: 0033
Anterioara: 0032

Perechea `asteapta_aprobare → in_validare` intră în funcția de tranziții permise a bazei (aceeași listă ca
`app/productie/stari.py`): versiunea editată de un om în biroul de aprobări trece din nou prin cascadă; nicio
aprobare
pe o versiune nevalidată.
"""

import importlib.util
from pathlib import Path

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def _perechi(cu_editare: bool) -> str:
    cale = Path(__file__).with_name("0007_livrabile.py")
    spec = importlib.util.spec_from_file_location("migrarea_0007", cale)
    if spec is None or spec.loader is None:
        raise RuntimeError("migrarea 0007 lipsește")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    perechi = [(d, la) for d, ls in m.PERECHI.items() for la in ls]
    if cu_editare:
        perechi.append(("asteapta_aprobare", "in_validare"))
    return ", ".join(f"('{d}', '{la}')" for d, la in perechi)


def _functie(cu_editare: bool) -> None:
    op.execute(
        f"""CREATE OR REPLACE FUNCTION ama_livrabil_tranzitie_permisa(din text, la text) RETURNS boolean
            LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT (din, la) IN (VALUES {_perechi(cu_editare)}) $$"""
    )


def upgrade() -> None:
    _functie(True)


def downgrade() -> None:
    _functie(False)
