"""Nivelurile de autonomie (7.4, ADR-12), nucleu pur: fără bază de date, fără configurare citită.

Nivelul se setează pe client și pe cinci clase de acțiuni. Funcția `cere_aprobare` răspunde la o singură
întrebare: pentru acest livrabil, la acest nivel, cere platforma aprobarea unui om? Răspunsul este:
- `umbra` (L0): livrabilul se produce, dar nu se publică și nu se aprobă nimic;
- `aprobare`: un om decide;
- `automat`: trece singur (peste prag și verificări).

Eșantionul de la L2 / L3 (livrabilele care merg totuși la om) este DETERMINIST: se decide din identificatorul
livrabilului și clasa lui, nu dintr-un zar. Același livrabil primește același răspuns la fiecare apel
(testabil, reproductibil, auditabil), iar ponderea pe termen lung este cea configurată.
"""

import hashlib
import uuid
from collections.abc import Collection
from enum import IntEnum, StrEnum


class Nivel(IntEnum):
    L0 = 0  # Umbră: produce, nu publică
    L1 = 1  # Aprobare totală (implicit)
    L2 = 2  # Aprobare prin excepție
    L3 = 3  # Autonom cu plafon
    L4 = 4  # Autonom în perimetru


NIVEL_IMPLICIT = Nivel.L1
ETICHETE_NIVEL: dict[Nivel, str] = {
    Nivel.L0: "L0 Umbră",
    Nivel.L1: "L1 Aprobare totală",
    Nivel.L2: "L2 Aprobare prin excepție",
    Nivel.L3: "L3 Autonom cu plafon",
    Nivel.L4: "L4 Autonom în perimetru",
}


class Clasa(StrEnum):
    """Cele cinci clase de acțiuni (7.4)."""

    PUBLICARE_CONTINUT = "publicare_continut"
    RASPUNS_INBOX = "raspuns_inbox"
    SCHIMBARE_RECLAME = "schimbare_reclame"
    SCHIMBARE_STRATEGIE = "schimbare_strategie"
    CHELTUIALA = "cheltuiala"


ETICHETE_CLASA: dict[Clasa, str] = {
    Clasa.PUBLICARE_CONTINUT: "Publicare de conținut",
    Clasa.RASPUNS_INBOX: "Răspuns în inbox",
    Clasa.SCHIMBARE_RECLAME: "Schimbare de reclame",
    Clasa.SCHIMBARE_STRATEGIE: "Schimbare de strategie",
    Clasa.CHELTUIALA: "Cheltuială",
}


class Decizie(StrEnum):
    UMBRA = "umbra"
    APROBARE = "aprobare"
    AUTOMAT = "automat"

    @property
    def cere_aprobare(self) -> bool:
        return self is Decizie.APROBARE


class _Regim(StrEnum):
    UMBRA = "U"
    APROBARE = "A"
    ESANTION_L2 = "E2"  # automat, cu eșantionul L2 (10–20%) la om
    ESANTION_L3 = "E3"  # automat, cu eșantionul L3 (5–10%) la om
    AUTOMAT = "T"


U, A, E2, E3, T = (
    _Regim.UMBRA,
    _Regim.APROBARE,
    _Regim.ESANTION_L2,
    _Regim.ESANTION_L3,
    _Regim.AUTOMAT,
)

# Matricea 7.4, ca DATE: pentru fiecare clasă, regimul la L0, L1, L2, L3, L4.
# - publicare de conținut: singură de la L2 (ce trece verificările, cu eșantion); răspunsurile în inbox și
#   ajustările de reclame de la L3 („în plus”); strategia doar la L4 („în perimetrul contractului”);
# - cheltuiala: de la L3, doar în plafoanele din contract (parametrul `in_limite`); deciziile de buget
#   rămân la om (7.4, L4).
REGIM: dict[Clasa, tuple[_Regim, _Regim, _Regim, _Regim, _Regim]] = {
    Clasa.PUBLICARE_CONTINUT: (U, A, E2, E3, E3),
    Clasa.RASPUNS_INBOX: (U, A, A, E3, E3),
    Clasa.SCHIMBARE_RECLAME: (U, A, A, E3, E3),
    Clasa.SCHIMBARE_STRATEGIE: (U, A, A, A, T),
    Clasa.CHELTUIALA: (U, A, A, E3, E3),
}

RATA_L2_IMPLICITA = 0.15  # mijlocul intervalului 10–20%
RATA_L3_IMPLICITA = 0.075  # mijlocul intervalului 5–10%
CANALE_CONSIMTAMANT_IMPLICITE: frozenset[str] = frozenset({"tiktok"})


def esantionat(livrabil_id: uuid.UUID, clasa: Clasa, rata: float) -> bool:
    """Livrabilul face parte din eșantionul care merge la om? Determinist: doar (clasă, livrabil, rată).
    Rata 0 nu alege niciodată; rata 1 alege mereu."""
    if not 0.0 <= rata <= 1.0:
        raise ValueError("rata eșantionului trebuie să fie între 0 și 1")
    if rata <= 0.0:
        return False
    if rata >= 1.0:
        return True
    rest = hashlib.sha256(f"{clasa.value}:{livrabil_id}".encode()).digest()
    return int.from_bytes(rest[:8], "big") / 2**64 < rata


def nivel_efectiv(nivel: Nivel, canal: str | None, canale_consimtamant: Collection[str]) -> Nivel:
    """Canalele cu consimțământ per postare (TikTok, 7.4) rămân la cel mult L1, oricare ar fi nivelul."""
    if canal is not None and canal.lower() in {c.lower() for c in canale_consimtamant}:
        return min(nivel, Nivel.L1)
    return nivel


def cere_aprobare(
    nivel: Nivel,
    clasa: Clasa,
    livrabil_id: uuid.UUID,
    *,
    canal: str | None = None,
    canale_consimtamant: Collection[str] = CANALE_CONSIMTAMANT_IMPLICITE,
    rata_l2: float = RATA_L2_IMPLICITA,
    rata_l3: float = RATA_L3_IMPLICITA,
    verificari_ok: bool = True,
    in_limite: bool = True,
) -> Decizie:
    """Cere platforma aprobarea unui om pentru acest livrabil?

    - `verificari_ok`: a trecut toate verificările peste prag (la L2+ doar ce trece merge singur);
    - `in_limite`: acțiunea e în plafoanele / perimetrul aprobat (cheltuiala, strategia);
    - `canale_consimtamant`: canalele rămase la L1 (date, nu cod).
    """
    efectiv = nivel_efectiv(nivel, canal, canale_consimtamant)
    regim = REGIM[clasa][efectiv]
    if regim is _Regim.UMBRA:
        return Decizie.UMBRA
    if regim is _Regim.APROBARE or not verificari_ok or not in_limite:
        return Decizie.APROBARE
    if regim is _Regim.AUTOMAT:
        return Decizie.AUTOMAT
    rata = rata_l2 if regim is _Regim.ESANTION_L2 else rata_l3
    return Decizie.APROBARE if esantionat(livrabil_id, clasa, rata) else Decizie.AUTOMAT


def retrogradat(nivel: Nivel) -> Nivel:
    """Cu un nivel mai jos (incident critic, 7.4); L0 e podeaua."""
    return Nivel(max(Nivel.L0, nivel - 1))
