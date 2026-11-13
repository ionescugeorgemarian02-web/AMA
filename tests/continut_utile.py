"""# SIMULAT: modelul fals al producției de conținut (F6) pentru brandul FICTIV „Cafeneaua Zorilor”. Nicio rețea, nicio
cheie reală. Fiecare handler răspunde după o frază care apare doar în promptul lui; testele pot cere greșeli (de exemplu un
text fără diacritice) ca să dovedească validarea și reparația."""

from typing import Any

from tests.furnizor_fals import CerereInregistrata
from tests.onboarding_utile import ModelFals, raspuns_json

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
