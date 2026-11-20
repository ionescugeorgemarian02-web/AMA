"""Două dosare de intrare fictive pentru pilot. Răspunsuri ale clientului și documente brute."""

from dataclasses import dataclass

from tests import materiale_zorilor
from tests.onboarding_utile import RASPUNSURI


@dataclass(frozen=True)
class Dosar:
    marca: str
    raspunsuri: dict[str, str]
    recenzii: list[str]
    concurenti: dict[str, list[str]]
    produs: str
    pret: str
    unitate: str


MAGAZIN = Dosar(
    "Cafeneaua Zorilor",
    {
        **RASPUNSURI,
        "preturi": "Etiopia Guji, pachet de 250 g, costă 49 lei.",
        "obiectiv": "Dorim 60 de comenzi de Etiopia Guji din magazinul online în 90 de zile; promovăm pe Facebook.",
    },
    materiale_zorilor.RECENZII,
    materiale_zorilor.CONCURENTI,
    "Etiopia Guji",
    "49",
    "250 g",
)

ATELIER = Dosar(
    "Atelierul Spița",
    {
        "nume": "Atelierul Spița, atelier de biciclete din Sibiu.",
        "ce_vinde": "Revizie Urbană, o verificare a frânelor și a transmisiei pentru biciclete de oraș.",
        "preturi": "Revizia Urbană costă 120 lei pentru o bicicletă.",
        "public": "Navetiști din Sibiu care folosesc bicicleta în fiecare zi.",
        "de_ce_ne_aleg": "Explicăm devizul înainte de intervenție și acceptăm programări prin formular.",
        "obiectii": "Cicliștii se tem de costuri suplimentare și de reparații greu de înțeles.",
        "concurenti": "Roata Albastră, Lanțul Verde și Pedala Lină sunt alte ateliere locale.",
        "ce_a_incercat": "Am comunicat pe Facebook despre pregătirea bicicletelor pentru primăvară.",
        "interdictii": "Evităm promisiunile de siguranță garantată și reducerile de preț.",
        "ton": "Calm și practic, explicăm operațiunile în cuvinte obișnuite.",
        "obiectiv": "Dorim 30 de programări confirmate pentru Revizia Urbană în 90 de zile prin formular, folosind Facebook.",
    },
    [
        "Pot aduce bicicleta înainte de a pleca la birou?",
        "Aș vrea să știu dinainte ce verificări sunt incluse în revizie.",
        "Îmi place să primesc devizul înainte să schimbați piesele.",
        "Pot alege din formular ziua în care aduc bicicleta?",
        "Frâna mea din spate scârțâie după ce merg prin ploaie.",
        "Am nevoie de bicicletă pentru drumul de dimineață spre serviciu.",
        "Nu știu cum să descriu zgomotul care vine de la lanț.",
        "Mi-a fost de folos explicația despre uzura saboților.",
        "Am preferat programarea din formular, fără să telefonez.",
        "M-ar ajuta să văd într-o fotografie ce piesă trebuie schimbată.",
        "Sunt curios cât durează verificarea transmisiei pe bicicleta mea.",
        "Pot refuza o piesă nouă dacă depășește bugetul meu?",
        "Am primit o explicație clară despre ce înseamnă o revizie.",
        "Aș dori să aduc două biciclete de oraș în aceeași dimineață.",
        "Mi-am cumpărat bicicleta la mâna a doua și vreau să o verific.",
        "Frâna din față prinde mai slab decât luna trecută.",
        "Prefer să îmi spuneți din vreme dacă bicicleta rămâne peste noapte.",
        "Am ales atelierul pentru că era aproape de traseul meu zilnic.",
        "Nu știam cum să verific singur dacă lanțul este uzat.",
        "Pot să programez bicicleta partenerei mele prin același formular?",
        "M-am bucurat că mi-ați explicat diferența dintre reglaj și înlocuire.",
        "Pot să aduc bicicleta dacă are și un scaun pentru copil?",
        "Vreau să știu ce costuri presupun piesele înainte de intervenție.",
        "Folosesc bicicleta tot anul și aș vrea să verific transmisia.",
    ],
    {
        "Roata Albastră": [
            "Reglăm frânele bicicletelor de oraș.",
            "Primim bicicletele pe bază de programare.",
            "Verificarea transmisiei costă 60 lei.",
        ],
        "Lanțul Verde": [
            "Oferim reglaje pentru biciclete pliabile.",
            "Realizăm revizii pentru navetiști.",
            "Înlocuirea cablului se face la cerere.",
        ],
        "Pedala Lină": [
            "Preluăm programări prin telefon.",
            "Oferim o fișă după verificarea bicicletei.",
            "Verificăm schimbătoarele înainte de predare.",
        ],
    },
    "Revizia Urbană",
    "120",
    "bicicletă",
)

CAZURI = {"magazin": MAGAZIN, "servicii": ATELIER}
