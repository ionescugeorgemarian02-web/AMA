"""Randarea șabloanelor Jinja2 (autoescape activ). Șabloanele stau în app/web/templates."""

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

DIRECTOR = Path(__file__).resolve().parents[1] / "web" / "templates"
templates = Jinja2Templates(directory=str(DIRECTOR))

ETICHETE_ROL = {
    "proprietar": "Proprietar",
    "operator": "Operator",
    "analist": "Analist",
    "client_titular": "Client, titular",
    "client_aprobator": "Client, aprobator",
    "client_vizitator": "Client, vizitator",
}


def randare(request: Request, sablon: str, status: int = 200, **context: Any) -> HTMLResponse:
    r = templates.TemplateResponse(
        request, sablon, {"etichete_rol": ETICHETE_ROL, **context}, status_code=status
    )
    r.headers["Cache-Control"] = "no-store"
    return r
