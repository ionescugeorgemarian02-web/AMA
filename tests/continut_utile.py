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


FARA_DIACRITICE = str.maketrans("ăâîșțĂÂÎȘȚ", "aaistAAIST")


def _subiect(p: str) -> str:
    m = re.search(r"Mesaj unic: Cafeaua noastră ajunge proaspătă: (.*?)\.\n", p)
    return m.group(1) if m else "cafeaua proaspătă"


def model_hookuri(modele: ModelFals) -> None:
    """Cinci deschideri: o cifră din afara faptelor, una slabă, o întrebare legată de subiect, una lungă și o întrebare
    scurtă (potrivită pentru video, unde hook-ul are cel mult 7 cuvinte)."""

    def handler(c: CerereInregistrata) -> str:
        s = _subiect(prompt_complet(c))
        return raspuns_json(
            hookuri=[
                {"text": "În 10 zile, totul se schimbă pentru cafeaua ta.", "tipar": "cifra"},
                {"text": "Bună ziua, azi vă spunem o poveste despre cafea.", "tipar": "poveste"},
                {"text": f"Știi ce înseamnă „{s}”?", "tipar": "intrebare"},
                {"text": "Am prăjit, am gustat, am mai prăjit o dată și abia apoi am trimis cafeaua la tine acasă, "
                 "în pachetul cu data pe el.", "tipar": "rezultat"},
                {"text": "Ce gust are cafeaua proaspătă?", "tipar": "intrebare"},
            ]
        )  # fmt: skip

    modele.handlere["Propune deschideri pentru materialul"] = handler


class AutorPostari:
    """Autorul fals de postări (E4) și de reparații. `stricate`: a câta postare (de la 1) iese fără diacritice; reparația
    o readuce corectă."""

    def __init__(self, stricate: set[int] | None = None) -> None:
        self.stricate = stricate or set()
        self.scrise = 0
        self.reparatii: list[str] = []
        self._bune: dict[str, str] = {}

    def postare(self, c: CerereInregistrata) -> str:
        p = prompt_complet(c)
        self.scrise += 1
        hook = re.search(r"Hook \(prima frază, păstrată exact\): (.*)\n", p)
        fapte = re.findall(r"^- (.*)$", p.split("Fapte permise", 1)[1], re.M) if "Fapte permise" in p else []
        fapt = next((f for f in fapte if "costă" in f or "gratuită" in f), "")
        corp = (
            "La Cafeneaua Zorilor prăjim cafeaua în loturi mici, ca să ajungă la tine proaspătă, cu data prăjirii "
            f"scrisă pe pachet. {fapt + '.' if fapt and not fapt.endswith('.') else fapt} "
            "Comandă acum din magazinul online."
        ).replace("  ", " ")
        if self.scrise in self.stricate:
            stricat = corp.translate(FARA_DIACRITICE)
            self._bune[stricat] = corp
            corp = stricat
        text = f"{hook.group(1) if hook else ''}\n\n{corp}"
        return raspuns_json(text=text, hashtaguri=["cafea", "#Brasov"])

    def repara(self, c: CerereInregistrata) -> str:
        p = prompt_complet(c)
        material = p.split("Material:\n", 1)[1].split("\n\nCorecturile cerute:", 1)[0]
        self.reparatii.append(p.split("Corecturile cerute:\n", 1)[1][:300])
        for rau, bun in self._bune.items():
            material = material.replace(rau, bun)
        return raspuns_json(text=material)


def model_postari(modele: ModelFals, stricate: set[int] | None = None) -> AutorPostari:
    a = AutorPostari(stricate)
    model_hookuri(modele)
    modele.handlere["Scrie postarea pentru"] = a.postare
    modele.handlere["Corectează materialul de mai jos"] = a.repara
    return a


BATAI = [
    "La Cafeneaua Zorilor prăjim cafeaua în loturi mici, în fiecare săptămână, chiar aici, în Brașov.",
    "Pe fiecare pachet scriem data prăjirii, ca să știi exact cât de proaspătă este cafeaua ta.",
    "{fapt} Așa știi de la început ce primești în fiecare pachet de cafea.",
    "Pachetul pleacă spre tine în aceeași săptămână, bine închis, ca boabele să rămână proaspete.",
]


class ScenaristFals:
    """E2 fals: patru bătăi de ~16 cuvinte (≈ 30 s cu hook-ul și apelul). `prea_lungi`: a câta cerere (de la 1)
    întoarce un script de două ori mai lung; `mereu_lung`: toate."""

    def __init__(self, prea_lungi: set[int] | None = None, mereu_lung: bool = False) -> None:
        self.prea_lungi = prea_lungi or set()
        self.mereu_lung = mereu_lung
        self.cereri: list[str] = []

    def __call__(self, c: CerereInregistrata) -> str:
        p = prompt_complet(c)
        self.cereri.append(p)
        fapte = re.findall(r"^- (.*)$", p.split("Fapte permise", 1)[1], re.M) if "Fapte permise" in p else []
        fapt = next((f for f in fapte if "costă" in f or "gratuită" in f), "Cafeaua e prăjită în Brașov")
        voci = [b.format(fapt=fapt.rstrip(".") + ".") for b in BATAI]
        if self.mereu_lung or len(self.cereri) in self.prea_lungi:
            voci = [v + " " + v for v in voci]
        batai = [
            {"voce": v, "text_ecran": e, "vizual": z}
            for v, e, z in zip(
                voci,
                [
                    "Prăjită în Brașov",
                    "Data prăjirii pe pachet",
                    "Prețul, pe față",
                    "Pleacă în aceeași săptămână",
                ],
                [
                    "Prăjitorul, cadru apropiat",
                    "Mâna scrie data pe pachet",
                    "Pachetul pe tejghea",
                    "Cutia închisă",
                ],
                strict=True,
            )
        ]
        return raspuns_json(batai=batai, apel_la_actiune="Comandă acum din magazinul online.")


def model_scripturi(modele: ModelFals, **kw: Any) -> ScenaristFals:
    s = ScenaristFals(**kw)
    model_hookuri(modele)
    modele.handlere["Scrie scriptul video scurt"] = s
    return s
