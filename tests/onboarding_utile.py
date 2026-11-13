"""# SIMULAT: modelul fals al onboardingului (F4.4–F4.11) și răspunsurile de interviu ale brandului FICTIV „Cafeneaua
Zorilor”. Nicio rețea, nicio cheie reală. Modelul „citește” promptul (blocurile de date externe) și răspunde scriptat,
după o frază care apare doar în promptul respectiv; testele pot cere greșeli (citate falsificate, afirmații fără sursă)
ca să dovedească verificatorii deterministici."""

import json
import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import Engine, text

from tests.furnizor_fals import CerereInregistrata, FurnizorFals
from tests.gateway_utile import FabricaModele

PROFILURI = ("clasificare", "creatie", "strategie")
BLOC = re.compile(
    r"<<<DATE_EXTERNE sursa=(\w+) id=([a-z]{12})>>>\n(.*?)\n<<<SFARSIT_DATE_EXTERNE id=\2>>>", re.S
)

RASPUNSURI: dict[str, str] = {
    "nume": "Cafeneaua Zorilor, prăjitorie de cafea de specialitate din Brașov",
    "ce_vinde": "Cafea de specialitate în boabe (Etiopia Guji, Columbia Huila, Amestecul Zorilor), abonamente lunare "
    "și workshopuri de preparare acasă.",
    "preturi": "Pachetele de 250 g costă între 42 și 49 lei, abonamentul Lunar 89 lei pe lună, abonamentul Birou "
    "310 lei pe lună.",
    "public": "Iubitori de cafea de 25–45 de ani din Brașov și din țară, plus birouri mici care vor cafea bună la sediu.",
    "de_ce_ne_aleg": "Cafeaua ajunge proaspătă, în cel mult zece zile de la prăjire, și o schimbăm dacă nu a plăcut.",
    "obiectii": "Spun că e mai scumpă decât cafeaua din supermarket și nu știu ce cafea să aleagă pentru aparatul lor.",
    "concurenti": "Cafeneaua Brumei (brumei.exemplu.test), Prăjitoria Nordului (nordului.exemplu.test), "
    "Boabe de Munte (munte.exemplu.test)",
    "ce_a_incercat": "Am făcut reclame pe Facebook în 2024 și am avut 30 de comenzi noi într-o lună; newsletterul "
    "nu a mers.",
    "interdictii": "Fără promisiuni medicale despre cafea, fără comparații directe cu numele concurenților, fără "
    "cuvântul „ieftin”.",
    "ton": "Prietenos și simplu, fără termeni complicați, ca un barista care explică pe îndelete.",
    "obiectiv": "Să ajungem la 60 de abonamente lunare noi în 90 de zile.",
}


def blocuri(c: CerereInregistrata) -> list[tuple[str, str]]:
    mesaje = c.corp.get("messages", [])
    continut = "\n".join(m["content"] for m in mesaje if isinstance(m.get("content"), str))
    return [(m.group(1), m.group(3)) for m in BLOC.finditer(continut)]


def prompt_complet(c: CerereInregistrata) -> str:
    mesaje = c.corp.get("messages", [])
    return "\n".join(m["content"] for m in mesaje if isinstance(m.get("content"), str))


def raspuns_json(**campuri: Any) -> str:
    return json.dumps({**campuri, "dovezi": ["scriptat"], "incredere": 0.9}, ensure_ascii=False)


class ModelFals:
    """Un „model” care răspunde după promptul primit. `handlere[cheie]` primește cererea și întoarce JSON-ul; testele
    din fazele următoare își adaugă handlerele aici. `stricate`: câmpuri / elemente pe care modelul le strică."""

    def __init__(self) -> None:
        self.handlere: dict[str, Callable[[CerereInregistrata], str]] = {
            "Întrebarea pusă clientului": self._evalueaza,
            "Câmpurile brieful (cod": self._brief,
        }
        self.stricate: set[str] = set()
        self.apeluri: list[str] = []

    def __call__(self, c: CerereInregistrata) -> str:
        p = prompt_complet(c)
        for fraza, h in self.handlere.items():
            if fraza in p:
                self.apeluri.append(fraza)
                return h(c)
        raise AssertionError("prompt necunoscut modelului fals: " + p[:200])

    # --- F4.4
    def _evalueaza(self, c: CerereInregistrata) -> str:
        raspuns = blocuri(c)[0][1]
        if any(x in raspuns for x in ("Diverse", "multe lucruri", "tot felul")):
            return raspuns_json(
                suficient=False, lipseste="exemple concrete",
                intrebare="Care sunt cele două produse care se vând cel mai bine, pe nume?",
            )  # fmt: skip
        return raspuns_json(suficient=True, lipseste="", intrebare="")

    def _brief(self, c: CerereInregistrata) -> str:
        bl = blocuri(c)
        raspunsuri = list(re.finditer(r"\[R:([0-9a-f-]{36})\] \((\w+)\) (.*)", bl[0][1]))
        pasaje = {m.group(1): m.group(2) for m in re.finditer(r"\[P:([0-9a-f-]{36})\] (.*)", bl[1][1])}
        campuri = []
        for m in raspunsuri:
            rid, camp, text_ = m.group(1), m.group(2), m.group(3)
            elem: dict[str, str] = {"camp": camp, "valoare": text_, "sursa_tip": "raspuns", "sursa_ref": rid,
                                    "citat": text_[:60]}  # fmt: skip
            if camp == "ce_vinde" and pasaje:
                pid, t = next(iter(pasaje.items()))
                elem.update(sursa_tip="pasaj", sursa_ref=pid, citat=t[:50])
            if camp in self.stricate:
                elem["citat"] = "un citat inventat care nu apare nicăieri"
            campuri.append(elem)
        return raspuns_json(campuri=campuri)


@pytest.fixture
def model_fals() -> ModelFals:
    return ModelFals()


@pytest.fixture
def modele(
    fabrica_modele: FabricaModele,
    admin_engine: Engine,
    cheie_proba: str,
    fals: FurnizorFals,
    model_fals: ModelFals,
) -> Iterator[ModelFals]:
    """Profilurile `clasificare`, `creatie` și `strategie` trec pe un singur model de probă, servit de furnizorul fals."""
    fals.text = model_fals
    m = fabrica_modele.model(
        fabrica_modele.furnizor(), identificator="onboarding", nivel="T3", capabilitati=["iesire_structurata"]
    )
    originale: dict[str, Any] = {}
    with admin_engine.connect() as c:
        for p in PROFILURI:
            originale[p] = c.execute(
                text("SELECT lant FROM gateway_profiluri WHERE nume = :n"), {"n": p}
            ).scalar_one()
    with admin_engine.begin() as c:
        for p in PROFILURI:
            c.execute(text("UPDATE gateway_profiluri SET lant = :l WHERE nume = :n"), {"l": [m.cod], "n": p})
    yield model_fals
    with admin_engine.begin() as c:
        for p in PROFILURI:
            c.execute(
                text("UPDATE gateway_profiluri SET lant = :l WHERE nume = :n"),
                {"l": list(originale[p]), "n": p},
            )
        c.execute(text("DELETE FROM gateway_prompturi WHERE nume LIKE 'onboarding.%'"))
