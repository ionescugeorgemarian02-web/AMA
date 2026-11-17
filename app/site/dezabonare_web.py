"""Dezabonarea dintr-un clic (F12.2, docs/17 §17.3, docs/21 §21.8). Linkul din email deschide o pagină cu un
singur buton; `POST` pe aceeași adresă dezabonează (și e ținta antetului `List-Unsubscribe-Post`, trimisă de
programele de email fără pagină). Jetonul semnat din adresă e singura autentificare, deci fără CSRF."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.crm import email as crm_email
from app.db import sesiune_agentie
from app.site.web import randeaza

router = APIRouter(prefix="/site/dezabonare", tags=["site"])


@router.get("/{jeton}")
def pagina(request: Request, jeton: str) -> HTMLResponse:
    if crm_email.email_din_jeton(jeton) is None:
        raise HTTPException(status_code=404, detail="Linkul nu este valid.")
    return randeaza(request, "site/dezabonare.html", "dezabonare", jeton=jeton, gata=False)


@router.post("/{jeton}")
def dezaboneaza(request: Request, jeton: str) -> HTMLResponse:
    with sesiune_agentie() as db:
        if not crm_email.dezaboneaza(db, jeton):
            raise HTTPException(status_code=404, detail="Linkul nu este valid.")
    return randeaza(request, "site/dezabonare.html", "dezabonare", jeton=jeton, gata=True)
