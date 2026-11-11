"""Randarea paginilor panoului. Șabloanele stau în app/web/templates/panou (autoescape activ)."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.conturi import SesiuneCurenta
from app.conturi.roluri import Rol

DIRECTOR = Path(__file__).resolve().parents[1] / "web" / "templates"
STATIC = DIRECTOR.parent / "static"
templates = Jinja2Templates(directory=str(DIRECTOR))

ETICHETE_ROL = {
    "proprietar": "Proprietar",
    "operator": "Operator",
    "analist": "Analist",
}
ETICHETE_BACKUP = {
    "nerulat": "încă nu a rulat",
    "ok": "în regulă",
    "invechit": "învechit",
    "esuat": "eșuat",
    "necitibil": "necitibil",
}
ETICHETE_STARE = {
    "solicitata": "solicitată",
    "in_curs": "în curs",
    "reusita": "reușită",
    "esuata": "eșuată",
    "revenita": "revenire făcută",
}
ETICHETE_CERERE = {"promovare": "promovare în producție", "revenire": "revenire la versiunea anterioară"}


def _moment(t: datetime | None) -> str:
    if t is None:
        return "–"
    t = t if t.tzinfo else t.replace(tzinfo=UTC)
    return t.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


templates.env.filters["moment"] = _moment


def pagina(
    request: Request, u: SesiuneCurenta, sablon: str, *, tab: str, status: int = 200, **context: Any
) -> HTMLResponse:
    r = templates.TemplateResponse(
        request,
        sablon,
        {
            "csrf_token": u.csrf_token,
            "utilizator": u,
            "tab": tab,
            "etichete_rol": ETICHETE_ROL,
            "etichete_backup": ETICHETE_BACKUP,
            "etichete_stare": ETICHETE_STARE,
            "etichete_cerere": ETICHETE_CERERE,
            "este_proprietar": u.rol is Rol.PROPRIETAR,
            **context,
        },
        status_code=status,
    )
    r.headers["Cache-Control"] = "no-store"  # paginile autentificate nu se țin în cache
    return r
