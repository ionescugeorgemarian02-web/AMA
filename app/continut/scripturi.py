"""Scripturile video scurte (F6.4, E2, docs/13 §13.3: „hook în primele 3 secunde, 3–6 bătăi, text pe ecran,
apel la
acțiune, durată estimată din numărul de cuvinte”; docs/14: E2 livrează scriptul pe bătăi).

- Hook-ul îl aleg E1 + regula deterministă, cu limita de cuvinte a video-ului (`scriere.CUVINTE_HOOK_PE_TIP`,
[I]).
- E2 (profilul `creatie`) scrie bătăile: ce se spune (`voce`), textul pe ecran și indicația vizuală, plus
apelul la acțiune.
- Durata NU o dă modelul: se estimează determinist din cuvintele rostite (`CUVINTE_PE_SECUNDA` [I]) plus o
pauză pe bătaie
  [I]. Scriptul se încadrează dacă durata estimată e în ±15% [I] din durata-țintă (din brief; implicit 30 s,
  între 15 și
  60). Dacă nu se încadrează, E2 primește o singură dată instrucțiunea de a scurta / lungi; altfel livrabilul
  merge în
  coada de erori cu diagnostic (nu în validare).
- Conținutul pentru cascadă: `text` = hook + vocea bătăilor + apelul (ce se aude); `campuri` = `hook`,
`batai`, `cta`,
  `durata_tinta_sec`, `durata_estimata_sec` (G1 cere 3–6 bătăi).
"""

import math

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app import gateway, productie, validare
from app.continut import brief, editor, scriere
from app.operare.motor import Prioritate

COMPONENTA = "E2"
CUVINTE_PE_SECUNDA = 2.5  # [I] ritmul unei voci calme în română
PAUZA_PE_BATAIE = 0.5  # [I] secunde între bătăi (tăietură, respirație)
TOLERANTA = 0.15  # [I] ±15% din durata-țintă
DURATA_IMPLICITA, DURATA_MINIMA, DURATA_MAXIMA = 30, 15, 60


class Bataie(BaseModel):
    model_config = ConfigDict(extra="forbid")
    voce: str = Field(min_length=3, max_length=400)
    text_ecran: str = Field(default="", max_length=80)
    vizual: str = Field(min_length=3, max_length=200)


class ScriptVideo(gateway.Iesire):
    batai: list[Bataie] = Field(min_length=3, max_length=6)
    apel_la_actiune: str = Field(min_length=3, max_length=150)


def _cuvinte(text: str) -> int:
    return len(text.split())


def durata_estimata(hook: str, batai: list[str], cta: str) -> float:
    """Secundele estimate din cuvintele rostite, cu o pauză pe bătaie. Nucleu pur."""
    cuvinte = _cuvinte(hook) + sum(_cuvinte(b) for b in batai) + _cuvinte(cta)
    return round(cuvinte / CUVINTE_PE_SECUNDA + PAUZA_PE_BATAIE * len(batai), 1)


def se_incadreaza(estimata: float, tinta: int) -> bool:
    return abs(estimata - tinta) <= TOLERANTA * tinta


def durata_tinta(continut_brief: dict[str, object]) -> int:
    v = continut_brief.get("durata_tinta_sec", DURATA_IMPLICITA)
    tinta = int(v) if isinstance(v, int | float | str) and str(v).isdigit() else DURATA_IMPLICITA
    return min(max(tinta, DURATA_MINIMA), DURATA_MAXIMA)


def cuvinte_tinta(tinta: int, nr_batai: int = 4) -> int:
    """Câte cuvinte rostite încap în durata-țintă (ca indicație pentru E2)."""
    return math.floor((tinta - PAUZA_PE_BATAIE * nr_batai) * CUVINTE_PE_SECUNDA)


class ScriptNeincadrat(scriere.AutorEsuat):
    """Scriptul nu se încadrează în durata-țintă nici după a doua încercare."""


def _cere(
    db: Session, lv: productie.Livrabil, b: dict[str, object], hook: str, indicatie: str
) -> tuple[ScriptVideo, str]:
    tinta = durata_tinta(b)
    r = gateway.apeleaza(
        db,
        prompt="continut.script@1",
        schema=ScriptVideo,
        tenant_id=lv.tenant_id,
        componenta="continut.script",
        livrabil_id=lv.id,
        prioritate=Prioritate.P2,
        max_tokeni=1500,
        variabile={
            "canal": lv.canal,
            "hook": hook,
            "tinta": str(tinta),
            "cuvinte": str(cuvinte_tinta(tinta)),
            "brief": brief.text_pentru_autor(b),
            "exemple": scriere.exemple_text(db, lv),
            "indicatie": indicatie,
        },
    )
    if not isinstance(r.iesire, ScriptVideo):
        raise TypeError("ieșirea nu respectă schema promptului")
    return r.iesire, r.model


def scrie_scriptul(db: Session, lv: productie.Livrabil, b: dict[str, object]) -> validare.ContinutNou:
    hook = editor.editeaza(scriere.hook_ales(db, lv, b))
    tinta = durata_tinta(b)
    indicatie = ""
    estimata = 0.0
    for _ in range(2):
        s, model = _cere(db, lv, b, hook, indicatie)
        voci = [editor.editeaza(x.voce) for x in s.batai]
        cta = editor.editeaza(s.apel_la_actiune)
        estimata = durata_estimata(hook, voci, cta)
        if se_incadreaza(estimata, tinta):
            batai = [
                {"voce": v, "text_ecran": editor.editeaza(x.text_ecran), "vizual": x.vizual}
                for v, x in zip(voci, s.batai, strict=True)
            ]
            return validare.ContinutNou(
                text="\n".join([hook, *voci, cta]),
                campuri={
                    "hook": hook,
                    "batai": batai,
                    "cta": cta,
                    "durata_tinta_sec": tinta,
                    "durata_estimata_sec": estimata,
                },
                autor=COMPONENTA,
                model_autor=model,
            )
        sens = "Scurtează" if estimata > tinta else "Lungește"
        indicatie = (
            f"Încercarea anterioară dura aproximativ {estimata:.0f} de secunde. {sens} vocea până la circa "
            f"{cuvinte_tinta(tinta, len(s.batai))} de cuvinte în total, ca să încapă în {tinta} de secunde."
        )
    raise ScriptNeincadrat(f"scriptul durează ~{estimata:.0f} s față de ținta de {tinta} s")


scriere.AUTORI["script_video_scurt"] = scrie_scriptul
