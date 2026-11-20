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


def concept_zorilor(dovada: str = "", **suprascrie: Any) -> dict[str, Any]:
    """# SIMULAT: un concept bun pentru brandul fictiv (moment real, cadre cu oameni în acțiune)."""
    c: dict[str, Any] = {
        "titlu": "Prima cafea de sâmbătă",
        "moment_real": "Sâmbătă dimineața, în bucătăria de acasă, cineva deschide un pachet nou și macină boabele.",
        "tensiune": "Cafeaua din supermarket are gust de carton și nu știe de când stă pe raft.",
        "mesaj_unic": "Cafeaua proaspătă se recunoaște după data prăjirii de pe pachet.",
        "dovada": dovada,
        "de_ce_acum": "Weekendul e momentul în care oamenii prepară cafeaua pe îndelete.",
        "cadre": [
            {"subiect": "mâna clientului", "actiune": "deschide pachetul și miroase boabele",
             "context": "bucătăria de acasă, dimineața", "tip": "video", "incadrare": "prim-plan",
             "interogari": ["hands opening coffee bag", "smelling coffee beans close up"]},
            {"subiect": "boabele de cafea", "actiune": "se rostogolesc în prăjitor",
             "context": "prăjitoria din Brașov", "tip": "video", "incadrare": "detaliu", "interogari": []},
            {"subiect": "mâna baristului", "actiune": "scrie data prăjirii pe pachet",
             "context": "tejgheaua cafenelei", "tip": "foto", "incadrare": "prim-plan",
             "interogari": ["hand writing date on coffee bag", "coffee roaster label handwriting"]},
            {"subiect": "clientul", "actiune": "toarnă apă fierbinte peste cafeaua măcinată",
             "context": "bucătăria de acasă", "tip": "video", "incadrare": "plan mediu",
             "interogari": ["pour over coffee home kitchen", "pouring hot water coffee filter"]},
            {"subiect": "apelul la acțiune", "actiune": "apare adresa magazinului", "context": "",
             "tip": "text", "incadrare": "", "interogari": []},
        ],
        "material_propriu": [2],
    }  # fmt: skip
    c.update(suprascrie)
    return c


def aliasuri_fapte(p: str) -> list[str]:
    bucata = p.split("Fapte aprobate", 1)[1].split("Context aprobat", 1)[0] if "Fapte aprobate" in p else ""
    return re.findall(r"^\[(F\d+)\] ", bucata, re.M)


def idei_fals(c: CerereInregistrata) -> str:
    """Cinci concepte (variații ale celui bun), cu dovada pe primul fapt aprobat."""
    p = prompt_complet(c)
    dovada = next(iter(aliasuri_fapte(p)), "")
    n = int(m.group(1)) if (m := re.search(r"Întoarce `concepte`: (\d+)", p)) else 5
    return raspuns_json(
        concepte=[concept_zorilor(dovada, titlu=f"Prima cafea de sâmbătă {i}") for i in range(1, n + 1)]
    )


def critica_idee_fals(c: CerereInregistrata) -> str:
    """Note bune pentru fiecare concept, primul cel mai bun; varianta îmbunătățită e chiar primul."""
    p = prompt_complet(c)
    numere = [int(x) for x in re.findall(r"^Concept (\d+):", p, re.M)] or [1]
    primul = json.loads(p.split("Concept 1:\n", 1)[1].split("\n", 1)[0]) if "Concept 1:\n" in p else None
    evaluari = [
        {"nr": n, "specificitate": 5 if n == 1 else 4, "realism": 5, "relevanta": 4, "fezabilitate": 4,
         "noutate": 4, "onestitate": 5, "obiectii": ["cadrul 4 poate arăta mai aproape aburul"]}
        for n in numere
    ]  # fmt: skip
    return raspuns_json(evaluari=evaluari, nr_imbunatatit=1 if primul else None, imbunatatit=primul)


class ModelFals:
    """Un „model” care răspunde după promptul primit. `handlere[cheie]` primește cererea și întoarce JSON-ul; testele
    din fazele următoare își adaugă handlerele aici. `stricate`: câmpuri / elemente pe care modelul le strică."""

    def __init__(self) -> None:
        self.handlere: dict[str, Callable[[CerereInregistrata], str]] = {
            "Întrebarea pusă clientului": self._evalueaza,
            "Câmpurile brieful (cod": self._brief,
            # F-idee: etapa de idee rulează înaintea oricărui brief de livrabil
            "Propune concepte creative pentru livrabilul": idei_fals,
            "Critică conceptele de mai jos": critica_idee_fals,
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
