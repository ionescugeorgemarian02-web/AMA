"""Stările livrabilului și tabelul de tranziții (7.2, 7.3). Nucleu pur: fără bază de date și fără HTTP.

Tabelul este DATE (`TABEL`), nu `if`-uri împrăștiate: orice pereche (din, în) absentă din el este refuzată.
Migrarea `0007` copiază perechile în funcția SQL `ama_livrabil_tranzitie_permisa` (declanșatorul din bază);
un test compară cele două tabele, deci nu pot diverge pe tăcute.
"""

from enum import StrEnum


class Stare(StrEnum):
    # cele 16 stări normale (7.2)
    PLANIFICAT = "planificat"
    BRIEFAT = "briefat"
    IN_SCRIERE = "in_scriere"
    IN_VALIDARE = "in_validare"
    IN_REPARATIE = "in_reparatie"
    VALIDAT = "validat"
    ASTEAPTA_APROBARE = "asteapta_aprobare"
    APROBAT = "aprobat"
    IN_RANDARE = "in_randare"
    CONTROL_MEDIA = "control_media"
    GATA = "gata"
    PROGRAMAT = "programat"
    IN_PUBLICARE = "in_publicare"
    PUBLICAT = "publicat"
    IN_MASURARE = "in_masurare"
    INCHIS = "inchis"
    # stările de excepție
    RESPINS = "respins"  # de om, cu motiv
    CARANTINA = "carantina"  # blocat de un validator critic
    ESEC_TEMPORAR = "esec_temporar"  # se reîncearcă
    COADA_DE_ERORI = "coada_de_erori"  # cere intervenție umană
    ANULAT = "anulat"
    EXPIRAT = "expirat"  # slotul a trecut fără aprobare


S = Stare

NORMALE = (
    S.PLANIFICAT,
    S.BRIEFAT,
    S.IN_SCRIERE,
    S.IN_VALIDARE,
    S.IN_REPARATIE,
    S.VALIDAT,
    S.ASTEAPTA_APROBARE,
    S.APROBAT,
    S.IN_RANDARE,
    S.CONTROL_MEDIA,
    S.GATA,
    S.PROGRAMAT,
    S.IN_PUBLICARE,
    S.PUBLICAT,
    S.IN_MASURARE,
    S.INCHIS,
)
EXCEPTII = (S.RESPINS, S.CARANTINA, S.ESEC_TEMPORAR, S.COADA_DE_ERORI, S.ANULAT, S.EXPIRAT)

ETICHETE: dict[Stare, str] = {
    S.PLANIFICAT: "Planificat",
    S.BRIEFAT: "Briefat",
    S.IN_SCRIERE: "În scriere",
    S.IN_VALIDARE: "În validare",
    S.IN_REPARATIE: "În reparație",
    S.VALIDAT: "Validat",
    S.ASTEAPTA_APROBARE: "Așteaptă aprobare",
    S.APROBAT: "Aprobat",
    S.IN_RANDARE: "În randare",
    S.CONTROL_MEDIA: "Control media",
    S.GATA: "Gata",
    S.PROGRAMAT: "Programat",
    S.IN_PUBLICARE: "În publicare",
    S.PUBLICAT: "Publicat",
    S.IN_MASURARE: "În măsurare",
    S.INCHIS: "Închis",
    S.RESPINS: "Respins",
    S.CARANTINA: "Carantină",
    S.ESEC_TEMPORAR: "Eșec temporar",
    S.COADA_DE_ERORI: "Coada de erori",
    S.ANULAT: "Anulat",
    S.EXPIRAT: "Expirat",
}

# Stările în care o componentă lucrează efectiv: intrarea în ele este o „predare” (7.3, cel mult 12).
STARI_DE_LUCRU = frozenset({S.IN_SCRIERE, S.IN_VALIDARE, S.IN_REPARATIE, S.IN_RANDARE, S.CONTROL_MEDIA})

# Din aceste stări se iese doar printr-o decizie de om (7.3: „merge la om”; carantina cere un om).
DOAR_OM = frozenset({S.CARANTINA, S.COADA_DE_ERORI})

# Din aceste stări se revine doar unde era livrabilul (`stare_anterioara`), sau se anulează / se escaladează.
REVENIRE = frozenset({S.ESEC_TEMPORAR, S.COADA_DE_ERORI})

_REVENIRI_POSIBILE = frozenset(
    {
        S.BRIEFAT,
        S.IN_SCRIERE,
        S.IN_VALIDARE,
        S.IN_REPARATIE,
        S.VALIDAT,
        S.APROBAT,
        S.IN_RANDARE,
        S.CONTROL_MEDIA,
        S.GATA,
        S.PROGRAMAT,
        S.IN_PUBLICARE,
        S.PUBLICAT,
        S.IN_MASURARE,
    }
)

TABEL: dict[Stare, frozenset[Stare]] = {
    S.PLANIFICAT: frozenset({S.BRIEFAT, S.ANULAT}),
    S.BRIEFAT: frozenset({S.IN_SCRIERE, S.COADA_DE_ERORI, S.ANULAT}),
    S.IN_SCRIERE: frozenset({S.IN_VALIDARE, S.ESEC_TEMPORAR, S.COADA_DE_ERORI, S.ANULAT}),
    S.IN_VALIDARE: frozenset(
        {S.VALIDAT, S.IN_REPARATIE, S.CARANTINA, S.ESEC_TEMPORAR, S.COADA_DE_ERORI, S.ANULAT}
    ),
    S.IN_REPARATIE: frozenset({S.IN_VALIDARE, S.ESEC_TEMPORAR, S.COADA_DE_ERORI, S.ANULAT}),
    S.VALIDAT: frozenset({S.ASTEAPTA_APROBARE, S.APROBAT, S.EXPIRAT, S.COADA_DE_ERORI, S.ANULAT}),
    # editarea pe loc din biroul de aprobări (F5.9): versiunea nouă se validează din nou (doar un om o cere)
    S.ASTEAPTA_APROBARE: frozenset({S.APROBAT, S.RESPINS, S.EXPIRAT, S.ANULAT, S.IN_VALIDARE}),
    S.APROBAT: frozenset({S.IN_RANDARE, S.PROGRAMAT, S.COADA_DE_ERORI, S.ANULAT}),
    S.IN_RANDARE: frozenset({S.CONTROL_MEDIA, S.ESEC_TEMPORAR, S.COADA_DE_ERORI, S.ANULAT}),
    S.CONTROL_MEDIA: frozenset(
        {S.GATA, S.IN_RANDARE, S.CARANTINA, S.ESEC_TEMPORAR, S.COADA_DE_ERORI, S.ANULAT}
    ),
    S.GATA: frozenset({S.PROGRAMAT, S.COADA_DE_ERORI, S.ANULAT}),
    S.PROGRAMAT: frozenset({S.IN_PUBLICARE, S.COADA_DE_ERORI, S.ANULAT}),
    # fără ANULAT: un efect aflat în trimitere nu se „anulează”; se verifică la platformă (F2.5)
    S.IN_PUBLICARE: frozenset({S.PUBLICAT, S.ESEC_TEMPORAR, S.COADA_DE_ERORI}),
    S.PUBLICAT: frozenset({S.IN_MASURARE, S.COADA_DE_ERORI}),
    S.IN_MASURARE: frozenset({S.INCHIS, S.COADA_DE_ERORI}),
    S.INCHIS: frozenset(),
    S.RESPINS: frozenset(),
    S.CARANTINA: frozenset({S.IN_REPARATIE, S.IN_VALIDARE, S.COADA_DE_ERORI, S.ANULAT}),
    S.ESEC_TEMPORAR: frozenset(
        {S.IN_SCRIERE, S.IN_VALIDARE, S.IN_REPARATIE, S.IN_RANDARE, S.CONTROL_MEDIA, S.IN_PUBLICARE}
        | {S.COADA_DE_ERORI, S.ANULAT}
    ),
    S.COADA_DE_ERORI: _REVENIRI_POSIBILE | {S.ANULAT},
    S.ANULAT: frozenset(),
    S.EXPIRAT: frozenset({S.PLANIFICAT, S.ANULAT}),  # „expiră și se reprogramează” (7.3)
}

STARI_FINALE = frozenset(s for s, urmatoare in TABEL.items() if not urmatoare)


def este_permisa(din: Stare, la: Stare) -> bool:
    """Perechea (din, în) apare în tabel? (Regula de revenire se verifică separat, în `motiv_refuz`.)"""
    return la in TABEL[din]


def perechi() -> list[tuple[str, str]]:
    """Perechile permise, ca text, în ordine stabilă (pentru migrare și pentru comparația cu baza)."""
    return sorted((d.value, la.value) for d, urmatoare in TABEL.items() for la in urmatoare)


def motiv_refuz(din: Stare, la: Stare, anterioara: Stare | None = None) -> str | None:
    """`None` dacă mutarea e permisă; altfel motivul refuzului (în română, fără date de client).

    Peste tabel, o regulă: din `esec_temporar` și `coada_de_erori` se revine doar în starea de dinainte
    (`anterioara`), sau se anulează, sau (din eșec temporar) se escaladează în coada de erori."""
    if din == la:
        return f"livrabilul este deja în starea „{ETICHETE[din]}”"
    if not este_permisa(din, la):
        return f"din „{ETICHETE[din]}” nu se poate trece în „{ETICHETE[la]}”"
    if din in REVENIRE and la not in (S.ANULAT, S.COADA_DE_ERORI) and la != anterioara:
        unde = ETICHETE[anterioara] if anterioara else "starea de dinainte"
        return f"din „{ETICHETE[din]}” se revine doar în „{unde}” (sau se anulează)"
    return None
