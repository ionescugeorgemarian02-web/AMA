"""Instrumente de administrare. Primul proprietar:

    uv run python -m app.conturi.cli creeaza-proprietar --email adresa@exemplu.ro

Parola se citește de la tastatură (fără ecou) sau de la stdin când nu e terminal; niciodată din argumente.
"""

import argparse
import getpass
import sys
from collections.abc import Callable, Sequence

from app.conturi.roluri import Rol
from app.conturi.servicii import Actor, DateInvalide, creeaza_utilizator
from app.db import sesiune_agentie


def citeste_parola() -> str:
    if sys.stdin.isatty():
        prima = getpass.getpass("Parola (minimum 12 caractere): ")
        if getpass.getpass("Repetă parola: ") != prima:
            raise DateInvalide("Parolele nu coincid.")
        return prima
    return sys.stdin.readline().rstrip("\r\n")


def creeaza_proprietar(email: str, nume: str | None, parola: str) -> str:
    with sesiune_agentie() as db:
        utilizator = creeaza_utilizator(
            db,
            email=email,
            parola=parola,
            nume_afisat=nume or email,
            rol=Rol.PROPRIETAR,
            tenant_id=None,
            actor=Actor.cli(),
        )
        return str(utilizator.id)


def main(argv: Sequence[str] | None = None, parola_din: Callable[[], str] = citeste_parola) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.conturi.cli")
    sub = parser.add_subparsers(dest="comanda", required=True)
    p = sub.add_parser("creeaza-proprietar", help="creează un utilizator cu rolul proprietar")
    p.add_argument("--email", required=True)
    p.add_argument("--nume", default=None)
    args = parser.parse_args(argv)
    try:
        uid = creeaza_proprietar(args.email, args.nume, parola_din())
    except DateInvalide as exc:
        print(f"Eroare: {exc}", file=sys.stderr)
        return 1
    print(f"Proprietar creat: {uid}. La prima autentificare se cere activarea celui de-al doilea factor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
