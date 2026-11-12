"""Gateway de modele în panou: registrul de furnizori și modele (F3.1, doar citire + activare / dezactivare de
către proprietar) și jurnalul de apeluri (F3.7). Ecranul bogat „Modele și cote” este F3.10.

Citirea: orice rol de agenție. Activarea cere rolul de proprietar, CSRF și lasă urmă în audit. Cheile de
API nu
apar nicăieri: panoul arată doar dacă variabila de mediu este configurată.

Jurnalul de apeluri: lista (filtre pe client, model, furnizor și rezultat) și detaliul unui apel, cu
mesajele trimise
și răspunsul (cât timp nu au expirat, 30 de zile). Sesiunea este a utilizatorului, deci izolarea pe
client (RLS) se
aplică: un operator vede doar clientul lui activ, proprietarul vede toți clienții. Deschiderea
conținutului unui
apel lasă urmă în audit.
"""

import json
import uuid
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response

from app import gateway
from app.conturi import DbSession, SesiuneCurenta, csrf_protect, lista_clienti, require_role
from app.conturi.roluri import ROLURI_AGENTIE, Rol
from app.gateway import jurnal
from app.operare import audit
from app.panou.sabloane import pagina

router = APIRouter(prefix="/gateway", tags=["gateway"])
Agentie = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_AGENTIE))]
Proprietar = Annotated[SesiuneCurenta, Depends(require_role(Rol.PROPRIETAR))]

MESAJE = {
    "activat": "Furnizorul a fost activat.",
    "dezactivat": "Furnizorul a fost dezactivat.",
}
ETICHETE_STARE = {"activ": "activ", "inactiv": "inactiv", "pauza": "pe pauză"}
ETICHETE_MARCAJ = {
    "V": "verificat la sursă",
    "S": "sursă secundară",
    "I": "presupunere, neverificat",
}


def _da_nu(v: bool | None) -> str:
    return "necunoscut" if v is None else ("da" if v else "nu")


def _limite(obiect: gateway.Furnizor | gateway.ModelLlm) -> str:
    parti = []
    for valoare, eticheta in (
        (obiect.cereri_minut, "cereri/min"),
        (obiect.cereri_zi, "cereri/zi"),
        (obiect.tokeni_minut, "tokeni/min"),
        (obiect.tokeni_zi, "tokeni/zi"),
    ):
        if valoare is not None:
            parti.append(f"{valoare:,} {eticheta}".replace(",", "."))
    return ", ".join(parti) or "–"


def _pret(m: gateway.ModelLlm) -> str:
    return f"{m.pret_umbra_intrare:.2f} / {m.pret_umbra_iesire:.2f} USD la 1 mil. tokeni"


def date_registru(db: DbSession) -> list[dict[str, object]]:
    modele = gateway.modele(db)
    randuri: list[dict[str, object]] = []
    for f in gateway.furnizori(db):
        randuri.append(
            {
                "f": f,
                "modele": [m for m in modele if m.furnizor_id == f.id],
                "cheie_ok": gateway.cheie_configurata(f),
                "motiv_blocat": gateway.poate_fi_activat(f) if f.stare != "activ" else None,
                "limite": _limite(f),
            }
        )
    return randuri


@router.get("/registru")
def registru(request: Request, u: Agentie, db: DbSession, mesaj: str = "", eroare: str = "") -> Response:
    return pagina(
        request,
        u,
        "panou/gateway_registru.html",
        tab="meniu",
        mesaj=MESAJE.get(mesaj, ""),
        eroare=eroare[:300],
        randuri=date_registru(db),
        poate_actiona=u.rol is Rol.PROPRIETAR,
        etichete_stare=ETICHETE_STARE,
        etichete_marcaj=ETICHETE_MARCAJ,
        da_nu=_da_nu,
        limite=_limite,
        pret=_pret,
    )


@router.post("/furnizori/{furnizor_id}/activeaza", dependencies=[Depends(csrf_protect)])
def activeaza(u: Proprietar, db: DbSession, furnizor_id: uuid.UUID) -> Response:
    try:
        gateway.activeaza(db, furnizor_id, utilizator_id=u.utilizator_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Furnizorul nu există.") from None
    except gateway.NuSePoateActiva as exc:
        return RedirectResponse(f"/gateway/registru?eroare={_cod(str(exc))}", status_code=303)
    return RedirectResponse("/gateway/registru?mesaj=activat", status_code=303)


@router.post("/furnizori/{furnizor_id}/dezactiveaza", dependencies=[Depends(csrf_protect)])
def dezactiveaza(
    u: Proprietar,
    db: DbSession,
    furnizor_id: uuid.UUID,
    motiv: Annotated[str, Form(max_length=300)] = "",
) -> Response:
    try:
        gateway.dezactiveaza(db, furnizor_id, motiv=motiv, utilizator_id=u.utilizator_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Furnizorul nu există.") from None
    return RedirectResponse("/gateway/registru?mesaj=dezactivat", status_code=303)


def _cod(text: str) -> str:
    from urllib.parse import quote

    return quote(text[:300])


# --- jurnalul de apeluri (F3.7)

PE_PAGINA = 50
ETICHETE_REZULTAT = {"ok": "reușit", "esec": "eșuat", "amanat": "amânat", "refuzat": "refuzat"}
CLASA_REZULTAT = {"ok": "ok", "esec": "pericol", "amanat": "atentie", "refuzat": "pericol"}


def _uuid_sau_none(valoare: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(valoare) if valoare else None
    except ValueError:
        return None


@router.get("/apeluri")
def apeluri(
    request: Request,
    u: Agentie,
    db: DbSession,
    client: str = "",
    model: str = "",
    furnizor: str = "",
    rezultat: str = "",
    pagina_: Annotated[int, Query(alias="pagina", ge=1, le=10_000)] = 1,
) -> Response:
    filtre = jurnal.Filtre(
        client=_uuid_sau_none(client),
        model=model.strip()[:100],
        furnizor=furnizor.strip()[:40],
        rezultat=rezultat,
    )
    randuri = jurnal.lista(db, filtre, limita=PE_PAGINA + 1, decalaj=(pagina_ - 1) * PE_PAGINA)
    nume_client = {c.id: c.nume for c in lista_clienti(db)}
    parametri = {
        k: v
        for k, v in (("client", client), ("model", model), ("furnizor", furnizor), ("rezultat", rezultat))
        if v
    }
    return pagina(
        request,
        u,
        "panou/gateway_apeluri.html",
        tab="meniu",
        randuri=[{"a": a, "client": nume_client.get(a.tenant_id, "–")} for a in randuri[:PE_PAGINA]],
        total=jurnal.totaluri(db, filtre),
        clienti=sorted(nume_client.items(), key=lambda p: p[1]),
        modele=jurnal.modele_folosite(db),
        filtre={"client": client, "model": model, "furnizor": furnizor, "rezultat": rezultat},
        etichete_rezultat=ETICHETE_REZULTAT,
        clasa_rezultat=CLASA_REZULTAT,
        pagina_curenta=pagina_,
        are_urmatoarea=len(randuri) > PE_PAGINA,
        interogare=urlencode(parametri),
    )


@router.get("/apeluri/{apel_id}")
def apel(request: Request, u: Agentie, db: DbSession, apel_id: uuid.UUID) -> Response:
    gasit = jurnal.citeste(db, apel_id)
    if gasit is None:  # inexistent sau al altui client (RLS)
        raise HTTPException(status_code=404, detail="Apelul nu există.")
    a, continut = gasit
    audit.record(
        db, "gateway.apel_citit", obiect_tip="apel", obiect_id=str(a.id), tenant_id=a.tenant_id,
        detalii={"cu_continut": continut is not None, "model": a.model},
    )  # fmt: skip
    nume_client = {c.id: c.nume for c in lista_clienti(db)}
    return pagina(
        request,
        u,
        "panou/gateway_apel.html",
        tab="meniu",
        a=a,
        continut=continut,
        raspuns_text=(
            json.dumps(continut.raspuns, ensure_ascii=False, indent=2)
            if continut is not None and continut.raspuns is not None
            else ""
        ),
        client=nume_client.get(a.tenant_id, "–"),
        etichete_rezultat=ETICHETE_REZULTAT,
        clasa_rezultat=CLASA_REZULTAT,
    )
