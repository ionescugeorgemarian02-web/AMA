"""Adaptoarele de furnizori: câte unul pe TIP de API (nu pe furnizor). Doar `app.gateway` le importă (garda
`scripts/check_gateway.py`). Un furnizor nou compatibil OpenAI nu cere cod, ci un rând în registru.

Punct de extensie: `inregistreaza(Adaptor)` adaugă un tip de API (de exemplu `local`, F3.5).
"""

from app.gateway.adaptoare.anthropic import Anthropic
from app.gateway.adaptoare.baza import Adaptor
from app.gateway.adaptoare.gemini import Gemini
from app.gateway.adaptoare.openai_compat import OpenAICompat

_ADAPTOARE: dict[str, Adaptor] = {}


def inregistreaza(adaptor: Adaptor) -> None:
    _ADAPTOARE[adaptor.tip_api] = adaptor


def adaptor_pentru(tip_api: str) -> Adaptor:
    try:
        return _ADAPTOARE[tip_api]
    except KeyError:
        raise LookupError(f"tip de API necunoscut: {tip_api!r}") from None


def tipuri() -> list[str]:
    return sorted(_ADAPTOARE)


for _a in (OpenAICompat(), Gemini(), Anthropic()):
    inregistreaza(_a)

__all__ = ["Adaptor", "adaptor_pentru", "inregistreaza", "tipuri"]
