"""F1.4 — matricea de permisiuni (18.5), modul pur."""

import pytest

from app.conturi.roluri import (
    MATRICE,
    ROLURI_AGENTIE,
    ROLURI_CLIENT,
    Permisiune,
    Rol,
    are_scop_agentie,
    este_agentie,
    necesita_al_doilea_factor,
    poate,
)

P = Permisiune


def test_fiecare_rol_are_intrare_in_matrice() -> None:
    assert set(MATRICE) == set(Rol)
    assert ROLURI_AGENTIE | ROLURI_CLIENT == set(Rol)
    assert not (ROLURI_AGENTIE & ROLURI_CLIENT)


def test_proprietarul_poate_tot() -> None:
    assert all(poate(Rol.PROPRIETAR, p) for p in Permisiune)


@pytest.mark.parametrize(
    ("rol", "permisiune", "asteptat"),
    [
        (Rol.OPERATOR, P.LIVRABIL_APROBA, True),
        (Rol.OPERATOR, P.INBOX_RASPUNDE, True),
        (Rol.OPERATOR, P.UTILIZATORI_GESTIONEAZA, False),
        (Rol.OPERATOR, P.OPRIRE_FOLOSESTE, False),
        (Rol.OPERATOR, P.PLAFOANE_SETEAZA, False),
        (Rol.ANALIST, P.RAPOARTE_CITESTE, True),
        (Rol.ANALIST, P.INVATARE_CITESTE, True),
        (Rol.ANALIST, P.LIVRABIL_APROBA, False),
        (Rol.ANALIST, P.LIVRABIL_EDITEAZA, False),
        (Rol.CLIENT_TITULAR, P.CREIER_EDITEAZA, True),
        (Rol.CLIENT_TITULAR, P.PLAFOANE_SETEAZA, True),
        (Rol.CLIENT_TITULAR, P.FACTURI_VEDE, True),
        (Rol.CLIENT_TITULAR, P.UTILIZATORI_GESTIONEAZA, False),
        (Rol.CLIENT_TITULAR, P.CLIENTI_GESTIONEAZA, False),
        (Rol.CLIENT_APROBATOR, P.LIVRABIL_APROBA, True),
        (Rol.CLIENT_APROBATOR, P.COMENTARII_SCRIE, True),
        (Rol.CLIENT_APROBATOR, P.CREIER_EDITEAZA, False),
        (Rol.CLIENT_APROBATOR, P.FACTURI_VEDE, False),
        (Rol.CLIENT_VIZITATOR, P.RAPOARTE_CITESTE, True),
        (Rol.CLIENT_VIZITATOR, P.LIVRABIL_APROBA, False),
        (Rol.CLIENT_VIZITATOR, P.COMENTARII_SCRIE, False),
    ],
)
def test_matricea(rol: Rol, permisiune: Permisiune, asteptat: bool) -> None:
    assert poate(rol, permisiune) is asteptat


def test_doar_proprietarul_gestioneaza_utilizatori_si_oprirea() -> None:
    for p in (P.UTILIZATORI_GESTIONEAZA, P.OPRIRE_FOLOSESTE, P.CLIENTI_GESTIONEAZA, P.JURNAL_CITESTE):
        assert [r for r in Rol if poate(r, p)] == [Rol.PROPRIETAR]


def test_rol_necunoscut_nu_are_nimic() -> None:
    assert not any(poate("administrator", p) for p in Permisiune)
    assert not este_agentie("administrator")
    assert not are_scop_agentie("")


def test_scop_agentie_si_al_doilea_factor() -> None:
    assert [r for r in Rol if are_scop_agentie(r)] == [Rol.PROPRIETAR]
    assert all(necesita_al_doilea_factor(r) for r in ROLURI_AGENTIE)
    assert not any(necesita_al_doilea_factor(r) for r in ROLURI_CLIENT)
    assert este_agentie("operator")
