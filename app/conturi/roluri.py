"""Roluri și permisiuni (18.5). Modul pur: fără bază de date, fără HTTP."""

from enum import StrEnum


class Rol(StrEnum):
    PROPRIETAR = "proprietar"
    OPERATOR = "operator"
    ANALIST = "analist"
    CLIENT_TITULAR = "client_titular"
    CLIENT_APROBATOR = "client_aprobator"
    CLIENT_VIZITATOR = "client_vizitator"


class Permisiune(StrEnum):
    CLIENTI_GESTIONEAZA = "clienti.gestioneaza"
    UTILIZATORI_GESTIONEAZA = "utilizatori.gestioneaza"
    OPRIRE_FOLOSESTE = "oprire.foloseste"
    PLAFOANE_SETEAZA = "plafoane.seteaza"
    JURNAL_CITESTE = "jurnal.citeste"
    LIVRABIL_CITESTE = "livrabil.citeste"
    LIVRABIL_APROBA = "livrabil.aproba"
    LIVRABIL_EDITEAZA = "livrabil.editeaza"
    COMENTARII_SCRIE = "comentarii.scrie"
    INBOX_RASPUNDE = "inbox.raspunde"
    RAPOARTE_CITESTE = "rapoarte.citeste"
    INVATARE_CITESTE = "invatare.citeste"
    CREIER_EDITEAZA = "creier.editeaza"
    FACTURI_VEDE = "facturi.vede"


ROLURI_AGENTIE = frozenset({Rol.PROPRIETAR, Rol.OPERATOR, Rol.ANALIST})
ROLURI_CLIENT = frozenset({Rol.CLIENT_TITULAR, Rol.CLIENT_APROBATOR, Rol.CLIENT_VIZITATOR})
# Doar proprietarul vede toți clienții. Operatorul vede clienții alocați (tabelul `alocari`), analistul: de decis.
ROLURI_SCOP_AGENTIE = frozenset({Rol.PROPRIETAR})

P = Permisiune
MATRICE: dict[Rol, frozenset[Permisiune]] = {
    Rol.PROPRIETAR: frozenset(Permisiune),  # „Tot”
    Rol.OPERATOR: frozenset(
        {
            P.LIVRABIL_CITESTE,
            P.LIVRABIL_APROBA,
            P.LIVRABIL_EDITEAZA,
            P.COMENTARII_SCRIE,
            P.INBOX_RASPUNDE,
            P.RAPOARTE_CITESTE,
        }
    ),
    Rol.ANALIST: frozenset({P.RAPOARTE_CITESTE, P.INVATARE_CITESTE, P.LIVRABIL_CITESTE}),
    Rol.CLIENT_TITULAR: frozenset(
        {
            P.LIVRABIL_CITESTE,
            P.LIVRABIL_APROBA,
            P.LIVRABIL_EDITEAZA,
            P.COMENTARII_SCRIE,
            P.CREIER_EDITEAZA,
            P.PLAFOANE_SETEAZA,
            P.FACTURI_VEDE,
            P.RAPOARTE_CITESTE,
        }
    ),
    Rol.CLIENT_APROBATOR: frozenset({P.LIVRABIL_CITESTE, P.LIVRABIL_APROBA, P.COMENTARII_SCRIE}),
    Rol.CLIENT_VIZITATOR: frozenset({P.RAPOARTE_CITESTE}),
}


def rol_valid(valoare: str) -> Rol | None:
    try:
        return Rol(valoare)
    except ValueError:
        return None


def poate(rol: Rol | str, permisiune: Permisiune) -> bool:
    """Refuz implicit: un rol necunoscut nu are nicio permisiune."""
    r = rol_valid(str(rol))
    return r is not None and permisiune in MATRICE[r]


def este_agentie(rol: Rol | str) -> bool:
    r = rol_valid(str(rol))
    return r is not None and r in ROLURI_AGENTIE


def are_scop_agentie(rol: Rol | str) -> bool:
    r = rol_valid(str(rol))
    return r is not None and r in ROLURI_SCOP_AGENTIE


def necesita_al_doilea_factor(rol: Rol | str) -> bool:
    """Al doilea factor este obligatoriu pentru rolurile de agenție, opțional pentru client (21.3)."""
    return este_agentie(rol)
