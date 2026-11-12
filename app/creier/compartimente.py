"""Compartimentele Creierului de brand (docs/10 §10.1) și nivelurile de cunoaștere (§10.2), ca DATE.

Un compartiment nou, un nivel nou sau o regulă de aprobare diferită se schimbă aici, nu în logica serviciului.
Conținutul unei intrări este un obiect JSON; fiecare compartiment își poate înregistra o schemă Pydantic
(`inregistreaza_schema`): F4.5 (profilul de brand), F4.6 (faptele și ofertele) și fazele următoare o fac la
import. Un compartiment fără schemă înregistrată primește doar verificarea generică (obiect, mărime maximă).
"""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ValidationError

CONTINUT_MAXIM_BYTI = 40_000


class Compartiment(StrEnum):
    PROFIL_BRAND = "profil_brand"
    REGISTRU_FAPTE = "registru_fapte"
    CATALOG_OFERTE = "catalog_oferte"
    IDENTITATE_VIZUALA = "identitate_vizuala"
    EXEMPLE_AUR = "exemple_aur"
    EXEMPLE_NEGATIVE = "exemple_negative"
    INSIGHT_PUBLIC = "insight_public"
    MEMORIE_PERFORMANTA = "memorie_performanta"
    PLAYBOOK = "playbook"
    CONSTRANGERI = "constrangeri"
    # Adăugate în F4 (D-005): documentul 10.1 are zece compartimente; onboardingul, harta pieței și strategia
    # au nevoie de depozitul versionat și de aprobarea lui, deci nu sunt reținute în afara Creierului.
    BRIEF = "brief"
    INSIGHT_PIATA = "insight_piata"
    STRATEGIE = "strategie"


class Nivel(StrEnum):
    """§10.2: ce ține de un client nu părăsește clientul; nișa și platforma sunt agregate anonimizate."""

    CLIENT = "client"
    NISA = "nisa"
    PLATFORMA = "platforma"


class Stare(StrEnum):
    CIORNA = "ciorna"
    PROPUS = "propus"
    APROBAT = "aprobat"
    RETRAS = "retras"


class CauzaRetragere(StrEnum):
    RETRAS = "retras"  # retras de un om după ce fusese aprobat sau propus
    RESPINS = "respins"  # propunere respinsă de om
    INLOCUITA = "inlocuita"  # o versiune mai nouă a fost aprobată
    EXPIRAT = "expirat"  # a trecut `valabil_pana_la` (F4.6)


class SursaTip(StrEnum):
    """De unde vine o intrare (§10.4: „proveniență: cine a creat-o, din ce și când”)."""

    DECLARATIE_CLIENT = "declaratie_client"  # clientul a spus-o (interviu, formular)
    DOCUMENT = "document"  # un document colectat sau încărcat (`sursa_ref` = id)
    PASAJ = "pasaj"  # un pasaj indexat (`sursa_ref` = id; detalii: document, URL, poziție)
    URL = "url"  # o adresă (`sursa_ref` = URL)
    OM = "om"  # introdusă de un om al agenției
    SISTEM = "sistem"  # produsă automat (exemple de aur, memorie de performanță)
    AGREGAT = "agregat"  # tipar anonimizat de nișă sau de platformă


SURSE_CU_REFERINTA = frozenset({SursaTip.DOCUMENT, SursaTip.PASAJ, SursaTip.URL})
SURSE_CU_AUTOR = frozenset({SursaTip.DECLARATIE_CLIENT, SursaTip.OM})


@dataclass(frozen=True)
class InfoCompartiment:
    cod: Compartiment
    nume: str
    contine: str
    cine_schimba: str
    aprobare_sistem: (
        bool  # True: intrările se pot aproba automat (`aprobat_prin='sistem'`); altfel doar de un om
    )
    niveluri: frozenset[Nivel]


_C = Nivel.CLIENT
_N = Nivel.NISA
_P = Nivel.PLATFORMA

COMPARTIMENTE: dict[Compartiment, InfoCompartiment] = {
    i.cod: i
    for i in (
        InfoCompartiment(
            Compartiment.PROFIL_BRAND,
            "Profil de brand",
            "Poziționare, public, atribute de ton cu exemple „așa da” și „așa nu”, vocabular permis și interzis",  # noqa: E501
            "Clientul aprobă fiecare schimbare",
            False,
            frozenset({_C}),
        ),
        InfoCompartiment(
            Compartiment.REGISTRU_FAPTE,
            "Registru de fapte",
            "Fapte aprobate, cu sursă și valabilitate",
            "Clientul",
            False,
            frozenset({_C}),
        ),
        InfoCompartiment(
            Compartiment.CATALOG_OFERTE,
            "Catalog de oferte",
            "Produse, pachete, prețuri, garanții, promoții cu date",
            "Clientul",
            False,
            frozenset({_C}),
        ),
        InfoCompartiment(
            Compartiment.IDENTITATE_VIZUALA,
            "Identitate vizuală",
            "Culori, fonturi, logo, zone sigure, șabloane",
            "Clientul, prin F1",
            False,
            frozenset({_C}),
        ),
        InfoCompartiment(
            Compartiment.EXEMPLE_AUR,
            "Exemple de aur",
            "Livrabile aprobate, pe tip și canal",
            "Automat, la aprobare",
            True,
            frozenset({_C}),
        ),
        InfoCompartiment(
            Compartiment.EXEMPLE_NEGATIVE,
            "Exemple negative",
            "Livrabile respinse, cu motiv",
            "Automat, la respingere",
            True,
            frozenset({_C}),
        ),
        InfoCompartiment(
            Compartiment.INSIGHT_PUBLIC,
            "Insight de public",
            "Citate reale, obiecții, întrebări frecvente",
            "C4, C5",
            True,
            frozenset({_C, _N}),
        ),
        InfoCompartiment(
            Compartiment.MEMORIE_PERFORMANTA,
            "Memorie de performanță",
            "Hook-urile, unghiurile, formatele și sloturile care au mers sau nu, cu cifre",
            "K2",
            True,
            frozenset({_C, _N}),
        ),
        InfoCompartiment(
            Compartiment.PLAYBOOK,
            "Playbook",
            "Lecții scurte, numerotate, cu contor „a ajutat” și „a dăunat”",
            "K8, cu revizuire",
            False,
            frozenset({_C, _N, _P}),
        ),
        InfoCompartiment(
            Compartiment.CONSTRANGERI,
            "Constrângeri",
            "Reguli juridice și de conformitate ale nișei și ale clientului",
            "Agenția",
            False,
            frozenset({_C, _N, _P}),
        ),
        InfoCompartiment(
            Compartiment.BRIEF,
            "Brief de onboarding",
            "Ce vinde firma, cui, la ce preț, de ce o aleg clienții, obiecții, concurenți, interdicții, ton, obiectiv",  # noqa: E501
            "Agenția, cu clientul (F4.4)",
            False,
            frozenset({_C}),
        ),
        InfoCompartiment(
            Compartiment.INSIGHT_PIATA,
            "Insight de piață",
            "Afirmațiile concurenței (oferte, prețuri, mesaje) cu sursă și brieful de insight cu trimiteri",
            "C7, C8 (F4.10)",
            True,  # afirmațiile concurenței se aprobă de sistem după verificarea citatului; brieful, de un om
            frozenset({_C}),
        ),
        InfoCompartiment(
            Compartiment.STRATEGIE,
            "Strategie",
            "Strategia pe 90 de zile: ipoteză, plan, indicator, prag, fereastră, criteriu de oprire",
            "A2 propune, omul aprobă (F4.11)",
            False,
            frozenset({_C}),
        ),
    )
}


class ContinutInvalid(ValueError):
    """Conținutul unei intrări nu respectă schema compartimentului."""


_SCHEME: dict[Compartiment, type[BaseModel]] = {}


def inregistreaza_schema(compartiment: Compartiment, schema: type[BaseModel]) -> None:
    """Schema Pydantic a conținutului unui compartiment (apelată la import de modulul care îl deține)."""
    _SCHEME[compartiment] = schema


class PoartaInchisa(ValueError):
    """Conținutul nu poate fi trimis spre aprobare sau aprobat: poarta compartimentului a găsit probleme."""

    def __init__(self, probleme: list[str]) -> None:
        super().__init__("; ".join(probleme))
        self.probleme = probleme


_POARTA: dict[Compartiment, Callable[[Any, uuid.UUID | None, dict[str, Any]], list[str]]] = {}
_RANDARE: dict[Compartiment, Callable[[dict[str, Any]], str | None]] = {}
_CERE_OM: dict[Compartiment, Callable[[dict[str, Any]], bool]] = {}


def inregistreaza_poarta(
    compartiment: Compartiment, verifica: Callable[[Any, uuid.UUID | None, dict[str, Any]], list[str]]
) -> None:
    """Poarta de aprobare a unui compartiment: `verifica(db, tenant_id, continut)` întoarce problemele
    (listă goală =
    poate trece). Se aplică ORICĂREI versiuni care devine `propus` sau `aprobat`, indiferent pe unde
    vine (serviciu,
    panou). Primește sesiunea, ca poarta să poată verifica și trimiteri către alte intrări sau surse."""
    _POARTA[compartiment] = verifica


def probleme_poarta(
    db: Any, tenant_id: uuid.UUID | None, compartiment: Compartiment, continut: dict[str, Any]
) -> list[str]:
    f = _POARTA.get(compartiment)
    return f(db, tenant_id, continut) if f else []


def inregistreaza_randare(
    compartiment: Compartiment, randeaza: Callable[[dict[str, Any]], str | None]
) -> None:
    """Cum se scrie conținutul unui compartiment în pachetul de context. Întoarce `None` pentru un
    conținut pe care
    nu îl cunoaște: atunci se folosește randarea implicită (`citire.text_intrare`)."""
    _RANDARE[compartiment] = randeaza


def randare(compartiment: Compartiment) -> Callable[[dict[str, Any]], str | None] | None:
    return _RANDARE.get(compartiment)


def inregistreaza_cere_om(compartiment: Compartiment, cere: Callable[[dict[str, Any]], bool]) -> None:
    """Într-un compartiment cu aprobare automată, anumite intrări (profilul de public, brieful de
    insight) le aprobă
    totuși doar un om: `cere(continut)` întoarce `True` pentru ele."""
    _CERE_OM[compartiment] = cere


def cere_om(compartiment: Compartiment, continut: dict[str, Any]) -> bool:
    f = _CERE_OM.get(compartiment)
    return bool(f and f(continut))


def schema(compartiment: Compartiment) -> type[BaseModel] | None:
    return _SCHEME.get(compartiment)


def valideaza_continut(compartiment: Compartiment, continut: dict[str, Any]) -> dict[str, Any]:
    """Conținutul normalizat (validat de schemă, dacă există una). Ridică `ContinutInvalid`."""
    if not isinstance(continut, dict):
        raise ContinutInvalid("conținutul trebuie să fie un obiect")
    s = _SCHEME.get(compartiment)
    if s is not None:
        try:
            continut = s.model_validate(continut).model_dump(mode="json")
        except ValidationError as exc:
            raise ContinutInvalid(str(exc.errors(include_url=False, include_input=False)[:3])) from None
    try:
        serializat = json.dumps(continut, ensure_ascii=False)
    except (TypeError, ValueError):
        raise ContinutInvalid("conținutul nu se poate serializa ca JSON") from None
    if len(serializat.encode()) > CONTINUT_MAXIM_BYTI:
        raise ContinutInvalid(f"conținutul depășește {CONTINUT_MAXIM_BYTI} de octeți")
    return continut


def text_de_cautare(continut: dict[str, Any], *, maxim: int = 4000) -> str:
    """Textul din valorile conținutului (șiruri), pentru căutarea lexicală. Determinist."""
    bucati: list[str] = []

    def parcurge(v: Any) -> None:
        if isinstance(v, str):
            bucati.append(v)
        elif isinstance(v, dict):
            for k in sorted(v):
                parcurge(v[k])
        elif isinstance(v, list | tuple):
            for x in v:
                parcurge(x)
        elif isinstance(v, int | float) and not isinstance(v, bool):
            bucati.append(str(v))

    parcurge(continut)
    return " ".join(bucati)[:maxim]
