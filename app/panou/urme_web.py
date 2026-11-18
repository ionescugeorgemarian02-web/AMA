"""Ecranul „Urme” (FT.5): trasabilitatea totală, doar pentru proprietar.

- `/urme?luna=AAAA-LL`: raportul lunar (salvat sau calculat acum): indicatorii, bine/prost, regresii,
  costuri, porți picate, motive de respingere, eșecurile cu lanțul până la sursă).
- `POST /urme/genereaza`: (re)generează raportul lunii (CSRF).
- `/urme/fir/<corelare>`: toate urmele unui fir, în ordine, cu cauzele.
- `/urme/export.json?luna=` (raportul întreg) și `/urme/export.csv?luna=&ce=esecuri|indicatori|urme`.
"""

import csv
import datetime as dt
import io
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select

from app.conturi import DbSession, Rol, SesiuneCurenta, csrf_protect, require_role
from app.operare import urme
from app.operare.urme import analiza
from app.panou.sabloane import pagina

router = APIRouter(prefix="/urme", tags=["urme"])
Proprietar = Annotated[SesiuneCurenta, Depends(require_role(Rol.PROPRIETAR))]
LIMITA_URME_CSV = 50_000
COLOANE_URME = (
    "la", "corelare_id", "id", "cauza_id", "tenant_id", "componenta", "actiune", "actor", "rezultat", "cod",
    "motiv", "cost", "unitate_cost", "durata_ms", "obiect_tip", "obiect_id",
)  # fmt: skip


def _luna(text: str) -> dt.date:
    if not text:
        return analiza.luna_precedenta(analiza.luna_de(dt.datetime.now(dt.UTC)))
    try:
        return dt.date.fromisoformat(f"{text[:7]}-01")
    except ValueError:
        raise HTTPException(400, "Luna se scrie AAAA-LL.") from None


def _raport(db: DbSession, luna: dt.date) -> tuple[dict[str, Any], bool]:
    """Raportul salvat sau, dacă lipsește, calculat acum (nesalvat)."""
    salvat = analiza.raport(db, luna)
    return (
        (salvat, True)
        if salvat is not None
        else (json.loads(json.dumps(analiza.analizeaza(db, luna))), False)
    )


@router.get("")
def ecran(request: Request, u: Proprietar, db: DbSession, luna: str = "", mesaj: str = "") -> Response:
    lu = _luna(luna)
    r, salvat = _raport(db, lu)
    return pagina(
        request, u, "panou/urme.html", tab="meniu", r=r, salvat=salvat, luna=lu.isoformat()[:7],
        luni=[x.isoformat()[:7] for x in analiza.luni_cu_raport(db)], mesaj=mesaj,
    )  # fmt: skip


@router.post("/genereaza", dependencies=[Depends(csrf_protect)])
def genereaza(u: Proprietar, db: DbSession, luna: Annotated[str, Form()] = "") -> Response:
    lu = _luna(luna)
    analiza.genereaza(db, lu)
    return RedirectResponse(f"/urme?luna={lu.isoformat()[:7]}&mesaj=generat", status_code=303)


@router.get("/fir/{corelare}")
def fir(request: Request, u: Proprietar, db: DbSession, corelare: str) -> Response:
    randuri = list(
        db.scalars(select(urme.Urma).where(urme.Urma.corelare_id == corelare[:100]).order_by(urme.Urma.la))
    )
    if not randuri:
        raise HTTPException(404, "Fir inexistent.")
    return pagina(request, u, "panou/urme_fir.html", tab="meniu", fir=corelare, urme=randuri)


@router.get("/export.json")
def export_json(u: Proprietar, db: DbSession, luna: str = "") -> Response:
    lu = _luna(luna)
    r, _ = _raport(db, lu)
    return Response(
        json.dumps(r, ensure_ascii=False, indent=2), media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="urme-{lu.isoformat()[:7]}.json"'},
    )  # fmt: skip


def _csv(randuri: list[list[Any]], antet: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(antet)
    w.writerows(randuri)
    return buf.getvalue()


@router.get("/export.csv")
def export_csv(u: Proprietar, db: DbSession, luna: str = "", ce: str = "esecuri") -> Response:
    lu = _luna(luna)
    if ce == "esecuri":
        r, _ = _raport(db, lu)
        antet = [
            "la",
            "fir",
            "componenta",
            "actiune",
            "rezultat",
            "cod",
            "motiv",
            "sursa",
            "cauza_probabila",
            "explicatie",
        ]
        randuri = [
            [
                e["esec"]["la"],
                e["fir"],
                e["esec"]["componenta"],
                e["esec"]["actiune"],
                e["esec"]["rezultat"],
                e["esec"]["cod"],
                e["esec"]["motiv"],
                f"{e['sursa']['componenta']}/{e['sursa']['actiune']}",
                f"{e['cauza_probabila']['componenta']}/{e['cauza_probabila']['actiune']}"
                if e["cauza_probabila"]
                else "",
                e["explicatie"],
            ]
            for e in r["esecuri"]
        ]
    elif ce == "indicatori":
        r, _ = _raport(db, lu)
        antet = [
            "componenta",
            "total",
            "rata_esec",
            "ok",
            "esec",
            "respins",
            "blocat",
            "amanat",
            "p50_ms",
            "p95_ms",
            "cost",
        ]
        randuri = [
            [
                i["componenta"],
                i["total"],
                i["rata_esec"],
                *(i["pe_rezultat"].get(k, 0) for k in ("ok", "esec", "respins", "blocat", "amanat")),
                i["durata_p50_ms"],
                i["durata_p95_ms"],
                "; ".join(f"{u_}={v}" for u_, v in i["cost"].items()),
            ]
            for i in r["indicatori"]
        ]
    elif ce == "urme":
        de_la = dt.datetime(lu.year, lu.month, 1, tzinfo=dt.UTC)
        urm = analiza.luna_de(de_la + dt.timedelta(days=32))
        pana_la = dt.datetime(urm.year, urm.month, 1, tzinfo=dt.UTC)
        q = select(urme.Urma).where(urme.Urma.la >= de_la, urme.Urma.la < pana_la).order_by(urme.Urma.la)
        antet = list(COLOANE_URME)
        randuri = [[getattr(x, c) for c in COLOANE_URME] for x in db.scalars(q.limit(LIMITA_URME_CSV))]
    else:
        raise HTTPException(400, "Exportul este „esecuri”, „indicatori” sau „urme”.")
    return Response(
        _csv(randuri, antet), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="urme-{ce}-{lu.isoformat()[:7]}.csv"'},
    )  # fmt: skip
