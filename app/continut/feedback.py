"""Capturarea feedbackului (F6.7, docs/11 N2 „ce respinge și ce editează omul”, docs/10 §10.1: exemplele de
aur se scriu
„automat, la aprobare”, cele negative „automat, la respingere”).

La o decizie aplicată pe un livrabil din calendar (punctul de extensie
`productie.aprobari.inregistreaza_dupa_decizie`, în
aceeași tranzacție):
- **respins** → o intrare în `exemple_negative`: textul respins, motivul (codul standard și fraza omului),
tipul, canalul,
  subiectul; aprobată prin sistem (compartimentul o permite);
- **aprobat** → o intrare în `exemple_aur`: textul final; dacă versiunea aprobată a fost editată de un om în
biroul de
  aprobări, și ciorna mașinii (diferența dintre ciornă și versiunea editată devine exemplu).

Exemplele intră în pachetul de context al următoarei sarcini de același tip și canal
(`creier.context.construieste(...,
exemple=(tip, canal))`): brieful (D5) și autorii (E1, E4, E2) le primesc în prompt.
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app import creier, productie, validare
from app.continut import brief
from app.creier.compartimente import Compartiment, SursaTip

TEXT_MAXIM = 1500


def _randeaza_negativ(c: dict[str, Any]) -> str | None:
    if "text" not in c:
        return None
    motiv = c.get("motiv") or "fără motiv"
    return f"Respins (motiv: {motiv}): {str(c['text'])[:TEXT_MAXIM]}"


def _randeaza_aur(c: dict[str, Any]) -> str | None:
    if "text" not in c:
        return None
    if c.get("ciorna"):
        ciorna = str(c["ciorna"])[:600]
        text = str(c["text"])[:TEXT_MAXIM]
        return f"Aprobat după editarea omului: {text} (ciorna, înainte de editare: {ciorna})"
    return f"Aprobat: {str(c['text'])[:TEXT_MAXIM]}"


creier.inregistreaza_randare(Compartiment.EXEMPLE_NEGATIVE, _randeaza_negativ)
creier.inregistreaza_randare(Compartiment.EXEMPLE_AUR, _randeaza_aur)


def _scrie(db: Session, lv: productie.Livrabil, comp: Compartiment, continut: dict[str, Any]) -> uuid.UUID:
    cheie = f"{lv.tip}:{lv.canal}:{lv.id}:v{continut['versiune']}"
    existenta = creier.gaseste_intrare(db, tenant_id=lv.tenant_id, compartiment=comp, cheie=cheie)
    if existenta is not None:
        return existenta.id
    i, v = creier.creeaza_intrare(
        db,
        tenant_id=lv.tenant_id,
        compartiment=comp,
        cheie=cheie,
        continut=continut,
        sursa=creier.Sursa(
            SursaTip.SISTEM, detalii={"livrabil": str(lv.id), "versiune": continut["versiune"]}
        ),
        motiv="feedback la aprobare",
    )
    creier.aproba(db, i.id, v.nr, utilizator_id=None, prin_sistem=True)
    return i.id


def captureaza(
    db: Session, ap: productie.Aprobare, lv: productie.Livrabil, hotarare: productie.Hotarare
) -> uuid.UUID | None:
    """Exemplul (negativ la respingere, de aur la aprobare) pentru un livrabil din calendar; `None` pentru
    celelalte."""
    b = brief.al_livrabilului(db, lv.id)
    if b is None:
        return None
    c = validare.continut.citeste(db, lv.id, ap.versiune)
    baza: dict[str, Any] = {
        "tip": lv.tip,
        "canal": lv.canal,
        "subiect": b.continut.get("subiect", ""),
        "text": c.text[:4000],
        "versiune": ap.versiune,
        "livrabil": str(lv.id),
    }
    if hotarare is productie.Hotarare.RESPINS:
        baza.update(motiv=ap.motiv or "", motiv_cod=ap.motiv_cod or "")
        return _scrie(db, lv, Compartiment.EXEMPLE_NEGATIVE, baza)
    randuri = validare.continut.versiuni(db, lv.id)
    aprobat = next((r for r in randuri if r.versiune == ap.versiune), None)
    if aprobat is not None and aprobat.creat_de is not None:  # editat de un om în biroul de aprobări
        ciorne = [r for r in randuri if r.versiune < ap.versiune and r.creat_de is None]
        if ciorne:
            baza["ciorna"] = ciorne[-1].text[:4000]
    return _scrie(db, lv, Compartiment.EXEMPLE_AUR, baza)


def _dupa_decizie(
    db: Session, ap: productie.Aprobare, lv: productie.Livrabil, hotarare: productie.Hotarare
) -> None:
    captureaza(db, ap, lv, hotarare)


productie.aprobari.inregistreaza_dupa_decizie(_dupa_decizie)


def exemple_text(db: Session, lv: productie.Livrabil) -> str:
    """Exemplele aceluiași tip și canal, gata de pus în promptul autorului; șir gol dacă nu există."""
    aur, negative = creier.context.exemple_pentru(db, lv.tenant_id, lv.tip, lv.canal, dt.datetime.now(dt.UTC))
    blocuri = []
    if aur:
        blocuri.append("Exemple aprobate (urmează-le tonul):\n" + "\n".join(f"- {r.text}" for r in aur))
    if negative:
        blocuri.append(
            "Exemple respinse (NU le repeta greșelile):\n" + "\n".join(f"- {r.text}" for r in negative)
        )
    return "\n\n".join(blocuri)
