"""Profilul de brand (F4.5, docs/13 §13.8): din brief și materiale, trei variante de ton; omul alege
una (sau combină /
editează), iar ghidul devine intrare în Creier (`profil_brand`, cheia `ghid`), citită de constructorul
de context.

O variantă are: descriere, reguli „da” și „nu”, vocabular preferat și interzis și cel puțin 3 exemple
scrise pe canale
DIFERITE. Verificările sunt deterministe (`valideaza_varianta`): un exemplu care folosește un cuvânt
din vocabularul
interzis, sau exemple pe mai puțin de 3 canale, fac varianta nevalidă, oricât de bine ar suna. Modelul
(profilul
`creatie`, prin gateway, schemă strictă) propune; omul alege; aprobarea ghidului o dă tot un om
(`creier.aproba`).
"""

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import creier, gateway
from app.creier.compartimente import Compartiment, SursaTip
from app.ids import new_id
from app.onboarding import brief as brief_mod
from app.onboarding import completare, prompturi
from app.onboarding.modele import VarianteTon
from app.operare import audit
from app.operare.motor import Prioritate

REFERINTA_PROMPT = "onboarding.propune_ton@1"
CHEIE_GHID = "ghid"
CANALE = ("facebook", "instagram", "tiktok", "linkedin", "email", "site", "whatsapp", "reclama")
PARTI = ("descriere", "reguli", "vocabular", "exemple")
EXEMPLE_MINIME = 3
CANALE_MINIME = 3


class ExempluTon(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canal: Literal["facebook", "instagram", "tiktok", "linkedin", "email", "site", "whatsapp", "reclama"]
    text: str = Field(min_length=15, max_length=700)


class VariantaTon(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nume: str = Field(min_length=3, max_length=60)
    descriere: str = Field(min_length=20, max_length=700)
    reguli_da: list[str] = Field(min_length=2, max_length=8)
    reguli_nu: list[str] = Field(min_length=2, max_length=8)
    vocabular_preferat: list[str] = Field(min_length=3, max_length=20)
    vocabular_interzis: list[str] = Field(min_length=2, max_length=20)
    exemple: list[ExempluTon] = Field(min_length=EXEMPLE_MINIME, max_length=8)


class GhidBrand(VariantaTon):
    """Ghidul de brand aprobat: o variantă validă + de unde vine."""

    origine: Literal["varianta", "combinat", "editat"] = "varianta"
    din_variante: list[int] = Field(default_factory=list, max_length=9)


class PropunereTon(gateway.Iesire):
    variante: list[VariantaTon] = Field(min_length=3, max_length=3)


class VariantaInvalida(ValueError):
    def __init__(self, probleme: list[str]) -> None:
        super().__init__("; ".join(probleme))
        self.probleme = probleme


def _cuvinte(text: str) -> set[str]:
    import re
    import unicodedata

    t = unicodedata.normalize("NFD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return set(re.findall(r"[a-z0-9]+", t))


def probleme_varianta(v: dict[str, Any]) -> list[str]:
    """Probleme ale unei variante, dincolo de schemă (nucleu pur): canale puține, exemple cu vocabular
    interzis,
    vocabular preferat și interzis care se suprapun, reguli goale."""
    probleme: list[str] = []
    canale = {e.get("canal") for e in v.get("exemple", []) if isinstance(e, dict)}
    if len(canale) < CANALE_MINIME:
        probleme.append(
            f"exemplele trebuie scrise pe cel puțin {CANALE_MINIME} canale diferite (sunt {len(canale)})"
        )
    interzise = {w for t in v.get("vocabular_interzis", []) for w in _cuvinte(str(t))}
    for e in v.get("exemple", []):
        folosite = _cuvinte(str(e.get("text", ""))) & interzise
        if folosite:
            probleme.append(
                f"exemplul de pe {e.get('canal')} folosește vocabular interzis: {', '.join(sorted(folosite))}"
            )
    preferat = {w for t in v.get("vocabular_preferat", []) for w in _cuvinte(str(t))}
    if preferat & interzise:
        probleme.append(
            "vocabularul preferat și cel interzis se suprapun: " + ", ".join(sorted(preferat & interzise))
        )
    for cheie in ("reguli_da", "reguli_nu"):
        if any(not str(r).strip() for r in v.get(cheie, [])):
            probleme.append(f"{cheie}: reguli goale")
    return probleme


def valideaza_ghid(continut: dict[str, Any]) -> GhidBrand:
    """Ghidul validat de schemă ȘI de verificările deterministe; ridică `VariantaInvalida`."""
    import pydantic

    try:
        g = GhidBrand.model_validate(continut)
    except pydantic.ValidationError as exc:
        raise VariantaInvalida(
            [f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()[:4]]
        ) from None
    probleme = probleme_varianta(g.model_dump(mode="json"))
    if probleme:
        raise VariantaInvalida(probleme)
    return g


def randeaza(continut: dict[str, Any]) -> str | None:
    """Ghidul pe scurt, pentru pachetul de context (`None`: conținut care nu e un ghid, se folosește
    randarea implicită)."""
    try:
        g = GhidBrand.model_validate(continut)
    except Exception:
        return None
    exemple = " | ".join(f"[{e.canal}] {e.text}" for e in g.exemple)
    return (
        f"Ton „{g.nume}”: {g.descriere}\n"
        f"Da: {'; '.join(g.reguli_da)}\nNu: {'; '.join(g.reguli_nu)}\n"
        f"Vocabular preferat: {', '.join(g.vocabular_preferat)}\n"
        f"Vocabular interzis: {', '.join(g.vocabular_interzis)}\nExemple: {exemple}"
    )


creier.inregistreaza_randare(Compartiment.PROFIL_BRAND, randeaza)


def propune_variante(
    db: Session, *, tenant_id: uuid.UUID, utilizator_id: uuid.UUID | None
) -> list[VarianteTon]:
    """Trei variante de ton din brieful aprobat și din materialele clientului. Ridică `Amanat` (se
    reprogramează) și
    `VariantaInvalida` dacă modelul întoarce o variantă care încalcă verificările."""
    from app import cercetare

    continut, versiune = completare.brief_aprobat(db, tenant_id)
    surse_ok = [s.id for s in cercetare.surse(db, tenant_id) if cercetare.STATUTE[s.statut].reutilizare_text]
    pasaje: list[str] = []
    if surse_ok:
        try:
            r = creier.cauta(
                db,
                tenant_id=tenant_id,
                intrebare="cum vorbește brandul, ton, stil, mesaje către clienți",
                limita=4,
                surse=surse_ok,
            )
            pasaje = [x.text[:600] for x in r.rezultate]
        except creier.CautareRefuzata:
            pasaje = []
    prompturi.asigura()
    r2 = gateway.apeleaza(
        db,
        prompt=REFERINTA_PROMPT,
        variabile={
            "brief": gateway.marcheaza_extern(
                brief_mod.text_pentru_prompt(continut), sursa="raspuns_client", max_caractere=20_000
            ),
            "pasaje": gateway.marcheaza_extern(
                "\n\n".join(pasaje) or "(niciun material colectat)", sursa="pagina", max_caractere=10_000
            ),
        },
        schema=PropunereTon,
        tenant_id=tenant_id,
        componenta="onboarding.propune_ton",
        prioritate=Prioritate.P2,
        max_tokeni=3500,
    )
    iesire = r2.iesire
    if not isinstance(iesire, PropunereTon):
        raise TypeError("ieșirea nu respectă schema promptului")
    probleme: list[str] = []
    for k, v in enumerate(iesire.variante, 1):
        probleme += [f"varianta {k}: {p}" for p in probleme_varianta(v.model_dump(mode="json"))]
    if probleme:
        raise VariantaInvalida(probleme)
    grup = new_id()
    randuri = [
        VarianteTon(
            id=new_id(), tenant_id=tenant_id, grup_id=grup, nr=k, continut=v.model_dump(mode="json"),
            prompt=REFERINTA_PROMPT, model=r2.model, brief_versiune=versiune,
        )
        for k, v in enumerate(iesire.variante, 1)
    ]  # fmt: skip
    db.add_all(randuri)
    db.flush()
    audit.record(
        db, "onboarding.variante_ton_propuse", obiect_tip="onboarding_variante_ton", obiect_id=grup,
        utilizator_id=utilizator_id, tenant_id=tenant_id, detalii={"brief_versiune": versiune},
    )  # fmt: skip
    return randuri


def variante(db: Session, tenant_id: uuid.UUID) -> list[VarianteTon]:
    """Variantele ultimei rulări, în ordine."""
    ultimul = db.execute(
        select(VarianteTon.grup_id)
        .where(VarianteTon.tenant_id == tenant_id)
        .order_by(VarianteTon.creat_la.desc())
        .limit(1)
    ).scalar_one_or_none()
    if ultimul is None:
        return []
    return list(
        db.execute(
            select(VarianteTon).where(VarianteTon.grup_id == ultimul).order_by(VarianteTon.nr)
        ).scalars()
    )


def alege(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    utilizator_id: uuid.UUID,
    varianta: int | None = None,
    combina: dict[str, int] | None = None,
    editari: dict[str, Any] | None = None,
) -> tuple[uuid.UUID, int]:
    """Omul alege: o variantă (`varianta=2`), o combinație (`combina={"descriere": 1, "reguli": 2,
    "vocabular": 2,
    "exemple": 3}`) și/sau corecturi (`editari={"descriere": "…"}`). Ghidul validat devine versiune
    `propus` a intrării
    `profil_brand/ghid`; aprobarea e un pas separat (`creier.aproba`). Întoarce (intrare, versiune)."""
    grup = variante(db, tenant_id)
    if not grup:
        raise creier.RegulaCreier("nu există variante de ton: propune-le întâi")
    dupa_nr = {v.nr: v for v in grup}
    if (varianta is None) == (combina is None):
        raise creier.RegulaCreier("alege fie o variantă, fie o combinație")
    if varianta is not None:
        if varianta not in dupa_nr:
            raise creier.RegulaCreier(f"varianta {varianta} nu există")
        baza = dict(dupa_nr[varianta].continut)
        origine, folosite = "varianta", [varianta]
    else:
        if combina is None:  # pragma: no cover  (exclus de verificarea de mai sus)
            raise creier.RegulaCreier("alege fie o variantă, fie o combinație")
        if set(combina) != set(PARTI) or any(n not in dupa_nr for n in combina.values()):
            raise creier.RegulaCreier(
                "combinația cere cele patru părți (descriere, reguli, vocabular, exemple), "
                "fiecare dintr-o variantă existentă"
            )
        baza = {
            "nume": dupa_nr[combina["descriere"]].continut["nume"],
            "descriere": dupa_nr[combina["descriere"]].continut["descriere"],
        }
        baza["reguli_da"] = dupa_nr[combina["reguli"]].continut["reguli_da"]
        baza["reguli_nu"] = dupa_nr[combina["reguli"]].continut["reguli_nu"]
        baza["vocabular_preferat"] = dupa_nr[combina["vocabular"]].continut["vocabular_preferat"]
        baza["vocabular_interzis"] = dupa_nr[combina["vocabular"]].continut["vocabular_interzis"]
        baza["exemple"] = dupa_nr[combina["exemple"]].continut["exemple"]
        origine, folosite = "combinat", sorted(set(combina.values()))
    if editari:
        baza.update(editari)
        origine = "editat"
    ghid = valideaza_ghid({**baza, "origine": origine, "din_variante": folosite})
    sursa = creier.Sursa(
        SursaTip.OM,
        detalii={
            "grup": str(grup[0].grup_id),
            "variante": folosite,
            "brief_versiune": grup[0].brief_versiune,
        },
    )
    existenta = creier.gaseste_intrare(
        db, tenant_id=tenant_id, compartiment=Compartiment.PROFIL_BRAND, cheie=CHEIE_GHID
    )
    continut = ghid.model_dump(mode="json")
    if existenta is None:
        intrare, v = creier.creeaza_intrare(
            db, tenant_id=tenant_id, compartiment=Compartiment.PROFIL_BRAND, cheie=CHEIE_GHID,
            continut=continut,
            sursa=sursa, utilizator_id=utilizator_id,
        )  # fmt: skip
        iid, nr = intrare.id, v.nr
    else:
        v = creier.propune_schimbare(
            db, existenta.id, continut=continut, sursa=sursa, utilizator_id=utilizator_id
        )
        iid, nr = existenta.id, v.nr
    acum = dt.datetime.now(dt.UTC)
    for x in grup:
        x.ales = x.nr in folosite
        if x.ales:
            x.ales_de, x.ales_la = utilizator_id, acum
    db.flush()
    return iid, nr


_ = Any
