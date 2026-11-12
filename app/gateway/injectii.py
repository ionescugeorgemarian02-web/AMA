"""Detecția euristică a tentativelor de injecție (G13, 12.8): un SEMNAL, nu o blocare.

Tiparele sunt date (tabelul `TIPARE`), în română și engleză. O potrivire nu oprește apelul — textul oricum
a intrat marcat ca date —, ci lasă un semnal în jurnalul de apeluri și în jurnalul aplicației, ca un om să
vadă sursa. Euristica NU prinde orice atac (rescrieri, limbi străine, codificări); apărarea reală este
marcarea, schema și lipsa uneltelor.
"""

import re
import unicodedata
from dataclasses import dataclass

TIPARE: tuple[tuple[str, str], ...] = (
    (
        "ignora_instructiuni",
        r"\b(?:ignor[aă]|uit[aă]|desconsider[aă]|anuleaz[aă]|ignore|disregard|forget)\b.{0,40}\b"
        r"(?:instruc[tț]iuni\w*|reguli\w*|ordine\w*|prompt\w*|instructions?|rules?|prompts?|above|previous)\b",
    ),
    (
        "schimba_rolul",
        r"\b(?:e[sș]ti acum|de acum (?:e[sș]ti|ac[tț]ionezi)|ac[tț]ioneaz[aă] ca|compor[tț]-?te ca|"
        r"prefa-?te c[aă]|you are now|act as|pretend (?:to be|you are)|from now on you)\b",
    ),
    (
        "cere_promptul",
        r"\b(?:system prompt|prompt-?ul (?:de )?sistem|"
        r"instruc[tț]iunile (?:tale )?(?:de sistem|secrete|ini[tț]iale)|"
        r"reveal your (?:instructions|prompt)|dezv[aă]luie.{0,30}(?:instruc[tț]iuni|prompt))\b",
    ),
    (
        "fals_rol_sistem",
        r"(?:^|\n)\s*(?:system|sistem|assistant|asistent|developer)\s*:|"
        r"<\|(?:im_start|im_end|system)\|>|\[/?INST\]|<</?SYS>>|###\s*(?:system|instruction)",
    ),
    ("delimitator_fals", r"<<<\s*(?:SFARSIT_)?DATE_EXTERNE|‹‹‹\s*(?:SFARSIT_)?DATE_EXTERNE"),
    (
        "forteaza_raspunsul",
        r"\b(?:r[aă]spunde (?:doar|exclusiv) cu|respond (?:only|exclusively) with|"
        r"rezultatul (?:trebuie|este) (?:s[aă] fie )?exact|output exactly)\b",
    ),
    (
        "cere_actiune",
        r"\b(?:[sș]terge|trimite|public[aă]|transfer[aă]|delete|send|publish|transfer|execute|run)\b.{0,40}\b"
        r"(?:toate|tot|contul|parola|datele|database|baza de date|password|account|all)\b",
    ),
    ("exfiltrare", r"\b(?:trimite|[ıi]ncarc[aă]|send|upload|post)\b.{0,50}\bhttps?://"),
)
_COMPILATE = tuple((cod, re.compile(rx, re.IGNORECASE | re.DOTALL)) for cod, rx in TIPARE)


@dataclass(frozen=True)
class Semnal:
    cod: str
    sursa: str  # sursa blocului extern, sau „nemarcat”


def _normalizeaza(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def cauta(text: str, sursa: str) -> list[Semnal]:
    """Codurile tiparelor găsite în `text` (fără textul însuși)."""
    t = _normalizeaza(text)
    return [Semnal(cod, sursa) for cod, rx in _COMPILATE if rx.search(t)]
