"""Profilul de public (F4.9, C4): clientul ideal — segmente, nevoi, obiecții, declanșatori, canale,
limbaj — construit din
brieful aprobat și din citatele reale (`citate`). Intrare `insight_public` cu cheia `profil-public`; o
aprobă un om.

Poarta compartimentului: un profil nu poate fi propus sau aprobat dacă îi lipsește un element al
schemei, dacă nu se
sprijină pe cel puțin 3 citate reale sau dacă clientul are sub 20 de citate aprobate (« Gata când » din plan).
"""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app import creier, gateway
from app.creier.compartimente import Compartiment, SursaTip
from app.onboarding import citate, completare, prompturi
from app.operare import audit
from app.operare.motor import Prioritate

REFERINTA_PROMPT = "onboarding.profil_public@1"
CHEIE_PROFIL = "profil-public"
DOVEZI_MINIME = 3


class Segment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nume: str = Field(min_length=3, max_length=80)
    descriere: str = Field(min_length=10, max_length=400)


class ProfilPublic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tip: Literal["profil_public"] = "profil_public"
    segmente: list[Segment] = Field(min_length=1, max_length=5)
    nevoi: list[str] = Field(min_length=2, max_length=10)
    obiectii: list[str] = Field(min_length=2, max_length=10)
    declansatori: list[str] = Field(min_length=2, max_length=10)
    canale: list[str] = Field(min_length=1, max_length=8)
    limbaj: list[str] = Field(min_length=3, max_length=20)
    dovezi: list[str] = Field(
        min_length=DOVEZI_MINIME, max_length=20
    )  # identificatori de citate (intrări insight_public)


class PropunerePublic(gateway.Iesire):
    profil: ProfilPublic


class ProfilInvalid(creier.RegulaCreier):
    def __init__(self, probleme: list[str]) -> None:
        super().__init__("; ".join(probleme))
        self.probleme = probleme


def probleme_profil(db: Session | None, tenant_id: uuid.UUID | None, c: dict[str, Any]) -> list[str]:
    """Poarta profilului: schema, citate suficiente, dovezi care chiar sunt citate aprobate ale clientului."""
    try:
        p = ProfilPublic.model_validate(c)
    except ValidationError as exc:
        return [f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()[:6]]
    if db is None or tenant_id is None:
        return []
    aprobate = {str(i) for i, _ in citate.citate_aprobate(db, tenant_id)}
    probleme: list[str] = []
    if len(aprobate) < citate.MINIM_CITATE:
        probleme.append(
            f"clientul are {len(aprobate)} citate aprobate; "
            f"profilul de public cere cel puțin {citate.MINIM_CITATE}"
        )
    straine = [d for d in p.dovezi if d not in aprobate]
    if straine:
        probleme.append(f"dovezi care nu sunt citate aprobate ale clientului: {len(straine)}")
    return probleme


def _poarta(db: Any, tenant_id: uuid.UUID | None, c: dict[str, Any]) -> list[str]:
    return probleme_profil(db, tenant_id, c) if c.get("tip") == "profil_public" else []


def randeaza(c: dict[str, Any]) -> str | None:
    if c.get("tip") != "profil_public":
        return None
    try:
        p = ProfilPublic.model_validate(c)
    except ValidationError:
        return None
    segmente = "; ".join(f"{s.nume} ({s.descriere})" for s in p.segmente)
    return (
        f"Segmente: {segmente}\nNevoi: {'; '.join(p.nevoi)}\nObiecții: {'; '.join(p.obiectii)}\n"
        f"Declanșatori: {'; '.join(p.declansatori)}\nCanale: {', '.join(p.canale)}\n"
        f"Limbajul clienților: {', '.join(p.limbaj)}"
    )


creier.inregistreaza_poarta(Compartiment.INSIGHT_PUBLIC, _poarta)
creier.inregistreaza_randare(Compartiment.INSIGHT_PUBLIC, randeaza)
creier.inregistreaza_cere_om(Compartiment.INSIGHT_PUBLIC, lambda c: c.get("tip") == "profil_public")


def propune_profil(
    db: Session, *, tenant_id: uuid.UUID, utilizator_id: uuid.UUID | None
) -> tuple[uuid.UUID, int]:
    """Profilul de public din brieful aprobat și din citatele aprobate. Ridică `Amanat`;
    `ProfilInvalid` dacă modelul
    se sprijină pe dovezi inexistente sau clientul are prea puține citate."""
    continut_brief, versiune = completare.brief_aprobat(db, tenant_id)
    from app.onboarding import brief as brief_mod

    toate = citate.citate_aprobate(db, tenant_id)
    if len(toate) < citate.MINIM_CITATE:
        raise ProfilInvalid(
            [f"clientul are {len(toate)} citate aprobate; cere cel puțin {citate.MINIM_CITATE}"]
        )
    linii = "\n".join(
        f"[{i}] ({c.get('categorie')}, {c.get('sentiment')}) {c.get('text')}" for i, c in toate[:60]
    )
    prompturi.asigura()
    r = gateway.apeleaza(
        db,
        prompt=REFERINTA_PROMPT,
        variabile={
            "brief": gateway.marcheaza_extern(
                brief_mod.text_pentru_prompt(continut_brief), sursa="raspuns_client", max_caractere=20_000
            ),
            "citate": gateway.marcheaza_extern(linii, sursa="recenzie", max_caractere=30_000),
        },
        schema=PropunerePublic,
        tenant_id=tenant_id,
        componenta="onboarding.profil_public",
        prioritate=Prioritate.P2,
        max_tokeni=2500,
    )
    iesire = r.iesire
    if not isinstance(iesire, PropunerePublic):
        raise TypeError("ieșirea nu respectă schema promptului")
    continut = iesire.profil.model_dump(mode="json")
    probleme = probleme_profil(db, tenant_id, continut)
    if probleme:
        raise ProfilInvalid(probleme)
    sursa = creier.Sursa(
        SursaTip.SISTEM, detalii={"brief_versiune": versiune, "citate": len(toate), "model": r.model}
    )
    existenta = creier.gaseste_intrare(
        db, tenant_id=tenant_id, compartiment=Compartiment.INSIGHT_PUBLIC, cheie=CHEIE_PROFIL
    )
    if existenta is None:
        i, v = creier.creeaza_intrare(
            db,
            tenant_id=tenant_id,
            compartiment=Compartiment.INSIGHT_PUBLIC,
            cheie=CHEIE_PROFIL,
            continut=continut,
            sursa=sursa,
        )
        iid, nr = i.id, v.nr
    else:
        v = creier.propune_schimbare(db, existenta.id, continut=continut, sursa=sursa)
        iid, nr = existenta.id, v.nr
    audit.record(
        db, "onboarding.profil_public_propus", obiect_tip="creier_intrare", obiect_id=iid,
        utilizator_id=utilizator_id, tenant_id=tenant_id, detalii={"versiune": nr},
    )  # fmt: skip
    return iid, nr
