"""Stările unui efect extern și tranzițiile lor, ca DATE (F2.5). Nucleu pur: fără bază și fără HTTP.

Migrarea `0011` copiază perechile în declanșatorul `ama_efect_garda`; un test le compară.
"""

from enum import StrEnum

from app.operare.opriri import Oprire


class Stare(StrEnum):
    IN_ASTEPTARE = "in_asteptare"  # cerut, nu a plecat (sau a fost oprit / pus pe pauză și așteaptă)
    IN_TRIMITERE = "in_trimitere"  # o încercare a început; dacă procesul moare aici, rezultatul e NECUNOSCUT
    TRIMIS = "trimis"  # există la platformă; are id extern
    ESUAT_TEMPORAR = "esuat_temporar"  # ultima încercare a pierdut; urmează altă încercare (după `verifica`)
    ESUAT_DEFINITIV = "esuat_definitiv"  # refuzat sau încercări epuizate; cere un om
    ANULAT = "anulat"  # nu mai este valabil (versiune schimbată, stare nepotrivită, anulat de om)


S = Stare

ETICHETE: dict[Stare, str] = {
    S.IN_ASTEPTARE: "În așteptare",
    S.IN_TRIMITERE: "În trimitere",
    S.TRIMIS: "Trimis",
    S.ESUAT_TEMPORAR: "Eșec temporar",
    S.ESUAT_DEFINITIV: "Eșuat",
    S.ANULAT: "Anulat",
}

TABEL: dict[Stare, frozenset[Stare]] = {
    S.IN_ASTEPTARE: frozenset({S.IN_TRIMITERE, S.ANULAT}),
    # înapoi în așteptare: eroare de autentificare (nu a plecat nimic, canalul e pe pauză)
    S.IN_TRIMITERE: frozenset({S.IN_ASTEPTARE, S.TRIMIS, S.ESUAT_TEMPORAR, S.ESUAT_DEFINITIV, S.ANULAT}),
    S.ESUAT_TEMPORAR: frozenset({S.IN_TRIMITERE, S.TRIMIS, S.ESUAT_DEFINITIV, S.ANULAT}),
    # un om îl reia (înapoi în așteptare); `trimis` dacă `verifica` descoperă că totuși a ajuns la platformă
    S.ESUAT_DEFINITIV: frozenset({S.IN_ASTEPTARE, S.TRIMIS, S.ANULAT}),
    S.TRIMIS: frozenset(),
    S.ANULAT: frozenset(),
}
FINALE = frozenset(s for s, urmatoare in TABEL.items() if not urmatoare)
# Stări în care rezultatul la platformă poate fi necunoscut: înainte de orice încercare se întreabă
# `verifica`.
NECUNOSCUT = frozenset({S.IN_TRIMITERE, S.ESUAT_TEMPORAR})
DESCHISE = frozenset({S.IN_ASTEPTARE, S.IN_TRIMITERE, S.ESUAT_TEMPORAR})


class Tip(StrEnum):
    PUBLICARE = "publicare"


ETICHETE_TIP: dict[Tip, str] = {Tip.PUBLICARE: "Publicare"}

# Clasa de efect → oprirea care îl ține pe loc (7.8). Extensibil: reclamele (F13) și emailul pun aici
# rândul lor.
# Oprirea pe client (`Oprire.CLIENT`) acoperă toate clasele, prin `opriri.este_oprit`.
OPRIRE_PE_TIP: dict[Tip, Oprire] = {Tip.PUBLICARE: Oprire.PUBLICARE}


def este_permisa(din: Stare, la: Stare) -> bool:
    return la in TABEL[din]


def perechi() -> list[tuple[str, str]]:
    return sorted((d.value, la.value) for d, urmatoare in TABEL.items() for la in urmatoare)


def cheia(tenant_id: object, livrabil_id: object, canal: str, versiune: int, tip: Tip | str) -> str:
    """Cheia de idempotență din 7.3: client + livrabil + canal + versiune (+ tipul efectului)."""
    tip_valoare = tip.value if isinstance(tip, Tip) else tip
    return f"{tenant_id}:{livrabil_id}:{canal}:v{versiune}:{tip_valoare}"
