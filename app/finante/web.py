"""Webhook-ul procesatorului de plăți (F7.6): mașină la mașină, fără browser și fără cookie, deci fără CSRF;
se apără prin semnătura HMAC a corpului (secretul `AMA_PLATI_WEBHOOK_SECRET`, comparat în timp constant) și
prin
vechimea evenimentului (≤ 5 minute); fiecare eveniment se aplică o singură dată."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.finante import abonamente

router = APIRouter(prefix="/facturare", tags=["facturare"])
ANTET = "x-semnatura"
LIMITA = 64 * 1024


@router.post("/webhook")
async def webhook(request: Request) -> JSONResponse:
    corp = await request.body()
    if len(corp) > LIMITA:
        return JSONResponse({"eroare": "prea mare"}, status_code=413)
    try:
        rezultat = abonamente.trateaza_webhook(corp, request.headers.get(ANTET, ""))
    except abonamente.SemnaturaInvalida:
        return JSONResponse({"eroare": "semnătură"}, status_code=400)
    except (abonamente.EroareFacturare, KeyError, ValueError):
        return JSONResponse({"eroare": "eveniment invalid"}, status_code=422)
    return JSONResponse({"rezultat": rezultat})
