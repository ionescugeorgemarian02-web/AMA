"""# SIMULAT: vectorizator fals, determinist, care păstrează o noțiune de apropiere (sac de cuvinte cu hashing).

Nu e un model de limbaj: fiecare cuvânt (fără diacritice, fără cuvinte de legătură) și prefixul lui de 4 litere devin
„găleți” într-un vector de dimensiune fixă; vectorul se normalizează. Două texte cu multe cuvinte comune au vectori
apropiați (cosinus mare), două texte fără cuvinte comune sunt aproape ortogonale. Calitatea reală a modelului
multilingv rămâne „De verificat la migrare”. Independent de codul aplicației (are propria normalizare)."""

import hashlib
import math
import re
import unicodedata

STOP = frozenset(
    [
        "a",
        "al",
        "ale",
        "am",
        "are",
        "aveti",
        "ca",
        "cat",
        "cate",
        "care",
        "cand",
        "ce",
        "cu",
        "cum",
        "de",
        "din",
        "e",
        "este",
        "in",
        "la",
        "mai",
        "nu",
        "o",
        "pe",
        "pentru",
        "pot",
        "poate",
        "poti",
        "si",
        "sa",
        "se",
        "sunt",
        "sau",
        "un",
        "una",
        "va",
    ]
)


def _cuvinte(text: str) -> list[str]:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return [c for c in re.findall(r"[a-z0-9]+", t) if c not in STOP and len(c) > 1]


def vector_bow(text: str, dim: int = 384) -> list[float]:
    v = [0.0] * dim
    for c in _cuvinte(text):
        for trasatura, pondere in ((c, 1.0), (c[:4], 0.6)):
            h = hashlib.sha256(trasatura.encode()).digest()
            v[int.from_bytes(h[:4], "big") % dim] += pondere * (1 if h[4] % 2 else -1)
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [round(x / n, 6) for x in v]
