"""Ecranul „Creierul de brand” (F4.8, docs/18 §18.2, ecranul 6): pe client, compartimentele cu
intrările lor, versiunea aprobată și propunerile în așteptare, diferența între versiuni, editare
(CREEAZĂ o propunere nouă, nu suprascrie), aprobare / respingere / retragere, sursele și faptele.

Întâi pentru telefon: carduri și formulare, fără tabele late. CSRF pe orice schimbare; aprobarea,
respingerea și retragerea cer `creier.editeaza`, iar editarea (o propunere) cere `creier.editeaza`
sau `onboarding.completeaza`. Fiecare schimbare trece prin serviciul Creierului (audit în aceeași
tranzacție, poarta compartimentului, schema). Faptele rămân pe `/creier/fapte` (aprobare cu
verificarea citatului) și ofertele au propriul circuit (F4.6): aici nu se dublează, doar se leagă.
"""

import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app import cercetare, creier
from app.conturi import (
    DbSession,
    Permisiune,
    SesiuneCurenta,
    csrf_protect,
    current_user,
    lista_clienti,
    poate,
    require_permission,
    require_role,
)
from app.conturi.roluri import ROLURI_AGENTIE
from app.creier import fapte
from app.creier.compartimente import COMPARTIMENTE, Compartiment, ContinutInvalid, text_de_cautare
from app.onboarding import brief as _brief  # noqa: F401  (înregistrează schema, poarta și randarea brieful)
from app.onboarding import completare, fluxuri, ghid, piata, public, strategie  # noqa: F401
from app.panou.sabloane import pagina

router = APIRouter(prefix="/creier", tags=["creier"])
Agentie = Annotated[SesiuneCurenta, Depends(require_role(*ROLURI_AGENTIE))]
PoateAproba = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.CREIER_EDITEAZA))]
PoatePropune = Annotated[SesiuneCurenta, Depends(require_permission(Permisiune.ONBOARDING_COMPLETEAZA))]
DEDICATE = frozenset({Compartiment.REGISTRU_FAPTE, Compartiment.CATALOG_OFERTE})  # circuite proprii (F4.6)
MOTIV_MAXIM = 300
REZUMAT_CARACTERE = 220
MESAJE = {
    "editat": "Modificarea a fost salvată ca propunere nouă. Versiunea aprobată rămâne în vigoare "
    "până o aprobi pe cea nouă.",
    "aprobat": "Versiunea a fost aprobată.",
    "respins": "Propunerea a fost respinsă, cu motivul tău.",
    "retras": "Versiunea a fost retrasă.",
    "trimis": "Ciorna a fost trimisă spre aprobare.",
    "pornit": "Pasul s-a pornit. Reîncarcă pagina peste câteva secunde.",
    "concurent": "Concurentul a fost adăugat ca sursă.",
}
ETICHETE_STARE = {"ciorna": "ciornă", "propus": "propus", "aprobat": "aprobat", "retras": "retras"}


def poate_edita_propunere(u: SesiuneCurenta) -> bool:
    return poate(u.rol, Permisiune.CREIER_EDITEAZA) or poate(u.rol, Permisiune.ONBOARDING_COMPLETEAZA)


def _poate_propune(u: Annotated[SesiuneCurenta, Depends(current_user)]) -> SesiuneCurenta:
    if not poate_edita_propunere(u):
        raise HTTPException(status_code=403, detail="Acces interzis.")
    return u


PoateEdita = Annotated[SesiuneCurenta, Depends(_poate_propune)]


def _id(valoare: str) -> uuid.UUID:
    try:
        return uuid.UUID(valoare)
    except ValueError:
        raise HTTPException(status_code=404, detail="Nu există.") from None


def _client(db: DbSession, client_id: str):  # type: ignore[no-untyped-def]
    cid = _id(client_id)
    for c in lista_clienti(db):
        if c.id == cid:
            return c
    raise HTTPException(status_code=404, detail="Clientul nu există.")


def _compartiment(cod: str) -> Compartiment:
    try:
        return Compartiment(cod)
    except ValueError:
        raise HTTPException(status_code=404, detail="Compartiment necunoscut.") from None


def rezumat(continut: dict[str, Any], maxim: int = REZUMAT_CARACTERE) -> str:
    t = text_de_cautare(continut, maxim=maxim + 1)
    return t if len(t) <= maxim else t[:maxim].rstrip() + "…"


# --- câmpurile unui conținut ca formular (editare pe telefon: text, un rând pe element, JSON pentru
# structuri)


def campuri_formular(continut: dict[str, Any]) -> list[dict[str, Any]]:
    iesire = []
    for k in sorted(continut):
        v = continut[k]
        if isinstance(v, str):
            tip, valoare = "text", v
        elif isinstance(v, list) and all(isinstance(x, str) for x in v):
            tip, valoare = "lista", "\n".join(v)
        elif isinstance(v, bool) or v is None:
            tip, valoare = "json", json.dumps(v, ensure_ascii=False)
        elif isinstance(v, int | float):
            tip, valoare = "numar", str(v)
        else:
            tip, valoare = "json", json.dumps(v, ensure_ascii=False, indent=1)
        iesire.append(
            {"nume": k, "tip": tip, "valoare": valoare, "lung": tip in ("json", "lista") or len(valoare) > 80}
        )
    return iesire


def continut_din_formular(original: dict[str, Any], form: Any) -> dict[str, Any]:
    """Reface conținutul din câmpurile formularului, păstrând tipul fiecărui câmp. `ValueError` cu mesaj."""
    nou: dict[str, Any] = {}
    for k, v in original.items():
        brut = form.get(f"c_{k}")
        if brut is None:
            nou[k] = v
            continue
        brut = str(brut)
        if isinstance(v, str):
            nou[k] = brut.strip()
        elif isinstance(v, list) and all(isinstance(x, str) for x in v):
            nou[k] = [r.strip() for r in brut.splitlines() if r.strip()]
        elif isinstance(v, bool) or v is None or isinstance(v, dict | list):
            try:
                nou[k] = json.loads(brut)
            except json.JSONDecodeError:
                raise ValueError(f"câmpul „{k}” nu este un JSON valid") from None
        elif isinstance(v, int):
            try:
                nou[k] = int(brut)
            except ValueError:
                raise ValueError(f"câmpul „{k}” trebuie să fie un număr întreg") from None
        else:
            try:
                nou[k] = float(brut.replace(",", "."))
            except ValueError:
                raise ValueError(f"câmpul „{k}” trebuie să fie un număr") from None
    return nou


def afisare_valoare(v: Any) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return "; ".join(v)
    return json.dumps(v, ensure_ascii=False, indent=1)


# --- pagini


def _pagina_client(
    request: Request, u: SesiuneCurenta, db: DbSession, client_id: str, *, status: int = 200, **extra: object
) -> Response:
    c = _client(db, client_id)
    rez = creier.rezumat_pe_compartimente(db, c.id)
    carduri = [
        {"info": info, "rez": rez.get(cod), "dedicat": cod in DEDICATE} for cod, info in COMPARTIMENTE.items()
    ]
    asteptare = [
        {"intrare": i, "versiune": v, "nume": COMPARTIMENTE[Compartiment(i.compartiment)].nume,
         "text": rezumat(v.continut, 120)}
        for i, v in creier.propuneri_in_asteptare(db, c.id)
        if i.compartiment != Compartiment.REGISTRU_FAPTE.value  # faptele se aprobă pe ecranul lor
    ]  # fmt: skip
    return pagina(
        request, u, "panou/creier_client.html", tab="meniu", status=status, client=c, carduri=carduri,
        asteptare=asteptare, surse=cercetare.surse(db, c.id), statute=cercetare.STATUTE,
        fapte_propuse=len(fapte.propuneri(db, tenant_id=c.id)),
        poate_propune=poate_edita_propunere(u), poate_completa=poate(u.rol,
        Permisiune.ONBOARDING_COMPLETEAZA), **extra,
    )  # fmt: skip


@router.get("/client")
def clienti(request: Request, u: Agentie, db: DbSession) -> Response:
    return pagina(request, u, "panou/creier_clienti.html", tab="meniu", clienti=lista_clienti(db))


@router.get("/client/{client_id}")
def client_vezi(request: Request, u: Agentie, db: DbSession, client_id: str, mesaj: str = "") -> Response:
    return _pagina_client(request, u, db, client_id, mesaj=MESAJE.get(mesaj, ""))


@router.get("/client/{client_id}/{compartiment}")
def compartiment_vezi(
    request: Request, u: Agentie, db: DbSession, client_id: str, compartiment: str, mesaj: str = ""
) -> Response:
    c = _client(db, client_id)
    comp = _compartiment(compartiment)
    if comp is Compartiment.REGISTRU_FAPTE:  # faptele au ecranul lor (aprobare cu sursa și citatul exact)
        return RedirectResponse(f"/creier/fapte?client={c.id}", status_code=303)
    randuri = []
    for i, aprobata in creier.lista(db, tenant_id=c.id, compartiment=comp):
        asteptare = [v for v in creier.istoric(db, i.id) if v.stare == "propus"]
        randuri.append({"intrare": i, "aprobata": aprobata, "asteptare": asteptare,
                        "text": rezumat(aprobata.continut) if aprobata else ""})  # fmt: skip
    return pagina(
        request, u, "panou/creier_compartiment.html", tab="meniu", client=c, info=COMPARTIMENTE[comp],
        comp=comp,
        randuri=randuri, dedicat=comp in DEDICATE, mesaj=MESAJE.get(mesaj, ""),
    )  # fmt: skip


def _pagina_intrare(
    request: Request, u: SesiuneCurenta, db: DbSession, intrare_id: str, *, a: int = 0, b: int = 0,
    status: int = 200, **extra: object,
) -> Response:  # fmt: skip
    iid = _id(intrare_id)
    try:
        i = creier.intrare(db, iid)
    except creier.IntrareInexistenta:
        raise HTTPException(status_code=404, detail="Intrarea nu există.") from None
    comp = Compartiment(i.compartiment)
    versiuni = creier.istoric(db, iid)
    aprobata = next((v for v in versiuni if v.stare == "aprobat"), None)
    asteptare = [v for v in versiuni if v.stare == "propus"]
    ciorne = [v for v in versiuni if v.stare == "ciorna"]
    baza = aprobata or (versiuni[-1] if versiuni else None)
    # diferența: cea cerută (a, b) sau, implicit, versiunea aprobată față de ultima propunere
    schimbari: list[Any] = []
    if not a and not b and aprobata and asteptare:
        a, b = aprobata.nr, asteptare[-1].nr
    if a and b:
        try:
            schimbari = creier.diferenta_versiuni(db, iid, a, b)
        except creier.VersiuneInexistenta:
            raise HTTPException(status_code=404, detail="Versiunea nu există.") from None
    client_nume = next((c.nume for c in lista_clienti(db) if c.id == i.tenant_id), "–")
    return pagina(
        request, u, "panou/creier_intrare.html", tab="meniu", status=status, intrare=i, comp=comp,
        info=COMPARTIMENTE[comp], client_nume=client_nume, versiuni=versiuni, aprobata=aprobata,
        asteptare=asteptare,
        ciorne=ciorne, schimbari=schimbari, diff_a=a, diff_b=b, campuri=campuri_formular(baza.continut)
        if baza else [],
        dedicat=comp in DEDICATE, poate_aproba=poate(u.rol, Permisiune.CREIER_EDITEAZA),
        poate_propune=poate_edita_propunere(u), afisare=afisare_valoare, etichete_stare=ETICHETE_STARE,
        **extra,
    )  # fmt: skip


@router.get("/intrare/{intrare_id}")
def intrare_vezi(
    request: Request, u: Agentie, db: DbSession, intrare_id: str, a: int = 0, b: int = 0, mesaj: str = ""
) -> Response:
    return _pagina_intrare(request, u, db, intrare_id, a=a, b=b, mesaj=MESAJE.get(mesaj, ""))


def _eroare_creier(exc: Exception) -> str:
    probleme = getattr(exc, "probleme", None)
    return "; ".join(probleme[:6]) if probleme else str(exc)


@router.post("/intrare/{intrare_id}/editeaza", dependencies=[Depends(csrf_protect)])
async def editeaza(request: Request, u: PoateEdita, db: DbSession, intrare_id: str) -> Response:
    iid = _id(intrare_id)
    try:
        i = creier.intrare(db, iid)
    except creier.IntrareInexistenta:
        raise HTTPException(status_code=404, detail="Intrarea nu există.") from None
    if Compartiment(i.compartiment) in DEDICATE:
        raise HTTPException(status_code=409, detail="Faptele și ofertele se editează în circuitul lor.")
    form = await request.form()
    motiv = str(form.get("motiv", "")).strip()[:500]
    versiuni = creier.istoric(db, iid)
    baza = next((v for v in versiuni if v.stare == "aprobat"), versiuni[-1])
    try:
        continut = continut_din_formular(baza.continut, form)
        creier.propune_schimbare(
            db, iid, continut=continut, sursa=creier.Sursa(creier.SursaTip.OM),
            motiv=motiv or "editat în panou", utilizator_id=u.utilizator_id,
        )  # fmt: skip
    except (ValueError, ContinutInvalid, creier.RegulaCreier) as exc:
        db.rollback()
        return _pagina_intrare(
            request,
            u,
            db,
            intrare_id,
            status=422,
            eroare="Modificarea nu a fost salvată: " + _eroare_creier(exc),
        )
    return RedirectResponse(f"/creier/intrare/{iid}?mesaj=editat", status_code=303)


def _decide(
    db: DbSession, request: Request, u: SesiuneCurenta, intrare_id: str, fa: Any, mesaj: str
) -> Response:
    iid = _id(intrare_id)
    try:
        fa(iid)
    except creier.IntrareInexistenta:
        raise HTTPException(status_code=404, detail="Intrarea nu există.") from None
    except (creier.TranzitieNepermisa, creier.RegulaCreier, creier.VersiuneInexistenta) as exc:
        db.rollback()
        return _pagina_intrare(request, u, db, intrare_id, status=409 if not getattr(exc, "probleme",
        None) else 422,
                               eroare="Nu s-a putut: " + _eroare_creier(exc))  # fmt: skip
    return RedirectResponse(f"/creier/intrare/{iid}?mesaj={mesaj}", status_code=303)


@router.post("/intrare/{intrare_id}/aproba", dependencies=[Depends(csrf_protect)])
def aproba(
    request: Request, u: PoateAproba, db: DbSession, intrare_id: str, versiune: Annotated[int, Form(ge=1)]
) -> Response:
    return _decide(
        db,
        request,
        u,
        intrare_id,
        lambda i: creier.aproba(db, i, versiune, utilizator_id=u.utilizator_id),
        "aprobat",
    )


@router.post("/intrare/{intrare_id}/trimite", dependencies=[Depends(csrf_protect)])
def trimite(
    request: Request, u: PoateEdita, db: DbSession, intrare_id: str, versiune: Annotated[int, Form(ge=1)]
) -> Response:
    return _decide(
        db,
        request,
        u,
        intrare_id,
        lambda i: creier.trimite_spre_aprobare(db, i, versiune, utilizator_id=u.utilizator_id),
        "trimis",
    )


def _cu_motiv(
    db: DbSession, request: Request, u: SesiuneCurenta, intrare_id: str, versiune: int, motiv: str,
    cauza: Any, mesaj: str,
) -> Response:  # fmt: skip
    if len(motiv.strip()) < 3:
        return _pagina_intrare(
            request, u, db, intrare_id, status=422, eroare="Scrie motivul (cel puțin 3 caractere)."
        )
    return _decide(
        db, request, u, intrare_id,
        lambda i: creier.retrage(db, i, versiune, utilizator_id=u.utilizator_id, motiv=motiv.strip(),
        cauza=cauza), mesaj,
    )  # fmt: skip


@router.post("/intrare/{intrare_id}/respinge", dependencies=[Depends(csrf_protect)])
def respinge(
    request: Request, u: PoateAproba, db: DbSession, intrare_id: str, versiune: Annotated[int, Form(ge=1)],
    motiv: Annotated[str, Form(max_length=MOTIV_MAXIM)] = "",
) -> Response:  # fmt: skip
    return _cu_motiv(db, request, u, intrare_id, versiune, motiv, creier.CauzaRetragere.RESPINS, "respins")


@router.post("/intrare/{intrare_id}/retrage", dependencies=[Depends(csrf_protect)])
def retrage(
    request: Request, u: PoateAproba, db: DbSession, intrare_id: str, versiune: Annotated[int, Form(ge=1)],
    motiv: Annotated[str, Form(max_length=MOTIV_MAXIM)] = "",
) -> Response:  # fmt: skip
    return _cu_motiv(db, request, u, intrare_id, versiune, motiv, creier.CauzaRetragere.RETRAS, "retras")


# --- pașii de pregătire a Creierului, pornitți din ecran (aceleași fluxuri durabile ca în teste)


def _pas(client_id: str, db: DbSession, u: SesiuneCurenta, nume: str) -> Response:
    c = _client(db, client_id)
    tenant = c.id
    db.commit()
    cheie = f"{nume}:{tenant}:{uuid.uuid4().hex[:8]}"
    if nume == "ton":
        fluxuri.trimite_propunerea_de_ton(tenant, u.utilizator_id, cheie=cheie)
    elif nume == "public":
        fluxuri.trimite_profilul_de_public(tenant, u.utilizator_id, cheie=cheie)
    elif nume == "insight":
        fluxuri.trimite_brief_insight(tenant, u.utilizator_id, cheie=cheie)
    elif nume == "strategie":
        fluxuri.trimite_strategia(tenant, u.utilizator_id, cheie=cheie)
    elif nume == "citate":
        with_surse = [
            s.id for s in cercetare.surse(db, tenant) if cercetare.STATUTE[s.statut].reutilizare_text
        ]
        for sid in with_surse:
            fluxuri.trimite_extragerea_citatelor(tenant, sid, cheie=f"{cheie}:{sid}")
    elif nume == "afirmatii":
        for s in piata.concurenti(db, tenant):
            fluxuri.trimite_extragerea(tenant, s.id, "afirmatii", cheie=f"{cheie}:{s.id}")
    else:
        raise HTTPException(status_code=404, detail="Pas necunoscut.")
    return RedirectResponse(f"/creier/client/{tenant}?mesaj=pornit", status_code=303)


@router.post("/client/{client_id}/pas/{nume}", dependencies=[Depends(csrf_protect)])
def pas(request: Request, u: PoatePropune, db: DbSession, client_id: str, nume: str) -> Response:
    return _pas(client_id, db, u, nume)


@router.post("/client/{client_id}/concurent", dependencies=[Depends(csrf_protect)])
def concurent(
    request: Request, u: PoatePropune, db: DbSession, client_id: str, nume: Annotated[str,
    Form(max_length=200)],
    adresa: Annotated[str, Form(max_length=500)] = "",
) -> Response:  # fmt: skip
    c = _client(db, client_id)
    try:
        piata.adauga_concurent(
            db, tenant_id=c.id, nume=nume, url=adresa.strip() or None, utilizator_id=u.utilizator_id
        )
    except (cercetare.ColectareInvalida, cercetare.SursaInterzisa, creier.RegulaCreier) as exc:
        db.rollback()
        return _pagina_client(
            request, u, db, client_id, status=422, eroare=f"Concurentul nu a fost adăugat: {exc}"
        )
    return RedirectResponse(f"/creier/client/{c.id}?mesaj=concurent", status_code=303)
