"""Regulile de limbă pentru conținutul în engleză (F16.3). Nucleu pur, determinist, ca G10 pentru română.

- Diacriticele românești (ă â î ș ț, și cu sedilă) nu au ce căuta într-un text englez: până la
`TOLERANTA_NUME`
  cuvinte se iau drept nume proprii (brandul, strada), peste ele textul e respins (amestec de limbi).
- Ghilimelele românești „…” → avertisment, cu ghilimelele englezești “…”.
- Repetiția aceluiași cuvânt, ca la română.
Limba conținutului: `campuri["limba"]`, altfel limba clientului (`clienti.limba`), altfel română.
"""

import re

from app.validare.intrare import Intrare
from app.validare.probleme import Problema
from app.validare.verdict import Severitate

DIACRITICE_RO = re.compile(r"[ăâîșțşţĂÂÎȘȚŞŢ]")
TOLERANTA_NUME = 2  # [I] cuvinte cu diacritice primite ca nume proprii


def limba_intrare(intrare: Intrare) -> str:
    """Limba în care trebuie să fie conținutul validat."""
    from app import localizare

    ceruta = intrare.continut.campuri.get("limba")
    if isinstance(ceruta, str) and ceruta:
        return localizare.normalizeaza(ceruta)
    if intrare.db is None:
        return localizare.IMPLICITA
    return intrare.memo("limba", lambda: localizare.limba_client(intrare.baza(), intrare.livrabil.tenant_id))


def probleme_limba_en(text: str) -> list[Problema]:
    out: list[Problema] = []
    cu_diacritice = [c for c in text.split() if DIACRITICE_RO.search(c)]
    if len(cu_diacritice) > TOLERANTA_NUME:
        out.append(
            Problema(
                "G10.diacritice_in_engleza",
                " ".join(cu_diacritice[:3]),
                "Textul clientului e în engleză, dar conține cuvinte românești; rescrie-le în engleză "
                "(numele proprii rămân).",
                detalii=f"{len(cu_diacritice)} cuvinte cu diacritice românești",
            )
        )
    if "„" in text:
        out.append(
            Problema(
                "G10.ghilimele_en",
                "„",
                "În engleză folosește ghilimelele “…”, nu ghilimelele românești „…”.",
                blocant=False,
                severitate=Severitate.MINORA,
            )
        )
    m = re.search(r"\b([^\W\d_]{3,})\s+\1\b", text, re.IGNORECASE)
    if m:
        out.append(
            Problema(
                "G10.repetitie",
                m.group(0),
                f"Cuvântul „{m.group(1)}” este repetat; scoate una dintre apariții.",
                blocant=False,
                severitate=Severitate.MINORA,
            )
        )
    return out
