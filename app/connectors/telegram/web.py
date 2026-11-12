"""Webhook-ul Telegram. Public prin proxy (doar `/intern/*` e blocat acolo), deci păzit de două ori:
antetul-secret și lista de conversații permise (aceasta din urmă în `bot.proceseaza`)."""

import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, HTTPException
from pydantic import ValidationError

from app.config import get_settings
from app.connectors.telegram import bot, get_client
from app.connectors.telegram.modele import Actualizare
from app.logging import get_logger

log = get_logger("app.telegram")

router = APIRouter(tags=["telegram"], include_in_schema=False)


@router.post("/telegram/webhook")
def webhook(
    payload: Annotated[dict[str, Any], Body()],
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
) -> dict[str, bool]:
    s = get_settings()
    if not s.telegram_activ:
        raise HTTPException(status_code=404)
    asteptat = s.telegram_webhook_secret.get_secret_value().encode()
    primit = (x_telegram_bot_api_secret_token or "").encode()
    if not primit or not hmac.compare_digest(primit, asteptat):
        raise HTTPException(status_code=401)
    try:
        update = Actualizare.model_validate(payload)
    except ValidationError:
        log.warning("actualizare Telegram fără formă recunoscută")
        return {"ok": True}  # 200: altfel Telegram o retrimite la nesfârșit
    bot.proceseaza(update, get_client())
    return {"ok": True}
