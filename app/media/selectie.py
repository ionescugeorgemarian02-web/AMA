"""Selecția materialului pe scene (F-editorial, decizia 2): pură și deterministă, fără bază și fără model.

Candidații sunt activele clientului cu licență validă și rol de scenă (`fotografie`, `filmare`,
`ilustratie`). Sigla, coperțile și exporturile nu intră niciodată în scene (sigla apare doar în semnătura
finală).

Potrivirea: cuvintele indicației vizuale a scenei și cele din `subiect` + `descriere` ale activului,
normalizate (litere mici, fără diacritice), fără cuvinte de umplutură și fără cuvintele mai scurte de 4
litere. Două cuvinte se potrivesc dacă au un prefix comun de cel puțin 4 litere care acoperă cuvântul mai
scurt, minus o terminație de cel mult 3 litere („transmisia” ↔ „transmisie”, „frânei” ↔ „frâne”). Scorul =
cuvintele indicației găsite / toate cuvintele indicației. Câștigă scorul cel mai mare; la egalitate, activul
nefolosit încă, apoi fotografia sau filmarea înaintea ilustrației, apoi (pentru un cadru cu mișcare din
conceptul ales, F-idee) filmarea înaintea fotografiei, apoi id-ul (stabil). Cadrele conceptului intră ca
indicații în plus (`CerereScena.alternative`): scorul scenei e cel mai bun dintre indicații.

O scenă `obligatorie` (o bătaie cu indicație proprie) fără potrivire rămâne „lipsă”, cu subiectul cerut. O
scenă neobligatorie (hook, apel la acțiune) fără potrivire refolosește primul activ ales în storyboard, cu
motivul scris.
"""

import unicodedata
import uuid
from dataclasses import dataclass

ROLURI_SCENA = ("fotografie", "filmare", "ilustratie")
EXCLUSE = ("logo", "coperta", "export")
PREFIX_MINIM = 4
TERMINATIE = 3

# [I] cuvinte care nu spun ce se vede (articole, prepoziții, verbe auxiliare, termeni de cadru)
_UMPLUTURA = """
acest aceasta aceste acesti acel acea acele acolo aici avem este sunt fost fiind care cand unde cum
pentru prin dintre catre langa peste sub spre dupa inainte foarte mult multi multe putin toate toti
fiecare alte altul alta niste doar chiar inca deja apoi atunci ceva cineva noastra nostru nostri
noastre vostru voastra lui lor ale dintr intr intre fara asupra impreuna cadru cadrul cadre plan
planul prim apropiat apropiata larg larga imagine imaginea imagini scena scene vizual vizuala video
clip fotografie poza filmare logo sigla grafica animata animatie
"""
UMPLUTURA = frozenset(_UMPLUTURA.split())


def normalizeaza(text: str) -> str:
    fara = unicodedata.normalize("NFKD", text.lower())
    return "".join(c if c.isalnum() else " " for c in fara if not unicodedata.combining(c))


def cuvinte(text: str) -> list[str]:
    """Cuvintele de conținut, în ordine, fără dubluri."""
    out = [c for c in normalizeaza(text).split() if len(c) >= PREFIX_MINIM and c not in UMPLUTURA]
    return list(dict.fromkeys(out))


def _prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b, strict=False):
        if x != y:
            break
        n += 1
    return n


def se_potrivesc(a: str, b: str) -> bool:
    p = _prefix(a, b)
    return p >= PREFIX_MINIM and p >= min(len(a), len(b)) - TERMINATIE


def potrivire(indicatie: str, text: str) -> tuple[float, list[str]]:
    """Scorul (0–1) și cuvintele indicației găsite în text."""
    cerute, oferite = cuvinte(indicatie), cuvinte(text)
    if not cerute:
        return 0.0, []
    gasite = [c for c in cerute if any(se_potrivesc(c, o) for o in oferite)]
    return round(len(gasite) / len(cerute), 3), gasite


@dataclass(frozen=True)
class Candidat:
    id: uuid.UUID
    rol: str | None
    categorie: str
    subiect: str = ""
    descriere: str = ""
    licenta_ok: bool = True


@dataclass(frozen=True)
class CerereScena:
    replica: str
    indicatie: str
    obligatorie: bool = True
    # F-idee: cadrul conceptului (subiect + acțiune + context, interogările de stock), ca indicații în plus;
    # scorul e cel mai bun dintre indicații, deci un cadru nu strică o potrivire care exista deja
    alternative: tuple[str, ...] = ()
    video: bool = False  # cadrul cere mișcare: la scor egal, filmarea înaintea fotografiei

    def indicatii(self) -> list[str]:
        return [x for x in (self.indicatie or self.replica, *self.alternative) if x.strip()]


@dataclass(frozen=True)
class AlegereScena:
    scena: int
    replica: str
    subiect: str
    activ_id: uuid.UUID | None
    scor: float
    motiv: str

    @property
    def lipsa(self) -> bool:
        return self.activ_id is None


def eligibili(candidati: list[Candidat]) -> list[Candidat]:
    return [
        c for c in candidati if c.licenta_ok and c.rol in ROLURI_SCENA and c.categorie in ("foto", "video")
    ]


def subiect_cerut(indicatie: str) -> str:
    return " ".join(indicatie.split())[:120]


def alege(scene: list[CerereScena], candidati: list[Candidat]) -> list[AlegereScena]:
    """Activul ales pe fiecare scenă (sau lipsa lui, cu subiectul cerut). Determinist."""
    pool = sorted(eligibili(candidati), key=lambda c: str(c.id))
    folosite: dict[uuid.UUID, int] = {}
    out: list[AlegereScena | None] = [None] * len(scene)
    amanate: list[int] = []
    for i, s in enumerate(scene):
        subiect = subiect_cerut(s.indicatie or (s.alternative[0] if s.alternative else s.replica))
        notate = []
        for c in pool:
            text = f"{c.subiect} {c.descriere}"
            scor, gasite = max((potrivire(i, text) for i in s.indicatii()), key=lambda p: p[0])
            if scor > 0:
                static = s.video and c.categorie != "video"
                notate.append(
                    (-scor, folosite.get(c.id, 0), c.rol == "ilustratie", static, str(c.id), c, gasite)
                )
        if notate:
            neg, _, _, _, _, c, gasite = min(notate, key=lambda t: t[:5])
            reutil = f"; refolosit (a {folosite[c.id] + 1}-a oară)" if c.id in folosite else ""
            folosite[c.id] = folosite.get(c.id, 0) + 1
            out[i] = AlegereScena(
                i, s.replica, subiect, c.id, -neg, f"potrivire pe {', '.join(gasite)}{reutil}"
            )
        elif s.obligatorie:
            out[i] = AlegereScena(i, s.replica, subiect, None, 0.0, f"niciun material cu „{subiect}”")
        else:
            amanate.append(i)
    primul = next((a.activ_id for a in out if a is not None and a.activ_id is not None), None)
    for i in amanate:
        s = scene[i]
        subiect = subiect_cerut(s.indicatie or s.replica)
        if primul is None:
            out[i] = AlegereScena(i, s.replica, subiect, None, 0.0, "fără material potrivit")
        else:
            out[i] = AlegereScena(
                i, s.replica, subiect, primul, 0.0, "fără indicație proprie: refolosește primul cadru"
            )
    return [a for a in out if a is not None]
