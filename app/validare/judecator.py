"""Judecătorii mici (V3) și puternic (V4), prin gateway (docs/09 §9.6): rubrici cu criterii DA / NU și
cerință de dovadă.

Reguli (impuse aici, nu lăsate pe seama modelului):
- profilul `judecata` și `alt_model_decat` = modelul autorului: autorul nu este niciodată propriul judecător
(dacă nu
  există alt model eligibil, gateway-ul amână apelul, iar cascada se reprogramează);
- textul de validat intră în prompt ca DATE (`gateway.marcheaza_extern`), ieșirea este o schemă strictă
(`Rubrica`);
- un criteriu nesatisfăcut (`da = false`) cere FRAGMENTUL exact; dacă fragmentul nu apare literal în text,
constatarea nu
  poate fi dovedită și devine doar un avertisment minor (nu blochează);
- un criteriu la care modelul nu a răspuns rămâne neverificat (avertisment minor), nu „trecut”.
"""

from pydantic import BaseModel, ConfigDict, Field

from app import gateway
from app.creier.citat import normalizeaza
from app.operare.motor import Prioritate
from app.validare import prompturi
from app.validare.intrare import Intrare
from app.validare.probleme import Problema, verdict_din_probleme
from app.validare.verdict import Cost, Severitate, Treapta, Verdict

PROFIL = "judecata"


class RaspunsCriteriu(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criteriu: str = Field(max_length=40)
    da: bool  # criteriul este îndeplinit
    fragment: str = Field(
        default="", max_length=400
    )  # obligatoriu când `da` este fals: fragmentul exact din text
    motiv: str = Field(default="", max_length=300)


class Rubrica(gateway.Iesire):
    raspunsuri: list[RaspunsCriteriu] = Field(max_length=25)


def fragment_in_text(fragment: str, text: str) -> bool:
    """Fragmentul apare literal în text (aceleași normalizări ca la citatele din Creier: forma Unicode,
    spații, ghilimele,
    sedilă ≡ virgulă). Nu există lungime minimă: o greșeală poate fi un singur cuvânt."""
    f = normalizeaza(fragment)
    return bool(f) and f in normalizeaza(text)


def probleme_din_rubrica(
    rubrica: Rubrica,
    text: str,
    *,
    validator: str,
    criterii: dict[str, str],
    instructiuni: dict[str, str],
    blocant: bool,
    severitate: Severitate,
) -> tuple[list[Problema], dict[str, object]]:
    """Verificarea deterministă a răspunsului unui judecător (nucleu pur)."""
    probleme: list[Problema] = []
    raspunse: dict[str, RaspunsCriteriu] = {}
    for raspuns in rubrica.raspunsuri:
        if raspuns.criteriu in criterii and raspuns.criteriu not in raspunse:
            raspunse[raspuns.criteriu] = raspuns
    nedovedite: list[str] = []
    for cod in criterii:
        r = raspunse.get(cod)
        if r is None:
            probleme.append(
                Problema(
                    f"{validator}.{cod}.neverificat",
                    "",
                    f"Judecătorul nu a verificat criteriul „{cod}”; verifică-l tu: {criterii[cod]}",
                    blocant=False,
                    severitate=Severitate.MINORA,
                )
            )
        elif not r.da:
            if fragment_in_text(r.fragment, text):
                probleme.append(
                    Problema(
                        f"{validator}.{cod}",
                        r.fragment,
                        instructiuni[cod],
                        blocant=blocant,
                        severitate=severitate,
                        detalii=r.motiv,
                    )
                )
            else:
                nedovedite.append(cod)
                probleme.append(
                    Problema(
                        f"{validator}.{cod}.nedovedit",
                        "",
                        f"Judecătorul a semnalat „{cod}”, dar nu a indicat un fragment din text: verifică.",
                        blocant=False,
                        severitate=Severitate.MINORA,
                        detalii=r.motiv,
                    )
                )
    return probleme, {"criterii": sorted(criterii), "nedovedite": nedovedite}


def apeleaza(
    intrare: Intrare,
    *,
    validator: str,
    prompt: str,
    schema: type[gateway.Iesire],
    variabile: dict[str, str],
    profil: str = PROFIL,
    max_tokeni: int = 700,
) -> tuple[gateway.Rezultat | None, str | None]:
    """Un apel la judecător prin gateway: (rezultatul, None) sau (None, tipul erorii) dacă gateway-ul a
    refuzat / a
    eșuat. `gateway.Amanat` iese neprins (cascada se reprogramează). Textul de validat TREBUIE pus de
    apelant în
    `variabile` prin `gateway.marcheaza_extern`; modelul autorului e exclus (`alt_model_decat`)."""
    db = intrare.baza()
    if gateway.prompturi.rezolva(db, prompt) is None:
        prompturi.asigura()
    try:
        r = gateway.apeleaza(
            db,
            prompt=prompt,
            variabile=variabile,
            schema=schema,
            tenant_id=intrare.tenant_id,
            componenta=f"validare.{validator.lower()}",
            prioritate=Prioritate.P1,
            profil=profil,
            livrabil_id=intrare.livrabil.id,
            alt_model_decat=intrare.continut.model_autor,
            max_tokeni=max_tokeni,
            temperatura=0.0,
        )
    except gateway.Amanat:
        raise
    except gateway.EroareGateway as exc:
        return None, type(exc).__name__
    return r, None


def cost_din(r: gateway.Rezultat) -> Cost:
    return Cost(1, r.tokeni_intrare, r.tokeni_iesire, r.pret_umbra, r.durata_ms)


def detalii_din(r: gateway.Rezultat, intrare: Intrare) -> dict[str, object]:
    return {
        "prompt": f"{r.prompt_nume}@{r.prompt_versiune}",
        "model": r.model,
        "model_autor": intrare.continut.model_autor,
        "degradat": r.degradat,
    }


def indisponibil(validator: str, versiune: str, treapta: Treapta, eroare: str, prompt: str) -> Verdict:
    """Judecătorul n-a putut rula: avertisment minor, nu trecere tăcută."""
    return verdict_din_probleme(
        validator,
        versiune,
        treapta,
        [
            Problema(
                f"{validator}.judecator_indisponibil",
                "",
                "Judecătorul automat nu a putut rula; punctul acesta cere verificare umană.",
                blocant=False,
                severitate=Severitate.MINORA,
                detalii=eroare,
            )
        ],
        detalii={"prompt": prompt, "eroare": eroare},
    )


def judeca(
    intrare: Intrare,
    *,
    validator: str,
    versiune: str,
    treapta: Treapta,
    prompt: str,
    criterii: dict[str, str],
    instructiuni: dict[str, str],
    extra: dict[str, str] | None = None,
    blocant: bool = True,
    severitate: Severitate = Severitate.MAJORA,
    profil: str = PROFIL,
    max_tokeni: int = 700,
) -> Verdict:
    """Un verdict de la un judecător cu rubrică. `gateway.Amanat` iese neprins (cascada se reprogramează);
    alte erori ale
    gateway-ului dau un avertisment minor („judecătorul nu a putut rula”), nu o trecere tăcută."""
    variabile = {
        "text": gateway.marcheaza_extern(intrare.text, sursa="livrabil"),
        "criterii": "\n".join(f"- {cod}: {intrebare}" for cod, intrebare in criterii.items()),
        **(extra or {}),
    }
    r, eroare = apeleaza(
        intrare, validator=validator, prompt=prompt, schema=Rubrica, variabile=variabile, profil=profil,
        max_tokeni=max_tokeni,
    )  # fmt: skip
    if r is None:
        return indisponibil(validator, versiune, treapta, eroare or "", prompt)
    assert isinstance(r.iesire, Rubrica)  # noqa: S101  (schema cerută de apel)
    probleme, detalii = probleme_din_rubrica(
        r.iesire, intrare.text, validator=validator, criterii=criterii, instructiuni=instructiuni,
        blocant=blocant, severitate=severitate,
    )  # fmt: skip
    return verdict_din_probleme(
        validator,
        versiune,
        treapta,
        probleme,
        cost=cost_din(r),
        detalii={**detalii, **detalii_din(r, intrare)},
    )
