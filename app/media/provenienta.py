"""Proveniența și dezvăluirea AI, G11 (F8.11, docs/14 §14.3, docs/21 §21.9, ADR-08).

Fiecare fișier final (video din montaj, imagine din Compozitor) primește un PAȘAPORT: amprenta fișierului,
componentele cu licențele lor, ce e generat (imagini: model, prompt, sămânță; vocea: profilul și motorul),
verdictele controlului (G5, G6) și ETICHETA stabilită pentru fiecare canal. Pașaportul stă în baza de date
(`pasapoarte`), lângă fișier (`<client>/pasapoarte/<sha256>.json`) și, prescurtat, în metadatele fișierului
(marcare lizibilă de mașini; standardul exact, de ex. C2PA, îl stabilește avocatul în F0.7: NEVERIFICAT).

Regula etichetei [I] (21.9: „imaginile și sunetul generate care pot părea reale se etichetează pe platformă”):
- imagine generată sau voce sintetică -> eticheta AI a platformei, pe fiecare canal, plus o mențiune în text;
- doar materiale reale (fotografiile clientului, stock, formatul E: om real, voce reală) -> fără etichetă AI.
G11 respinge un fișier final fără pașaport sau fără etichetă stabilită pentru fiecare canal.
"""

import datetime as dt
import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import validare
from app.config import get_settings
from app.media.modele import Activ, Pasaport

VERSIUNE = "1"
CANALE = ("tiktok", "instagram", "facebook", "youtube")
ETICHETA_PLATFORMA = {
    "tiktok": "Conținut generat de AI (comutatorul de la publicare)",
    "instagram": "Informații AI (eticheta Meta)",
    "facebook": "Informații AI (eticheta Meta)",
    "youtube": "Conținut modificat sau sintetic (declarația de la încărcare)",
}


def _componente(db: Session, a: Activ) -> list[dict[str, Any]]:
    lic = a.licenta or {}
    if lic.get("tip") != "productie_proprie":
        return [{"activ_id": str(a.id), "categorie": a.categorie, "sursa": a.sursa, "licenta": lic}]
    out = []
    for c in lic.get("componente", []):
        if "activ_id" in c:
            x = db.get(Activ, uuid.UUID(c["activ_id"]))
            if x is not None:
                out.append({"activ_id": str(x.id), "categorie": x.categorie, "sursa": x.sursa,
                            "licenta": x.licenta or {}, "generare": x.generare or {}})  # fmt: skip
        else:
            out.append(c)
    return out


def ai_din(componente: list[dict[str, Any]], *, om_real: bool = False) -> dict[str, bool]:
    imagine = any((c.get("licenta") or {}).get("tip") == "generat" for c in componente)
    voce = any((c.get("licenta") or {}).get("tip") == "voce_sintetizata" for c in componente)
    return {"imagine_generata": imagine, "voce_sintetica": voce, "om_real": om_real}


def etichete(ai: dict[str, bool], canale: tuple[str, ...] = CANALE) -> dict[str, dict[str, Any]]:
    """Nucleu pur: decizia de etichetă pe fiecare canal."""
    motive = []
    if ai["imagine_generata"]:
        motive.append("Imagini generate cu AI.")
    if ai["voce_sintetica"]:
        motive.append("Voce generată cu AI.")
    out = {}
    for c in canale:
        if motive:
            out[c] = {"eticheta_ai": True, "platforma": ETICHETA_PLATFORMA[c], "mentiune": " ".join(motive)}
        else:
            motiv = "om real, fără conținut generat" if ai["om_real"] else "doar materiale reale, cu licență"
            out[c] = {"eticheta_ai": False, "platforma": None, "mentiune": None, "motiv": motiv}
    return out


def emite(
    db: Session,
    a: Activ,
    *,
    validari: dict[str, Any] | None = None,
    om_real: bool = False,
    canale: tuple[str, ...] = CANALE,
) -> Pasaport:
    """Pașaportul fișierului final (idempotent: unul pe activ; o emitere nouă îl actualizează)."""
    comp = _componente(db, a)
    ai = ai_din(comp, om_real=om_real)
    continut = {
        "versiune": VERSIUNE,
        "activ_id": str(a.id),
        "sha256": a.sha256,
        "mime": a.mime,
        "emis_la": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "componente": comp,
        "generare": a.generare or {},
        "ai": ai,
        "etichete": etichete(ai, canale),
        "validari": validari or {},
    }
    p = db.execute(select(Pasaport).where(Pasaport.activ_id == a.id)).scalar_one_or_none()
    if p is None:
        p = Pasaport(tenant_id=a.tenant_id, activ_id=a.id, continut=continut)
        db.add(p)
    else:
        p.continut = continut
    db.flush()
    lateral = Path(get_settings().media_dir) / str(a.tenant_id) / "pasapoarte" / f"{a.sha256}.json"
    lateral.parent.mkdir(parents=True, exist_ok=True)
    lateral.write_text(json.dumps(continut, ensure_ascii=False, indent=1))
    return p


def al_activului(db: Session, activ_id: uuid.UUID) -> Pasaport | None:
    return db.execute(select(Pasaport).where(Pasaport.activ_id == activ_id)).scalar_one_or_none()


def marcaj(ai: dict[str, bool], randare_id: str) -> str:
    """Metadatele scrise în fișier (marcare lizibilă de mașini, prescurtată)."""
    return json.dumps({"ama": randare_id, "ai": [k for k, v in ai.items() if v and k != "om_real"]},
                      separators=(",", ":"))  # fmt: skip


def verdict(db: Session, a: Activ, canale: tuple[str, ...] = CANALE) -> validare.Verdict:
    """G11: pașaport existent, cu amprenta fișierului și eticheta stabilită pe fiecare canal."""
    p = al_activului(db, a.id)
    dovezi = []
    if p is None:
        dovezi.append(validare.Dovada("", "G11.pasaport", "fișier final fără pașaport"))
    else:
        c = p.continut
        if c.get("sha256") != a.sha256:
            dovezi.append(validare.Dovada("", "G11.pasaport", "pașaportul nu corespunde fișierului"))
        for canal in canale:
            e = (c.get("etichete") or {}).get(canal)
            if not e or "eticheta_ai" not in e:
                dovezi.append(validare.Dovada("", "G11.eticheta", f"etichetă nestabilită pentru {canal}"))
            elif (c["ai"]["imagine_generata"] or c["ai"]["voce_sintetica"]) and not e["eticheta_ai"]:
                dovezi.append(
                    validare.Dovada("", "G11.eticheta", f"conținut generat fără etichetă pe {canal}")
                )
    if not dovezi:
        return validare.trece("G11", VERSIUNE, validare.Treapta.V1)
    return validare.esec(
        "G11",
        VERSIUNE,
        validare.Treapta.V1,
        dovezi=dovezi,
        instructiune="Emite pașaportul și stabilește eticheta pe fiecare canal.",
    )
