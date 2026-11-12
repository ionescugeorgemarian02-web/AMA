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

import datetime as dt
import json
import uuid
from typing import Annotated
from urllib.parse import quote, urlencode

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
    "limite": "Limitele au fost salvate; se aplică de la următorul apel.",
    "termeni": "Termenii au fost salvați.",
    "buget": "Bugetul clientului a fost salvat.",
    "bugete": "Bugetele implicite au fost salvate.",
    "evaluare": "Testul comparativ a fost pus în coadă (prioritate P3, după producție).",
    "note": "Notele au fost importate; scorurile din registru sunt recalculate.",
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


def _nr(n: int | None) -> str:
    return "–" if n is None else f"{int(n):,}".replace(",", ".")


def _ora(moment: dt.datetime | None) -> str:
    return "–" if moment is None else moment.astimezone(dt.UTC).strftime("%d.%m %H:%M UTC")


def _opt(valoare: str) -> str | None:
    return valoare.strip() or None


def _bool_optional(valoare: str) -> bool | None:
    return {"da": True, "nu": False}.get(valoare)


def primele_cote(
    db: DbSession,
    candidati: dict[uuid.UUID, gateway.Candidat],
    din_furnizor: list[gateway.ModelLlm],
    acum: dt.datetime,
) -> list[gateway.situatie.Cota]:
    """Cotele contului furnizorului (aceleași pentru toate modelele lui; se citesc prin primul)."""
    if not din_furnizor:
        return []
    return gateway.situatie.cote_pentru(db, candidati[din_furnizor[0].id], acum)


def date_registru(db: DbSession) -> list[dict[str, object]]:
    modele = gateway.modele(db)
    candidati = {c.model_id: c for c in gateway.registru.candidati(db)}
    acum = gateway.situatie.acum()
    randuri: list[dict[str, object]] = []
    for f in gateway.furnizori(db):
        din_furnizor = [m for m in modele if m.furnizor_id == f.id]
        cote_modele = {
            m.id: gateway.situatie.cote_pentru(db, candidati[m.id], acum)
            for m in din_furnizor
            if m.id in candidati
        }
        randuri.append(
            {
                "f": f,
                "modele": din_furnizor,
                "cheie_ok": gateway.cheie_configurata(f),
                "motiv_blocat": gateway.poate_fi_activat(f) if f.stare != "activ" else None,
                "limite": _limite(f),
                "cote": cote_modele,
                "cote_cont": [
                    c for c in (primele_cote(db, candidati, din_furnizor, acum)) if c.resursa == "cont"
                ],
                "blocaj": gateway.situatie.blocaj_pentru(db, candidati[din_furnizor[0].id], acum)
                if din_furnizor
                else None,
                "intrerupt": f.intrerupt_pana_la is not None and f.intrerupt_pana_la > acum,
            }
        )
    return randuri


def date_scoruri(db: DbSession) -> dict[str, object]:
    profiluri = gateway.registru.nume_profiluri(db)
    modele = [m for m in gateway.modele(db) if "embeddings" not in (m.capabilitati or [])]
    codes = {f.id: f.cod for f in gateway.furnizori(db)}
    return {
        "profiluri": profiluri,
        "randuri": [
            {"cod": f"{codes[m.furnizor_id]}/{m.identificator}", "m": m, "scor": m.scor or {}} for m in modele
        ],
        "rulari": gateway.evaluare.istoric(db, 8),
    }


@router.get("/registru")
def registru(request: Request, u: Agentie, db: DbSession, mesaj: str = "", eroare: str = "") -> Response:
    acum = gateway.situatie.acum()
    return pagina(
        request,
        u,
        "panou/gateway_registru.html",
        tab="meniu",
        mesaj=MESAJE.get(mesaj, ""),
        eroare=eroare[:300],
        randuri=date_registru(db),
        scoruri=date_scoruri(db),
        clienti=gateway.bugete.situatie(db, acum),
        implicit=gateway.bugete.implicit(db),
        poate_actiona=u.rol is Rol.PROPRIETAR,
        etichete_stare=ETICHETE_STARE,
        etichete_marcaj=ETICHETE_MARCAJ,
        da_nu=_da_nu,
        limite=_limite,
        pret=_pret,
        nr=_nr,
        ora=_ora,
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


# --- editare de către proprietar (F3.10): limite, termeni, bugete, test comparativ (CSRF, proprietar, audit)


def _limite_form(cereri_minut: str, cereri_zi: str, tokeni_minut: str, tokeni_zi: str) -> dict[str, object]:
    return {
        "cereri_minut": cereri_minut, "cereri_zi": cereri_zi,
        "tokeni_minut": tokeni_minut, "tokeni_zi": tokeni_zi,
    }  # fmt: skip


def _inapoi(mesaj: str = "", eroare: str = "") -> RedirectResponse:
    q = f"mesaj={mesaj}" if mesaj else f"eroare={quote(eroare[:300])}"
    return RedirectResponse(f"/gateway/registru?{q}", status_code=303)


@router.post("/furnizori/{furnizor_id}/limite", dependencies=[Depends(csrf_protect)])
def limite_furnizor(
    u: Proprietar,
    db: DbSession,
    furnizor_id: uuid.UUID,
    cereri_minut: Annotated[str, Form(max_length=15)] = "",
    cereri_zi: Annotated[str, Form(max_length=15)] = "",
    tokeni_minut: Annotated[str, Form(max_length=15)] = "",
    tokeni_zi: Annotated[str, Form(max_length=15)] = "",
    reset_zi_ora: Annotated[str, Form(max_length=3)] = "",
) -> Response:
    try:
        gateway.registru.seteaza_limite(
            db, "furnizor", furnizor_id,
            _limite_form(cereri_minut, cereri_zi, tokeni_minut, tokeni_zi),
            reset_zi_ora=reset_zi_ora, utilizator_id=u.utilizator_id,
        )  # fmt: skip
    except LookupError:
        raise HTTPException(status_code=404, detail="Furnizorul nu există.") from None
    except gateway.registru.RegistruInvalid as exc:
        db.rollback()
        return _inapoi(eroare=str(exc))
    return _inapoi("limite")


@router.post("/modele/{model_id}/limite", dependencies=[Depends(csrf_protect)])
def limite_model(
    u: Proprietar,
    db: DbSession,
    model_id: uuid.UUID,
    cereri_minut: Annotated[str, Form(max_length=15)] = "",
    cereri_zi: Annotated[str, Form(max_length=15)] = "",
    tokeni_minut: Annotated[str, Form(max_length=15)] = "",
    tokeni_zi: Annotated[str, Form(max_length=15)] = "",
) -> Response:
    try:
        gateway.registru.seteaza_limite(
            db, "model", model_id,
            _limite_form(cereri_minut, cereri_zi, tokeni_minut, tokeni_zi),
            utilizator_id=u.utilizator_id,
        )  # fmt: skip
    except LookupError:
        raise HTTPException(status_code=404, detail="Modelul nu există.") from None
    except gateway.registru.RegistruInvalid as exc:
        db.rollback()
        return _inapoi(eroare=str(exc))
    return _inapoi("limite")


@router.post("/furnizori/{furnizor_id}/termeni", dependencies=[Depends(csrf_protect)])
def termeni_furnizor(
    u: Proprietar,
    db: DbSession,
    furnizor_id: uuid.UUID,
    uz_comercial: Annotated[str, Form(max_length=10)] = "",
    antrenare_pe_date: Annotated[str, Form(max_length=10)] = "",
    restrictii_regionale: Annotated[str, Form(max_length=500)] = "",
    marcaj: Annotated[str, Form(max_length=1)] = "I",
    verificat_la: Annotated[str, Form(max_length=10)] = "",
) -> Response:
    try:
        data = dt.date.fromisoformat(verificat_la) if verificat_la.strip() else None
        gateway.registru.seteaza_termeni(
            db, furnizor_id, uz_comercial=_bool_optional(uz_comercial),
            antrenare_pe_date=_bool_optional(antrenare_pe_date), restrictii_regionale=restrictii_regionale,
            marcaj=marcaj, verificat_la=data, utilizator_id=u.utilizator_id,
        )  # fmt: skip
    except LookupError:
        raise HTTPException(status_code=404, detail="Furnizorul nu există.") from None
    except ValueError as exc:  # inclusiv RegistruInvalid și o dată greșită
        db.rollback()
        return _inapoi(
            eroare=str(exc)
            if isinstance(exc, gateway.registru.RegistruInvalid)
            else "Data nu e validă (AAAA-LL-ZZ)."
        )
    return _inapoi("termeni")


def _valori_buget(
    apeluri_zi: str,
    tokeni_zi: str,
    pret_umbra_zi: str,
    apeluri_luna: str,
    tokeni_luna: str,
    pret_umbra_luna: str,
) -> dict[str, object]:
    return {
        "apeluri_zi": apeluri_zi,
        "tokeni_zi": tokeni_zi,
        "pret_umbra_zi": pret_umbra_zi.replace(",", "."),
        "apeluri_luna": apeluri_luna,
        "tokeni_luna": tokeni_luna,
        "pret_umbra_luna": pret_umbra_luna.replace(",", "."),
    }


@router.post("/clienti/{client_id}/buget", dependencies=[Depends(csrf_protect)])
def buget_client(
    u: Proprietar,
    db: DbSession,
    client_id: uuid.UUID,
    apeluri_zi: Annotated[str, Form(max_length=15)] = "",
    tokeni_zi: Annotated[str, Form(max_length=15)] = "",
    pret_umbra_zi: Annotated[str, Form(max_length=15)] = "",
    apeluri_luna: Annotated[str, Form(max_length=15)] = "",
    tokeni_luna: Annotated[str, Form(max_length=15)] = "",
    pret_umbra_luna: Annotated[str, Form(max_length=15)] = "",
) -> Response:
    if not any(c.id == client_id for c in lista_clienti(db)):
        raise HTTPException(status_code=404, detail="Clientul nu există.")
    try:
        gateway.bugete.seteaza_client(
            db, client_id,
            _valori_buget(apeluri_zi, tokeni_zi, pret_umbra_zi, apeluri_luna, tokeni_luna, pret_umbra_luna),
            utilizator_id=u.utilizator_id,
        )  # fmt: skip
    except gateway.bugete.BugetInvalid as exc:
        db.rollback()
        return _inapoi(eroare=str(exc))
    return _inapoi("buget")


@router.post("/bugete/implicite", dependencies=[Depends(csrf_protect)])
def bugete_implicite(
    u: Proprietar,
    db: DbSession,
    apeluri_zi: Annotated[str, Form(max_length=15)] = "",
    tokeni_zi: Annotated[str, Form(max_length=15)] = "",
    pret_umbra_zi: Annotated[str, Form(max_length=15)] = "",
    apeluri_luna: Annotated[str, Form(max_length=15)] = "",
    tokeni_luna: Annotated[str, Form(max_length=15)] = "",
    pret_umbra_luna: Annotated[str, Form(max_length=15)] = "",
    prag_avertizare: Annotated[str, Form(max_length=6)] = "80",
    plafon_p1: Annotated[str, Form(max_length=6)] = "1.5",
) -> Response:
    try:
        gateway.bugete.seteaza_implicite(
            db,
            _valori_buget(apeluri_zi, tokeni_zi, pret_umbra_zi, apeluri_luna, tokeni_luna, pret_umbra_luna),
            prag_avertizare=float(prag_avertizare.replace(",", ".")) / 100,
            plafon_p1=float(plafon_p1.replace(",", ".")), utilizator_id=u.utilizator_id,
        )  # fmt: skip
    except ValueError as exc:  # BugetInvalid moștenește ValueError; float() greșit la fel
        db.rollback()
        return _inapoi(
            eroare=str(exc)
            if isinstance(exc, gateway.bugete.BugetInvalid)
            else "Pragul și plafonul trebuie să fie numere."
        )
    return _inapoi("bugete")


@router.post("/evaluare/porneste", dependencies=[Depends(csrf_protect)])
def porneste_evaluare(u: Proprietar, db: DbSession, model: Annotated[str, Form(max_length=250)]) -> Response:
    try:
        gateway.evaluare.porneste(model)
    except LookupError:
        raise HTTPException(status_code=404, detail="Modelul nu există.") from None
    audit.record(
        db, "gateway.evaluare_pornita", obiect_tip="model", obiect_id=model, utilizator_id=u.utilizator_id,
        tenant_id=None, detalii={"model": model},
    )  # fmt: skip
    return _inapoi("evaluare")


@router.post("/evaluare/{rulare_id}/note", dependencies=[Depends(csrf_protect)])
def note_evaluare(
    u: Proprietar, db: DbSession, rulare_id: uuid.UUID, csv: Annotated[str, Form(max_length=20_000)]
) -> Response:
    try:
        gateway.evaluare.importa_note(db, rulare_id, csv, utilizator_id=u.utilizator_id)
    except gateway.evaluare.NotaInvalida as exc:
        db.rollback()
        return _inapoi(eroare=str(exc))
    return _inapoi("note")


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
