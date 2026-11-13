"""G2 Verificatorul de fapte (docs/09 §9.3, §9.4): mecanismul anti-halucinații.

V1 (determinist): extrage din text afirmațiile verificabile (`afirmatii.extrage`) și le potrivește cu
registrul de fapte
APROBAT și valabil la data publicării (`creier.fapte.pentru_context`, `creier.oferte.pentru_context`) și cu
citatele din
surse de cercetare verificate literal. Cifrele și prețurile se compară EXACT, fără model (`acoperire`). O
afirmație
neacoperită sau diferită de registru BLOCHEAZĂ livrabilul. Platforma nu „verifică pe internet” în locul
registrului.

Fapt lipsă: dacă livrabilul declară ce fapte îi sunt necesare (`campuri["fapte_necesare"]`: `[{"tip",
"subiect"}]`) sau autorul
a cerut explicit un fapt (`campuri["intrebari_autor"]`: `[text]`) și registrul nu îl are, livrabilul se
oprește cu o ÎNTREBARE
către client (o înregistrare vizibilă, `intrebari.py`), nu cu o presupunere.

V3 (opțional, prin gateway): afirmațiile NESTRUCTURATE (fără cifre) pe care extractorul nu le prinde.
Modelul propune
fragmentul și faptul care îl acoperă; verificarea e deterministă: fragmentul trebuie să apară literal în
text, iar faptul să existe în
registrul trimis. Fără fapt acoperitor, afirmația blochează.
"""

import datetime as dt
import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app import creier, gateway
from app.creier.fapte import FaptPropus
from app.creier.oferte import OfertaContext
from app.validare import acoperire, afirmatii, judecator, registru
from app.validare.acoperire import Acoperire, IntrareRegistru, Registru
from app.validare.date_validare import incarca
from app.validare.intrare import Intrare
from app.validare.probleme import Problema, verdict_din_probleme
from app.validare.verdict import Treapta, Verdict

COD = "G2"
VERSIUNE = "1"
VERSIUNE_V3 = "1"
ETICHETE_FAPT = {
    "pret": "prețul",
    "caracteristica": "caracteristica",
    "cifra": "cifra",
    "garantie": "garanția",
    "termen": "termenul",
    "program": "programul",
    "date_contact": "datele de contact",
    "adresa": "adresa",
    "mentiune_legala": "mențiunea legală",
    "afirmatie_performanta": "afirmația de performanță",
}


def _dec(v: Any) -> Decimal | None:
    try:
        return None if v is None else Decimal(str(v))
    except InvalidOperation:
        return None


def _moneda(v: Any) -> str:
    return str(v or "RON").upper()


def _date_valabilitate(*momente: dt.datetime | None) -> list[tuple[int, int, int]]:
    return [(m.day, m.month, m.year) for m in momente if m is not None]


def din_fapt(f: FaptPropus) -> IntrareRegistru:
    val = f.valoare or {}
    numar = _dec(val.get("numar"))
    return acoperire.intrare_din_texte(
        str(f.intrare_id),
        "fapt",
        f.subiect,
        [f.afirmatie, str(val.get("text") or ""), str(val.get("unitate") or "")],
        numar=numar,
        moneda=_moneda(val["moneda"])
        if val.get("moneda")
        else ("RON" if f.tip == "pret" and numar else None),
        unitate=str(val.get("unitate") or "") or None,
        tip=f.tip,
        date_valabilitate=_date_valabilitate(f.valabil_de_la, f.valabil_pana_la),
    )


def din_oferta(o: OfertaContext) -> IntrareRegistru:
    pret = _dec(o.pret.get("numar"))
    ref = _dec((o.pret_referinta or {}).get("numar"))
    return acoperire.intrare_din_texte(
        str(o.intrare_id),
        "oferta",
        o.nume,
        [o.descriere, o.conditii, o.garantie, o.tip],
        tip="oferta",
        pret=(pret, _moneda(o.pret.get("moneda"))) if pret is not None else None,
        pret_referinta=(ref, _moneda((o.pret_referinta or {}).get("moneda"))) if ref is not None else None,
        date_valabilitate=_date_valabilitate(o.valabil_de_la, o.valabil_pana_la),
    )


def surse_citate(intrare: Intrare) -> tuple[list[IntrareRegistru], list[Problema]]:
    """Citatele din `campuri["surse_citate"]` (`[{"pasaj_id", "citat"}]`): un citat verificat literal în
    pasajul clientului
    devine intrare în registru; un citat care NU apare în pasaj este o sursă inventată și blochează."""
    intrari: list[IntrareRegistru] = []
    probleme: list[Problema] = []
    for s in intrare.continut.campuri.get("surse_citate") or []:
        citat_ = str(s.get("citat", "")) if isinstance(s, dict) else ""
        pasaj = None
        try:
            pasaj = (
                intrare.baza().get(creier.Pasaj, uuid.UUID(str(s.get("pasaj_id"))))
                if isinstance(s, dict)
                else None
            )
        except ValueError:
            pasaj = None
        if (
            pasaj is None
            or pasaj.tenant_id != intrare.tenant_id
            or not creier.citat_in_text(citat_, pasaj.text)
        ):
            probleme.append(
                Problema(
                    "G2.sursa_citata_falsa",
                    citat_[:200],
                    "Citatul indicat ca sursă nu se regăsește în pasajul din materialele clientului; "
                    "scoate-l.",
                )
            )
            continue
        intrari.append(acoperire.intrare_din_texte(f"pasaj:{pasaj.id}", "sursa", "", [citat_], tip="sursa"))
    return intrari, probleme


def incarca_registru(intrare: Intrare) -> Registru:
    """Registrul de fapte al clientului, valabil la `intrare.la` (o singură citire pe rulare)."""

    def citeste() -> Registru:
        db = intrare.baza()
        intrari = [din_fapt(f) for f in creier.fapte.pentru_context(db, intrare.tenant_id, intrare.la)]
        intrari += [din_oferta(o) for o in creier.oferte.pentru_context(db, intrare.tenant_id, intrare.la)]
        surse, _ = surse_citate(intrare)
        fereastra = int(incarca("afirmatii")["acoperire"]["fereastra_subiect"])
        return Registru(tuple(intrari + surse), fereastra)

    return intrare.memo("g2.registru", citeste)


# --- nucleul pur
# -----------------------------------------------------------------------------------------------------


def probleme_afirmatii(text: str, reg: Registru) -> list[Problema]:
    """O problemă pentru fiecare afirmație diferită de registru sau neacoperită (aceeași afirmație o
    dată)."""
    probleme: list[Problema] = []
    vazute: set[tuple[str, str]] = set()
    for c in acoperire.verifica(text, reg):
        a = c.afirmatie
        cheie = (a.tip, a.fragment.lower())
        if c.acoperire is Acoperire.ACOPERITA or cheie in vazute:
            continue
        vazute.add(cheie)
        if c.acoperire is Acoperire.DIFERITA:
            probleme.append(
                Problema(
                    f"G2.{a.tip}_diferit",
                    a.fragment,
                    f"„{a.fragment}” nu corespunde registrului de fapte ({c.registru_spune}); folosește "
                    f"exact valoarea "
                    "din registru sau scoate afirmația.",
                    detalii=c.registru_spune,
                )
            )
        else:
            probleme.append(
                Problema(
                    f"G2.neacoperita.{a.tip}",
                    a.fragment,
                    f"Afirmația „{a.fragment}” nu are acoperire în registrul de fapte aprobate; "
                    f"scoate-o sau înlocuiește-o "
                    "cu un fapt din registru (nu inventa cifre, prețuri sau promisiuni).",
                    detalii=a.tip,
                )
            )
    return probleme


def _radacini_subiect(subiect: str) -> list[str]:
    return [c[:5] for c in re.findall(r"[a-z]{4,}", afirmatii.baza(subiect))]


def fapte_lipsa(
    reg: Registru, necesare: list[Any], intrebari_autor: list[Any]
) -> list[tuple[str, str | None, str | None]]:
    """(întrebarea, tipul faptului, subiectul) pentru fiecare fapt necesar care nu există în registru."""
    lipsa: list[tuple[str, str | None, str | None]] = []
    for n in necesare:
        if not isinstance(n, dict):
            continue
        tip, subiect = str(n.get("tip", "")), str(n.get("subiect", "")).strip()
        radacini = _radacini_subiect(subiect)
        gasit = False
        for i in reg.intrari:
            nume_si_text = afirmatii.baza(i.nume + " " + i.text)
            subiect_ok = not radacini or all(r in nume_si_text for r in radacini)
            if tip == "pret":
                gasit = subiect_ok and bool(i.preturi)
            else:
                gasit = subiect_ok and (i.tip == tip or not tip)
            if gasit:
                break
        if not gasit:
            eticheta = ETICHETE_FAPT.get(tip, "informația")
            lipsa.append(
                (
                    f"Pentru acest livrabil este nevoie de {eticheta} pentru „{subiect}”, dar registrul "
                    f"de fapte nu o are. "
                    "Care este?",
                    tip or None,
                    subiect or None,
                )
            )
    for q in intrebari_autor:
        if isinstance(q, str) and len(q.strip()) >= 5:
            lipsa.append((q.strip()[:1000], None, None))
    return list(dict.fromkeys(lipsa))


@registru.validator(
    registru.DefinitieValidator(
        COD,
        "Fapte",
        VERSIUNE,
        Treapta.V1,
        30,
        descriere="Afirmații verificabile potrivite exact cu registrul; fapt lipsă → întrebare către client",
    )
)
def g2_reguli(intrare: Intrare) -> list[Verdict]:
    reg = incarca_registru(intrare)
    _, probleme_surse = surse_citate(intrare)
    probleme = [*probleme_surse, *probleme_afirmatii(intrare.text, reg)]
    detalii = {"intrari_registru": len(reg.intrari), "la": intrare.la.isoformat()}
    verdicte = [verdict_din_probleme(COD, VERSIUNE, Treapta.V1, probleme, detalii=detalii)]
    campuri = intrare.continut.campuri
    lipsa = fapte_lipsa(reg, campuri.get("fapte_necesare") or [], campuri.get("intrebari_autor") or [])
    if lipsa:
        verdicte.append(
            verdict_din_probleme(
                COD,
                VERSIUNE,
                Treapta.V1,
                [
                    Problema(
                        "G2.fapt_lipsa",
                        "",
                        "Livrabilul se oprește: lipsește un fapt necesar din registru. Clientul a fost "
                        "întrebat; "
                        f"nu presupune valoarea ({q[1] or 'fapt'}: {q[2] or 'vezi întrebarea'}).",
                        detalii=q[0],
                    )
                    for q in lipsa
                ],
                detalii={
                    "intrebare": True,
                    "intrebari": [{"intrebare": q[0], "tip": q[1], "subiect": q[2]} for q in lipsa],
                },
            )
        )
    if len(verdicte) == 2 and verdicte[0].rezultat.value == "trece":
        verdicte = verdicte[1:]
    return verdicte


# --- V3: afirmații nestructurate
# ---------------------------------------------------------------------------------------


class AfirmatieModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fragment: str = Field(max_length=400)
    fapt_id: str | None = Field(default=None, max_length=80)


class AfirmatiiNestructurate(gateway.Iesire):
    afirmatii: list[AfirmatieModel] = Field(max_length=30)


def probleme_din_afirmatii_model(
    iesire: AfirmatiiNestructurate, text: str, reg: Registru, deja: list[afirmatii.Afirmatie]
) -> list[Problema]:
    """Verificarea deterministă a răspunsului: fragmentul trebuie să apară literal în text, să nu conțină
    cifre (acelea sunt
    ale extractorului, comparate exact) și să nu fie deja o afirmație prinsă; acoperirea cere un fapt
    existent în registru."""
    cunoscute = {i.id for i in reg.intrari}
    probleme = []
    vazute: set[str] = set()
    baza_text = afirmatii.baza(text)
    for a in iesire.afirmatii:
        frag = a.fragment.strip()
        if not judecator.fragment_in_text(frag, text) or re.search(r"\d", frag) or frag.lower() in vazute:
            continue
        vazute.add(frag.lower())
        poz = baza_text.find(afirmatii.baza(frag))
        if poz >= 0 and any(x.start < poz + len(frag) and poz < x.sfarsit for x in deja):
            continue
        if a.fapt_id and a.fapt_id in cunoscute:
            continue
        probleme.append(
            Problema(
                "G2.neacoperita.nestructurata",
                frag,
                f"Afirmația „{frag}” nu are acoperire în registrul de fapte aprobate; scoate-o sau "
                f"înlocuiește-o cu un fapt "
                "din registru.",
            )
        )
    return probleme


@registru.validator(
    registru.DefinitieValidator(
        COD,
        "Fapte (judecător)",
        VERSIUNE_V3,
        Treapta.V3,
        30,
        foloseste_model=True,
        descriere="Afirmații nestructurate (fără cifre), potrivite cu registrul de un judecător mic",
    )
)
def g2_judecator(intrare: Intrare) -> Verdict:
    reg = incarca_registru(intrare)
    fapte_txt = (
        "\n".join(f"[{i.id}] {i.nume}: {i.afisare}" for i in reg.intrari if i.felul != "sursa")
        or "(registru gol)"
    )
    variabile = {"text": gateway.marcheaza_extern(intrare.text, sursa="livrabil"), "fapte": fapte_txt}
    r, eroare = judecator.apeleaza(
        intrare, validator=COD, prompt="validare.g2_afirmatii", schema=AfirmatiiNestructurate,
        variabile=variabile, max_tokeni=900,
    )  # fmt: skip
    if r is None:
        return judecator.indisponibil(COD, VERSIUNE_V3, Treapta.V3, eroare or "", "validare.g2_afirmatii")
    assert isinstance(r.iesire, AfirmatiiNestructurate)  # noqa: S101
    probleme = probleme_din_afirmatii_model(r.iesire, intrare.text, reg, afirmatii.extrage(intrare.text))
    return verdict_din_probleme(
        COD,
        VERSIUNE_V3,
        Treapta.V3,
        probleme,
        cost=judecator.cost_din(r),
        detalii=judecator.detalii_din(r, intrare),
    )
