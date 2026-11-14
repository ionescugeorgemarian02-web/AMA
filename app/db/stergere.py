"""Ștergerea datelor unui client la cerere (F7.7, docs/21: dreptul la ștergere; docs/19 §19.2 „Date”).

Singura operație care lucrează ca proprietarul schemei (`AMA_DATABASE_OWNER_URL`), pentru că tabelele de
business
sunt, intenționat, doar-adăugare pentru aplicație (declanșatori care refuză ștergerea, fără drept DELETE).
De aceea:
- se cheamă doar din jobul de ștergere (`app.portal.date`), după o cerere confirmată de titular, cu audit;
- șterge DOAR rândurile cu `tenant_id = :client`, tabel cu tabel, copiii întâi (ordinea din cheile
străine), cu
  declanșatorii utilizator opriți doar în tranzacția ei (cheile străine rămân în vigoare);
- păstrează tabelele din `pastreaza` (jurnalul de audit — obligație legală — cererea de ștergere însăși și
rândul
  clientului, marcat șters și anonimizat); anonimizează utilizatorii care aparțineau doar acestui client.
Totul într-o singură tranzacție: sau se șterge tot, sau nimic."""

import uuid
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, create_engine, text

from app.config import get_settings

PASTRATE_IMPLICIT = frozenset({"jurnal_audit", "cereri_stergere", "clienti"})

TABELE = """
SELECT c.relname FROM pg_class c
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id' AND a.attnum > 0 AND NOT a.attisdropped
WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r'
"""
DEPENDENTE = """
SELECT cl.relname AS copil, pr.relname AS parinte FROM pg_constraint k
JOIN pg_class cl ON cl.oid = k.conrelid JOIN pg_class pr ON pr.oid = k.confrelid
WHERE k.contype = 'f' AND cl.relnamespace = 'public'::regnamespace AND cl.oid <> pr.oid
"""


def ordine(tabele: set[str], dependente: list[tuple[str, str]]) -> list[str]:
    """Nucleu pur: copiii înaintea părinților (sortare topologică stabilă)."""
    copii: dict[str, set[str]] = defaultdict(set)
    for copil, parinte in dependente:
        if copil in tabele and parinte in tabele:
            copii[parinte].add(copil)
    rezultat: list[str] = []
    vizitate: set[str] = set()

    def viziteaza(t: str, drum: frozenset[str]) -> None:
        if t in vizitate or t in drum:
            return
        for c in sorted(copii[t]):
            viziteaza(c, drum | {t})
        vizitate.add(t)
        rezultat.append(t)

    for t in sorted(tabele):
        viziteaza(t, frozenset())
    return rezultat


def sterge_client(tenant_id: uuid.UUID, *, pastreaza: frozenset[str] = PASTRATE_IMPLICIT) -> dict[str, int]:
    """Șterge datele clientului; întoarce numărul de rânduri pe tabel."""
    motor = create_engine(get_settings().database_owner_url, pool_pre_ping=True)
    sterse: dict[str, int] = {}
    try:
        with motor.begin() as c:
            # contextul de agenție pentru citiri (politicile forțate se aplică și proprietarului)
            c.execute(text("SELECT set_config('app.agency', '1', true)"))
            tabele = {r[0] for r in c.execute(text(TABELE))} - pastreaza
            dep = [(r[0], r[1]) for r in c.execute(text(DEPENDENTE))]
            sql = text("SELECT utilizator_id FROM apartenente WHERE tenant_id = :t")
            utilizatori = [r[0] for r in c.execute(sql, {"t": tenant_id})]
            for t in ordine(tabele, dep):
                with _deschis(c, t):
                    n = c.execute(text(f'DELETE FROM "{t}" WHERE tenant_id = :t'), {"t": tenant_id}).rowcount  # noqa: S608
                if n:
                    sterse[t] = n
            with _deschis(c, "utilizatori"), _deschis(c, "sesiuni"), _deschis(c, "clienti"):
                _anonimizeaza(c, tenant_id, utilizatori)
    finally:
        motor.dispose()
    return sterse


@contextmanager
def _deschis(c: Connection, tabel: str) -> Iterator[None]:
    """Doar în tranzacția ștergerii: proprietarul ocolește politicile și declanșatorii utilizator ai
    tabelului."""
    c.execute(text(f'ALTER TABLE "{tabel}" NO FORCE ROW LEVEL SECURITY'))
    c.execute(text(f'ALTER TABLE "{tabel}" DISABLE TRIGGER USER'))
    yield
    c.execute(text(f'ALTER TABLE "{tabel}" ENABLE TRIGGER USER'))
    c.execute(text(f'ALTER TABLE "{tabel}" FORCE ROW LEVEL SECURITY'))


def _anonimizeaza(c: Connection, tenant_id: uuid.UUID, utilizatori: list[uuid.UUID]) -> None:
    """Utilizatorii care nu mai aparțin niciunui client: fără email, nume, parolă, 2FA, sesiuni."""
    for uid in utilizatori:
        ramase = c.execute(text("SELECT count(*) FROM apartenente WHERE utilizator_id = :u"), {"u": uid})
        if ramase.scalar_one() == 0:
            c.execute(
                text(
                    "UPDATE utilizatori SET email = 'sters-' || id || '@sters.invalid', nume_afisat = "
                    "'Utilizator șters', parola_hash = 'sters', totp_activ = false, totp_secret_enc = NULL "
                    "WHERE id = :u"
                ),
                {"u": uid},
            )
            c.execute(text("DELETE FROM sesiuni WHERE utilizator_id = :u"), {"u": uid})
    c.execute(
        text("UPDATE clienti SET nume = 'Client șters', sters_la = coalesce(sters_la, now()) WHERE id = :t"),
        {"t": tenant_id},
    )
