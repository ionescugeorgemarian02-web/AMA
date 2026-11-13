"""# SIMULAT: modelul fals al producției de conținut (F6) pentru brandul FICTIV „Cafeneaua Zorilor”. Nicio rețea, nicio
cheie reală. Fiecare handler răspunde după o frază care apare doar în promptul lui; testele pot cere greșeli (de exemplu un
text fără diacritice) ca să dovedească validarea și reparația."""

import re
from typing import Any

from tests.furnizor_fals import CerereInregistrata
from tests.onboarding_utile import ModelFals, prompt_complet, raspuns_json

PILONI = [
    {
        "nume": "Cafea proaspătă",
        "descriere": "Data prăjirii și loturile mici, explicate simplu.",
        "pondere": 50,
    },
    {
        "nume": "Preparare acasă",
        "descriere": "Cum prepari cafeaua de specialitate acasă, pas cu pas.",
        "pondere": 30,
    },
    {"nume": "Comunitate", "descriere": "Degustările de sâmbătă și oamenii din cafenea.", "pondere": 20},
]
IDEI = [
    {
        "pilon": "Cafea proaspătă",
        "subiect": "Data prăjirii pe pachetul de Etiopia Guji",
        "unghi": "întrebare",
    },
    {"pilon": "Cafea proaspătă", "subiect": "De ce prăjim cafeaua în loturi mici", "unghi": "poveste"},
    {"pilon": "Cafea proaspătă", "subiect": "Livrarea cafelei proaspete acasă", "unghi": "beneficiu"},
    {
        "pilon": "Preparare acasă",
        "subiect": "Cum macini cafeaua pentru filtru",
        "unghi": "greșeală frecventă",
    },
    {
        "pilon": "Preparare acasă",
        "subiect": "Cât de fierbinte trebuie să fie apa pentru cafea",
        "unghi": "cifră",
    },
    {"pilon": "Comunitate", "subiect": "Degustarea de sâmbătă la cafenea", "unghi": "invitație"},
    {"pilon": "Comunitate", "subiect": "Baristii care prăjesc cafeaua", "unghi": "poveste"},
]


def calendar_valid(**suprascrie: Any) -> dict[str, Any]:
    c: dict[str, Any] = {
        "piloni": PILONI,
        "formate": [
            {"canal": "facebook", "tip": "postare", "pe_saptamana": 4},
            {"canal": "facebook", "tip": "script_video_scurt", "pe_saptamana": 1},
        ],
        "idei": IDEI,
    }
    c.update(suprascrie)
    return c


def model_calendar(modele: ModelFals, calendar: dict[str, Any] | None = None) -> None:
    def handler(_c: CerereInregistrata) -> str:
        return raspuns_json(calendar=calendar or calendar_valid())

    modele.handlere["Propune calendarul de conținut"] = handler


def aliasuri(prompt: str) -> list[str]:
    """Aliasurile faptelor disponibile din promptul autorului de brief."""
    bucata = prompt.split("Fapte disponibile", 1)[1].split("Context aprobat", 1)[0]
    return re.findall(r"^\[(F\d+)\] ", bucata, re.M)


def model_brief(modele: ModelFals, *, inventeaza: bool = False) -> None:
    """Brieful permite toate faptele din pachet (cel mult 3); `inventeaza=True` citează un fapt care nu există."""

    def handler(c: CerereInregistrata) -> str:
        p = prompt_complet(c)
        subiect = re.search(r"Subiect: (.*?)\. Unghi", p)
        fapte = aliasuri(p)[:3] + (["F99"] if inventeaza else [])
        return raspuns_json(
            brief={
                "scop": "Să aducem comenzi noi de cafea proaspătă din magazinul online.",
                "public": "Iubitori de cafea de 25–45 de ani din Brașov și din țară.",
                "mesaj_unic": f"Cafeaua noastră ajunge proaspătă: {subiect.group(1) if subiect else 'cafea'}.",
                "fapte_permise": fapte,
                "format": "Prima linie ca hook, corp scurt, un singur apel la acțiune.",
                "apel_la_actiune": "Comandă acum din magazinul online.",
                "interdictii": ["Fără promisiuni medicale", "Fără cuvântul „ieftin”"],
            }
        )

    modele.handlere["Scrie brieful livrabilului"] = handler
