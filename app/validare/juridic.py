"""G9 Juridic (docs/09 §9.4, docs/21 §21.8, §21.11): reduceri cu preț de referință, promisiuni de rezultat,
mențiuni obligatorii.

- Reducerea (21.11): o afirmație de reducere (procent cu „reducere”, „redus”, „discount” …) trebuie să se
sprijine pe o ofertă din catalog
  care are preț de referință, iar acesta trebuie să fie CEL MAI MIC preț aplicat în cele 30 de zile
  dinaintea reducerii, calculat din
  versiunile aprobate ale ofertei (`creier.istoric`). Fără ofertă sau fără preț de referință → blocare. Fără
  istoric de prețuri (oferta nu
  a avut o versiune anterioară) verificarea nu se poate face: rezultatul este un avertisment EXPLICIT, nu o
  trecere. Istoric mai scurt de 30
  de zile → avertisment minor.
- Promisiuni de rezultat (V1, listă din `date/juridic.toml`): „rezultate garantate”, „sigur vei slăbi” …
blochează. V4 (opțional, judecător
  puternic prin gateway, profilul `strategie`): promisiune de rezultat, urgență falsă, recenzii false —
  rubrică cu dovadă literală.
- Mențiuni obligatorii: pachetul `juridic` de reguli (mecanismul F5.4, reguli `obligatoriu`).
"""

import datetime as dt
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app import creier
from app.validare import acoperire, afirmatii, judecator, registru, reguli
from app.validare.date_validare import incarca
from app.validare.intrare import Intrare
from app.validare.probleme import Problema, verdict_din_probleme
from app.validare.verdict import Severitate, Treapta, Verdict
from app.validare.verifica_fapte import incarca_registru

COD = "G9"
VERSIUNE = "1"
VERSIUNE_V4 = "1"


@dataclass(frozen=True)
class VersiunePret:
    pret: Decimal
    de_la: dt.datetime
    pana_la: dt.datetime | None  # None: în vigoare


def pret_minim_anterior(
    versiuni: list[VersiunePret], de_la_curent: dt.datetime, zile: int
) -> tuple[Decimal | None, bool]:
    """(cel mai mic preț aplicat în [de_la_curent − zile, de_la_curent), istoricul acoperă toată fereastra?)
    — nucleu pur.
    Fără nicio versiune anterioară: (None, False)."""
    inceput = de_la_curent - dt.timedelta(days=zile)
    anterioare = [v for v in versiuni if v.de_la < de_la_curent]
    preturi = [v.pret for v in anterioare if min(v.pana_la or de_la_curent, de_la_curent) > inceput]
    if not anterioare or not preturi:
        return None, False
    return min(preturi), min(v.de_la for v in anterioare) <= inceput


def _dec(v: object) -> Decimal | None:
    try:
        return None if v is None else Decimal(str(v))
    except InvalidOperation:
        return None


def istoric_oferta(
    db: object, intrare_id: uuid.UUID, la: dt.datetime
) -> tuple[list[VersiunePret], dt.datetime | None, dict[str, object]]:
    """Versiunile APROBATE ale ofertei ca intervale de preț, plus versiunea curentă la `la`."""
    ver = [v for v in creier.istoric(db, intrare_id) if v.aprobat_la is not None]  # type: ignore[arg-type]
    intervale: list[VersiunePret] = []
    curenta = None
    for i, v in enumerate(ver):
        sfarsit = v.retras_la or (ver[i + 1].aprobat_la if i + 1 < len(ver) else None)
        pret = _dec((v.continut.get("pret") or {}).get("numar"))
        if pret is not None and v.aprobat_la is not None:
            intervale.append(VersiunePret(pret, v.aprobat_la, sfarsit))
        if v.aprobat_la is not None and v.aprobat_la <= la and (sfarsit is None or sfarsit > la):
            curenta = v
    return intervale, (curenta.aprobat_la if curenta else None), (curenta.continut if curenta else {})


def afirmatii_de_reducere(text: str) -> list[afirmatii.Afirmatie]:
    cuvinte = incarca("juridic")["pret_referinta"]["cuvinte_reducere"]
    b = afirmatii.baza(text)
    gasite = []
    for a in afirmatii.extrage(text):
        if a.tip != "procent":
            continue
        zona = b[max(0, a.start - 30) : a.sfarsit + 30]
        if any(c in zona for c in cuvinte) or b[max(0, a.start - 1) : a.start] == "-":
            gasite.append(a)
    return gasite


def probleme_reduceri(intrare: Intrare) -> list[Problema]:
    reducere = afirmatii_de_reducere(intrare.text)
    if not reducere:
        return []
    zile = int(incarca("juridic")["pret_referinta"]["zile"])
    reg = incarca_registru(intrare)
    probleme: list[Problema] = []
    for a in reducere:
        aproape = [i for i in acoperire.apropiate(intrare.text, a, reg) if i.felul == "oferta"]
        if not aproape:
            probleme.append(
                Problema(
                    "G9.reducere_fara_oferta",
                    a.fragment,
                    f"Reducerea „{a.fragment}” nu se sprijină pe o ofertă din catalog cu preț de "
                    f"referință; "
                    "numește oferta și prețul ei anterior sau scoate reducerea.",
                )
            )
            continue
        for o in aproape:
            probleme += _verifica_oferta(intrare, a, o, zile)
    return list(dict.fromkeys(probleme))


def _verifica_oferta(
    intrare: Intrare, a: afirmatii.Afirmatie, o: acoperire.IntrareRegistru, zile: int
) -> list[Problema]:
    if o.pret_ref is None:
        return [
            Problema(
                "G9.reducere_fara_pret_de_referinta",
                a.fragment,
                f"Oferta „{o.nume}” nu are preț de referință în catalog, deci reducerea „{a.fragment}” "
                f"nu e permisă; "
                "adaugă prețul de referință (cel mai mic din ultimele 30 de zile) sau scoate reducerea.",
            )
        ]
    versiuni, de_la, _ = istoric_oferta(intrare.baza(), uuid.UUID(o.id), intrare.la)
    minim, acoperit = pret_minim_anterior(versiuni, de_la, zile) if de_la else (None, False)
    if minim is None:
        return [
            Problema(
                "G9.istoric_preturi_lipsa",
                a.fragment,
                f"Pentru „{o.nume}” nu există istoric de prețuri înainte de reducere: prețul de "
                f"referință "
                f"({afirmatii.baza(str(o.pret_ref[0]))}) nu se poate verifica față de cele 30 de zile "
                f"anterioare; un om trebuie să confirme.",
                blocant=False,
                severitate=Severitate.MAJORA,
                detalii="istoric de prețuri inexistent",
            )
        ]
    if o.pret_ref[0] != minim:
        return [
            Problema(
                "G9.pret_de_referinta_gresit",
                a.fragment,
                f"Prețul de referință al „{o.nume}” ({format(o.pret_ref[0].normalize(), 'f')}) nu este "
                f"cel mai mic preț din ultimele "
                f"{zile} de zile dinaintea reducerii ({format(minim.normalize(), 'f')}); corectează-l "
                f"în catalog sau scoate reducerea.",
                detalii=f"minim anterior {minim}",
            )
        ]
    if not acoperit:
        return [
            Problema(
                "G9.istoric_preturi_partial",
                a.fragment,
                f"Istoricul de prețuri al „{o.nume}” nu acoperă toate cele {zile} de zile dinaintea "
                f"reducerii; verifică prețul de referință.",
                blocant=False,
                severitate=Severitate.MINORA,
            )
        ]
    return []


def probleme_promisiuni(text: str) -> list[Problema]:
    b = afirmatii.baza(text)
    probleme = []
    for sablon in incarca("juridic")["promisiuni_rezultat"]["expresii"]:
        for m in re.finditer(sablon, b):
            fragment = text[m.start() : m.end()]
            probleme.append(
                Problema(
                    "G9.promisiune_de_rezultat",
                    fragment,
                    f"„{fragment}” promite un rezultat garantat; formulează ce oferi, nu ce vei obține "
                    f"garantat.",
                )
            )
    return list(dict.fromkeys(probleme))


def probleme_mentiuni(intrare: Intrare) -> list[Problema]:
    ctx = reguli.Context(
        canal=intrare.livrabil.canal, tip=intrare.livrabil.tip, campuri=intrare.continut.campuri
    )
    probleme = []
    for p in reguli.pachete_juridice(intrare.livrabil.canal):
        for r in p.pachet.reguli:
            for pot in reguli.potriviri(r, intrare.text, ctx):
                sev = Severitate(r.severitate)
                probleme.append(
                    Problema(
                        f"G9.{p.nume}.{r.id}",
                        pot.fragment,
                        r.instructiune or r.text,
                        blocant=sev is not Severitate.MINORA,
                        severitate=sev,
                        detalii=f"{r.sursa.titlu} ({r.marcaj})",
                    )
                )
    return probleme


@registru.validator(
    registru.DefinitieValidator(
        COD,
        "Juridic",
        VERSIUNE,
        Treapta.V1,
        80,
        descriere="Reduceri cu preț de referință, promisiuni de rezultat, mențiuni obligatorii",
    )
)
def g9_reguli(intrare: Intrare) -> Verdict:
    probleme = [*probleme_reduceri(intrare), *probleme_promisiuni(intrare.text), *probleme_mentiuni(intrare)]
    pachete = [
        {"pachet": p.nume, "versiune": p.pachet.versiune, "amprenta": p.amprenta}
        for p in reguli.pachete_juridice(intrare.livrabil.canal)
    ]
    return verdict_din_probleme(COD, VERSIUNE, Treapta.V1, probleme, detalii={"pachete": pachete})


CRITERII_V4 = {
    "fara_promisiune_de_rezultat": "Textul NU promite un rezultat garantat clientului (câștig, slăbit, "
    "vindecare, succes).",
    "fara_urgenta_falsa": "Textul NU creează o urgență falsă (stoc, termen sau cerere inventate, fără "
    "temei în text).",
    "fara_recenzii_false": "Textul NU conține recenzii, mărturii sau cifre de clienți prezentate ca "
    "reale fără sursă.",
}
INSTRUCTIUNI_V4 = {
    "fara_promisiune_de_rezultat": "Scoate promisiunea de rezultat din fragmentul indicat.",
    "fara_urgenta_falsa": "Scoate urgența neîntemeiată din fragmentul indicat.",
    "fara_recenzii_false": "Scoate sau sprijină pe o sursă reală recenzia din fragmentul indicat.",
}


@registru.validator(
    registru.DefinitieValidator(
        COD,
        "Juridic (judecător puternic)",
        VERSIUNE_V4,
        Treapta.V4,
        80,
        foloseste_model=True,
        descriere="Promisiuni de rezultat, urgență falsă, recenzii false; cazuri cu miză mare",
    )
)
def g9_judecator(intrare: Intrare) -> Verdict:
    return judecator.judeca(
        intrare, validator=COD, versiune=VERSIUNE_V4, treapta=Treapta.V4, prompt="validare.g9_juridic",
        criterii=CRITERII_V4, instructiuni=INSTRUCTIUNI_V4, profil="strategie", max_tokeni=900,
    )  # fmt: skip
