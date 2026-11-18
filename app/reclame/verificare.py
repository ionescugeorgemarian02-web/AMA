"""Verificarea reclamelor înainte de lansare (F13.8, I5, docs/16 §16.8 și §16.3 pasul 6). Reguli, fără model.

Pe fiecare reclamă, la construcție:
- pachetele de reguli (ca la G3, `reguli.selecteaza`: generale, de nișă și `reclame.toml` pentru canalele
  `meta_ads` / `google_ads`): atribute personale, promisiuni de rezultat, categorii speciale, produse
  restricționate; o regulă majoră sau critică blochează reclama;
- pachetele juridice ale canalului (mențiunile obligatorii);
- dezvăluirea AI: creativul generat cu AI o spune în text („AI”);
- potrivirea cu pagina de destinație: pagina răspunde și conține cel puțin un cuvânt important din titlu;
- linkul poartă schema UTM (urmărirea).
O reclamă blocată nu pleacă la platformă; o campanie fără nicio reclamă bună nu se creează. La activare se
reverifică pagina de destinație și existența unei reclame bune.
"""

import re
import unicodedata
from collections.abc import Callable
from typing import Any

from app.reclame import pagina
from app.validare import reguli

CANALE = {"meta": "meta_ads", "google": "google_ads"}
MINIM_CUVANT = 5


def _pagina(url: str) -> str | None:
    """Textul paginii de destinație, sau `None` dacă nu răspunde. # NEVERIFICAT: GET simplu, fără JS."""
    r = pagina.get_sigur(url)  # F15.2: fără SSRF (adrese interne, metadate cloud, redirecționări)
    return r.text if r is not None and r.status_code < 400 else None


CITESTE_PAGINA: Callable[[str], str | None] = _pagina


def probleme_text(text: str, platforma: str) -> list[dict[str, Any]]:
    """Nucleu: regulile de politică și mențiunile juridice pe textul reclamei."""
    canal = CANALE.get(platforma, platforma)
    ctx = reguli.Context(canal=canal, tip="reclama")
    out: list[dict[str, Any]] = []
    vazute: set[str] = set()
    for p in [*reguli.selecteaza(canal), *reguli.pachete_juridice(canal)]:
        for r in p.pachet.reguli:
            if r.severitate == "minora" or r.id in vazute:
                continue
            for pot in reguli.potriviri(r, text, ctx):
                vazute.add(r.id)
                out.append(
                    {"cod": f"{p.nume}.{r.id}", "fragment": pot.fragment, "text": r.text, "sursa": "reguli"}
                )
                break
    return out


def cuvinte(text: str) -> set[str]:
    simplu = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return {w for w in re.findall(r"[a-z0-9]+", simplu) if len(w) >= MINIM_CUVANT}


def verifica(titlu: str, text: str, link: str, platforma: str, *, generat_ai: bool) -> list[dict[str, Any]]:
    """Problemele unei reclame. Listă goală = poate pleca."""
    out = probleme_text(f"{titlu}\n{text}", platforma)
    if generat_ai and not re.search(r"\bAI\b|inteligen[țt][ăa] artificial", f"{titlu} {text}", re.I):
        out.append(
            {
                "cod": "dezvaluire_ai",
                "fragment": "",
                "sursa": "reguli",
                "text": "creativul e generat cu AI: reclama trebuie să o spună",
            }
        )
    if "utm_source=" not in link:
        out.append(
            {
                "cod": "urmarire",
                "fragment": "",
                "sursa": "reguli",
                "text": "linkul nu poartă schema UTM: rezultatele nu se pot măsura pe site",
            }
        )
    pagina = CITESTE_PAGINA(link)
    if pagina is None:
        out.append(
            {"cod": "pagina", "fragment": "", "sursa": "reguli", "text": "pagina de destinație nu răspunde"}
        )
    elif cuvinte(titlu) and not cuvinte(titlu) & cuvinte(pagina):
        out.append(
            {
                "cod": "potrivire",
                "fragment": titlu,
                "sursa": "reguli",
                "text": "reclama nu se potrivește cu pagina de destinație (niciun cuvânt din titlu)",
            }
        )
    return out
