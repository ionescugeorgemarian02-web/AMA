"""Harta pieței și brieful de insight (F4.10, C7, C8, docs/12 §12.6).

1. *Concurenții sunt surse* (statutul „site public al concurenței”): 3–5 pe client. Site-urile se
citesc cu colectorul
   existent (robots.txt, SSRF, limite), iar o sursă manuală primește text lipit. Textul concurenței se
   ANALIZEAZĂ, nu se
   reutilizează (statutul îl scoate din pachetul de context).
2. *Afirmațiile concurenței* (ofertă, preț, mesaj) se extrag pasaj cu pasaj, prin gateway (profilul
`clasificare`), fiecare
   cu citatul exact; același verificator determinist ca la fapte (citat literal în pasaj, cifra în
   citat). Ce trece devine
   intrare `insight_piata` (`afirm-<amprentă>`), cu pasajul și URL-ul sursă, aprobată de sistem.
3. *Brieful de insight* (profilul `strategie`, care se amână, nu se degradează) sintetizează pe o
pagină ce spun concurenții,
   unde sunt spațiile libere și ce recomandăm. FIECARE afirmație poartă trimiteri (`afirmatie:<id>` sau
   `pasaj:<id>`) către
   sursele ei. Poarta compartimentului blochează trimiterea spre aprobare și aprobarea unui brief cu o
   afirmație fără
   trimitere, cu o trimitere care nu duce nicăieri sau al cărui sondaj de citate pică.
4. *Verificarea prin sondaj*: un eșantion determinist de trimiteri (`sondaj.esantion`) se reverifică
LITERAL în sursă.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app import cercetare, creier, gateway
from app.creier.compartimente import Compartiment, SursaTip
from app.db import sesiune_tenant
from app.onboarding import completare, extractie, prompturi, sondaj
from app.onboarding.extractie import RezultatPasaj
from app.operare import audit
from app.operare.motor import Prioritate

STATUT_CONCURENTA = "site_concurenta"
MIN_CONCURENTI, MAX_CONCURENTI = 3, 5
REFERINTA_AFIRMATII = "onboarding.extrage_afirmatii@1"
REFERINTA_INSIGHT = "onboarding.brief_insight@1"
CHEIE_BRIEF = "brief-insight"
PREFIXE = ("afirmatie", "pasaj")
FRACTIE_SONDAJ, MINIM_SONDAJ = 0.3, 5


class RegulaPiata(creier.RegulaCreier):
    pass


# --- concurenți ca surse


def concurenti(db: Session, tenant_id: uuid.UUID) -> list[cercetare.SursaColectare]:
    return [s for s in cercetare.surse(db, tenant_id) if s.statut == STATUT_CONCURENTA]


def adauga_concurent(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    nume: str,
    url: str | None = None,
    utilizator_id: uuid.UUID | None = None,
) -> cercetare.SursaColectare:
    """Un concurent nou ca sursă (site cu crawl politicos, dacă are adresă; altfel material lipit). Cel
    mult 5."""
    if len(concurenti(db, tenant_id)) >= MAX_CONCURENTI:
        raise RegulaPiata(f"cel mult {MAX_CONCURENTI} concurenți pe client")
    return cercetare.creeaza_sursa(
        db, tenant_id=tenant_id, tip="site" if url else "manual", statut_cod=STATUT_CONCURENTA,
        nume=nume, url=url,
        utilizator_id=utilizator_id,
    )  # fmt: skip


# --- afirmațiile concurenței


class AfirmatieExtrasa(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tip: Literal["oferta", "pret", "mesaj"]
    afirmatie: str = Field(description="Ce afirmă concurentul, într-o propoziție", max_length=400)
    citat: str = Field(description="Citatul EXACT din text care o susține", max_length=600)
    valoare_numar: str | None = Field(
        default=None, description="Prețul / cifra exactă, dacă există", max_length=40
    )
    moneda: str | None = Field(default=None, max_length=3)


class PropunereAfirmatii(gateway.Iesire):
    afirmatii: list[AfirmatieExtrasa] = Field(default_factory=list, max_length=15)


def cheie_afirmatie(sursa_id: uuid.UUID, afirmatie: str) -> str:
    return (
        "afirm-"
        + hashlib.sha256(f"{sursa_id}\x1f{' '.join(afirmatie.lower().split())}".encode()).hexdigest()[:24]
    )


def motiv_respingere(a: AfirmatieExtrasa, text_pasaj: str) -> str | None:
    motiv = creier.verifica_propunere(a.citat, text_pasaj, valoare_numar=a.valoare_numar)
    if motiv is not None:
        return motiv
    if len(a.afirmatie.strip()) < 10:
        return "afirmatie_invalida"
    if a.moneda is not None and not (len(a.moneda) == 3 and a.moneda.isalpha() and a.moneda.isupper()):
        return "moneda_invalida"
    return None


def extrage_din_pasaj(tenant_id: uuid.UUID, pasaj_id: uuid.UUID) -> RezultatPasaj:
    with sesiune_tenant(tenant_id) as db:
        p = db.get(creier.Pasaj, pasaj_id)
        if p is None or extractie.deja_extras(db, pasaj_id, REFERINTA_AFIRMATII):
            return RezultatPasaj(pasaj_id)
        d = db.get(cercetare.Document, p.document_id)
        s = db.get(cercetare.SursaColectare, p.sursa_id)
        if s is None or s.statut != STATUT_CONCURENTA:
            return RezultatPasaj(pasaj_id)  # doar sursele de concurență intră în harta pieței
        r = RezultatPasaj(pasaj_id)
        try:
            ap = gateway.apeleaza(
                db,
                prompt=REFERINTA_AFIRMATII,
                variabile={"concurent": s.nume, "pasaj": gateway.marcheaza_extern(p.text, sursa="pagina")},
                schema=PropunereAfirmatii,
                tenant_id=tenant_id,
                componenta="onboarding.extrage_afirmatii",
                prioritate=Prioritate.P3,
                max_tokeni=2500,
                demasca=True,
            )
        except gateway.IesireInvalida:
            r.respinse.append({"motiv": "iesire_invalida"})
            extractie.noteaza(db, tenant_id, p, REFERINTA_AFIRMATII, r, None)
            return r
        iesire = ap.iesire
        if not isinstance(iesire, PropunereAfirmatii):
            raise TypeError("ieșirea nu respectă schema promptului")
        for a in iesire.afirmatii:
            motiv = motiv_respingere(a, p.text)
            if motiv is None:
                citat = " ".join(a.citat.split())
                sursa = creier.Sursa(
                    SursaTip.PASAJ, ref=str(pasaj_id), citat=citat,
                    detalii={"document_id": str(p.document_id), "url": d.url if d else None, "pozitie":
                    p.pozitie,
                             "car_inceput": p.car_inceput, "car_sfarsit": p.car_sfarsit,
                             "sursa_id": str(s.id)},
                )  # fmt: skip
                cheie = cheie_afirmatie(s.id, a.afirmatie)
                if creier.gaseste_intrare(
                    db, tenant_id=tenant_id, compartiment=Compartiment.INSIGHT_PIATA, cheie=cheie
                ):
                    r.duplicate += 1
                    continue
                valoare = {"numar": a.valoare_numar, "moneda": a.moneda} if a.valoare_numar else None
                i, v = creier.creeaza_intrare(
                    db, tenant_id=tenant_id, compartiment=Compartiment.INSIGHT_PIATA, cheie=cheie,
                    continut={"tip": "afirmatie", "concurent": s.nume, "categorie": a.tip,
                              "afirmatie": a.afirmatie.strip(), "valoare": valoare},
                    sursa=sursa,
                )  # fmt: skip
                creier.aproba(db, i.id, v.nr, utilizator_id=None, prin_sistem=True)
                r.propuse += 1
                continue
            r.respinse.append({"motiv": motiv, "afirmatie": a.afirmatie[:160], "citat": a.citat[:160]})
        extractie.noteaza(db, tenant_id, p, REFERINTA_AFIRMATII, r, ap.model)
    return r


@dataclass(frozen=True)
class Afirmatie:
    intrare_id: uuid.UUID
    versiune: int
    concurent: str
    categorie: str
    afirmatie: str
    valoare: dict[str, Any] | None
    citat: str
    url: str | None
    pasaj_id: str | None


def afirmatii(db: Session, tenant_id: uuid.UUID) -> list[Afirmatie]:
    """Afirmațiile aprobate ale concurenței, cu sursa lor (pasaj, URL, citat)."""
    rezultat = []
    for i, v in creier.lista(db, tenant_id=tenant_id, compartiment=Compartiment.INSIGHT_PIATA):
        if v is None or v.continut.get("tip") != "afirmatie":
            continue
        c = v.continut
        rezultat.append(
            Afirmatie(
                i.id,
                v.nr,
                c["concurent"],
                c["categorie"],
                c["afirmatie"],
                c.get("valoare"),
                v.sursa_citat or "",
                (v.sursa_detalii or {}).get("url"),
                v.sursa_ref,
            )
        )
    return rezultat


# --- brieful de insight


class AfirmatieInsight(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=15, max_length=500)
    surse: list[str] = Field(default_factory=list, max_length=6)  # „afirmatie:<id>” sau „pasaj:<id>”


class BriefInsight(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tip: Literal["brief_insight"] = "brief_insight"
    titlu: str = Field(min_length=5, max_length=120)
    rezumat: AfirmatieInsight
    harta: list[AfirmatieInsight] = Field(min_length=3, max_length=12)  # cine spune ce
    spatii_libere: list[AfirmatieInsight] = Field(min_length=1, max_length=6)
    recomandari: list[AfirmatieInsight] = Field(min_length=1, max_length=5)


class PropunereInsight(gateway.Iesire):
    brief: BriefInsight


def enunturi(c: dict[str, Any]) -> list[dict[str, Any]]:
    """Toate enunțurile brieful (rezumat, hartă, spații libere, recomandări), ca dicționare."""
    out: list[dict[str, Any]] = []
    if isinstance(c.get("rezumat"), dict):
        out.append(c["rezumat"])
    for k in ("harta", "spatii_libere", "recomandari"):
        out += [x for x in c.get(k, []) if isinstance(x, dict)]
    return out


def trimitere_valida(t: str) -> bool:
    prefix, _, ref = t.partition(":")
    if prefix not in PREFIXE:
        return False
    try:
        uuid.UUID(ref)
    except ValueError:
        return False
    return True


def fara_trimitere(c: dict[str, Any]) -> list[str]:
    """Nucleu pur: enunțurile fără nicio trimitere sau cu trimiteri într-o formă nepermisă."""
    probleme = []
    for e in enunturi(c):
        surse = e.get("surse") or []
        if not surse:
            probleme.append(f"afirmație fără trimitere la o sursă: „{str(e.get('text', ''))[:70]}”")
        elif not all(isinstance(t, str) and trimitere_valida(t) for t in surse):
            probleme.append(f"trimitere într-o formă nepermisă: „{str(e.get('text', ''))[:70]}”")
    return probleme


def toate_trimiterile(c: dict[str, Any]) -> list[str]:
    return sorted({t for e in enunturi(c) for t in (e.get("surse") or []) if isinstance(t, str)})


@dataclass
class RaportSondaj:
    verificate: list[str] = field(default_factory=list)
    picate: list[dict[str, str]] = field(default_factory=list)
    inexistente: list[str] = field(default_factory=list)

    @property
    def trece(self) -> bool:
        return not self.picate and not self.inexistente


def _rezolva(db: Session, tenant_id: uuid.UUID, trimitere: str) -> tuple[str | None, str | None]:
    """(citat, textul pasajului) pentru o trimitere, sau (None, None) dacă nu duce nicăieri."""
    prefix, _, ref = trimitere.partition(":")
    try:
        rid = uuid.UUID(ref)
    except ValueError:
        return None, None
    if prefix == "pasaj":
        p = db.get(creier.Pasaj, rid)
        return ("", p.text) if p is not None and p.tenant_id == tenant_id else (None, None)
    try:
        i = creier.intrare(db, rid) if prefix == "afirmatie" else None
    except creier.IntrareInexistenta:
        return None, None
    if i is None or i.tenant_id != tenant_id or i.compartiment != Compartiment.INSIGHT_PIATA.value:
        return None, None
    v = creier.versiune_aprobata(db, rid)
    if v is None or v.continut.get("tip") != "afirmatie" or not v.sursa_ref:
        return None, None
    try:
        p = db.get(creier.Pasaj, uuid.UUID(v.sursa_ref))
    except ValueError:
        return None, None
    return (v.sursa_citat or ""), (p.text if p is not None and p.tenant_id == tenant_id else None)


def verifica_prin_sondaj(
    db: Session,
    tenant_id: uuid.UUID,
    c: dict[str, Any],
    *,
    fractie: float = FRACTIE_SONDAJ,
    minim: int = MINIM_SONDAJ,
) -> RaportSondaj:
    """Reverifică LITERAL, pe un eșantion determinist al trimiterilor, că citatul fiecărei afirmații se
    află în pasajul ei;
    trimiterile care nu duc la nimic sunt raportate separat. Samânța este amprenta conținutului."""
    samanta = hashlib.sha256(json.dumps(c, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    raport = RaportSondaj()
    for t in sondaj.esantion(toate_trimiterile(c), samanta=samanta, fractie=fractie, minim=minim):
        citat, text_pasaj = _rezolva(db, tenant_id, t)
        if text_pasaj is None:
            raport.inexistente.append(t)
        elif citat and not creier.citat_in_text(citat, text_pasaj):
            raport.picate.append({"trimitere": t, "citat": citat[:120]})
        else:
            raport.verificate.append(t)
    return raport


def probleme_poarta(db: Session, tenant_id: uuid.UUID | None, c: dict[str, Any]) -> list[str]:
    """Poarta brieful de insight: trimiteri peste tot, trimiteri care duc la surse existente, sondaj de
    citate trecut."""
    probleme = fara_trimitere(c)
    if probleme or tenant_id is None:
        return probleme
    raport = verifica_prin_sondaj(db, tenant_id, c)
    probleme += [f"trimitere care nu duce la nicio sursă: {t}" for t in raport.inexistente]
    probleme += [f"citatul nu se regăsește în sursă (sondaj): {x['trimitere']}" for x in raport.picate]
    return probleme


def _poarta(db: Session, tenant_id: uuid.UUID | None, c: dict[str, Any]) -> list[str]:
    return probleme_poarta(db, tenant_id, c) if c.get("tip") == "brief_insight" else []


def propune_brief(
    db: Session, *, tenant_id: uuid.UUID, utilizator_id: uuid.UUID | None
) -> tuple[uuid.UUID, int]:
    """Brieful de insight din afirmațiile concurenței și brieful aprobat. Cere cel puțin 3 concurenți
    cu afirmații. Dacă
    modelul lasă o afirmație fără trimitere, brieful se salvează ca CIORNĂ și nu poate fi trimis
    (poarta). Ridică
    `Amanat` (profilul `strategie` se amână, nu se degradează)."""
    toate = afirmatii(db, tenant_id)
    nume = {a.concurent for a in toate}
    if len(nume) < MIN_CONCURENTI:
        raise RegulaPiata(
            f"harta pieței cere afirmații de la cel puțin {MIN_CONCURENTI} concurenți (sunt {len(nume)})"
        )
    continut_brief, versiune = completare.brief_aprobat(db, tenant_id)
    from app.onboarding import brief as brief_mod

    linii = "\n".join(
        f"[afirmatie:{a.intrare_id}] {a.concurent} ({a.categorie}): {a.afirmatie}" for a in toate[:80]
    )
    prompturi.asigura()
    r = gateway.apeleaza(
        db,
        prompt=REFERINTA_INSIGHT,
        variabile={
            "brief": gateway.marcheaza_extern(
                brief_mod.text_pentru_prompt(continut_brief), sursa="raspuns_client", max_caractere=20_000
            ),
            "afirmatii": gateway.marcheaza_extern(linii, sursa="pagina", max_caractere=40_000),
        },
        schema=PropunereInsight,
        tenant_id=tenant_id,
        componenta="onboarding.brief_insight",
        prioritate=Prioritate.P2,
        max_tokeni=3500,
    )
    iesire = r.iesire
    if not isinstance(iesire, PropunereInsight):
        raise TypeError("ieșirea nu respectă schema promptului")
    continut = iesire.brief.model_dump(mode="json")
    oferite = {f"afirmatie:{a.intrare_id}" for a in toate}
    for e in enunturi(
        continut
    ):  # trimiterile inventate (neoferite modelului) se scot: rămâne enunț fără trimitere
        e["surse"] = [t for t in e["surse"] if t in oferite]
    sursa = creier.Sursa(
        SursaTip.SISTEM,
        detalii={"brief_versiune": versiune, "afirmatii": len(toate), "concurenti": len(nume)},
    )
    complet = not probleme_poarta(db, tenant_id, continut)
    existenta = creier.gaseste_intrare(
        db, tenant_id=tenant_id, compartiment=Compartiment.INSIGHT_PIATA, cheie=CHEIE_BRIEF
    )
    if existenta is None:
        i, v = creier.creeaza_intrare(
            db, tenant_id=tenant_id, compartiment=Compartiment.INSIGHT_PIATA, cheie=CHEIE_BRIEF,
            continut=continut,
            sursa=sursa, propune=complet,
        )  # fmt: skip
        iid, nr = i.id, v.nr
    else:
        v = creier.propune_schimbare(db, existenta.id, continut=continut, sursa=sursa, propune=complet)
        iid, nr = existenta.id, v.nr
    audit.record(
        db, "onboarding.brief_insight_propus", obiect_tip="creier_intrare", obiect_id=iid,
        utilizator_id=utilizator_id, tenant_id=tenant_id, detalii={"versiune": nr, "complet": complet},
    )  # fmt: skip
    return iid, nr


def randeaza(c: dict[str, Any]) -> str | None:
    if c.get("tip") != "brief_insight":
        return None
    rezumat = c.get("rezumat", {}).get("text", "")
    sectiuni = (
        ("Harta pieței (cine spune ce)", "harta"),
        ("Spații libere", "spatii_libere"),
        ("Recomandări", "recomandari"),
    )
    corp = "\n".join(
        f"{titlu}: " + " ".join(f"- {e['text']}" for e in c.get(cheie, [])) for titlu, cheie in sectiuni
    )
    return f"{c.get('titlu', '')}\n{rezumat}\n{corp}"


creier.inregistreaza_poarta(Compartiment.INSIGHT_PIATA, _poarta)
creier.inregistreaza_randare(Compartiment.INSIGHT_PIATA, randeaza)
creier.inregistreaza_cere_om(Compartiment.INSIGHT_PIATA, lambda c: c.get("tip") == "brief_insight")
