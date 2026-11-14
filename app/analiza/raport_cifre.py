"""Cifrele raportului lunar (F10.5, L1 + K3, docs/19 §19.6, docs/05 §5.12 „G2 pe cifre”).

- `cifre_luna`: din datele măsurate (F10.1–F10.3), pentru postările publicate în lună: câte au fost
  măsurate, totalurile pe metrică (ultima citire a fiecărei postări), cele mai bune postări, cel mai bun și
  cel mai slab tipar de hook și cel mai bun slot (doar grupurile cu cel puțin `MINIM_GRUP` postări).
- `propozitii`: frazele raportului, construite determinist din aceste cifre (fără model: un text scris de
  un model ar putea greși o cifră; autorul de insight cu model, K3, rămâne o propunere pentru F11).
- `verifica`: controlul „G2 pe cifre”: extrage numerele din fraze cu același extractor ca G2
  (`validare.extrage_afirmatii`) și cere ca fiecare să existe în cifrele din date. O frază cu un număr care
  nu vine din date face raportul să renunțe la fraze (rămân tabelele) și să spună de ce.
"""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import validare
from app.analiza import colector, etichete
from app.analiza.modele import EtichetePostare
from app.connectors.contract import CHEI_METRICI, ETICHETE_METRICI

MINIM_GRUP = 2  # sub atâtea postări, un grup nu intră în comparații
TIP = "interactiuni_pe_afisari"
# Numerele care țin de formulare, nu de date („la 100 de afișări”, „cel puțin 2 postări”).
CONSTANTE = (Decimal(100), Decimal(MINIM_GRUP))


def _la_suta(medie: float) -> float:
    return round(medie * 100, 1)


def _zecimal(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def cifre_luna(db: Session, tenant_id: uuid.UUID, de_la: dt.datetime, pana_la: dt.datetime) -> dict[str, Any]:
    postari = list(
        db.execute(
            select(EtichetePostare).where(
                EtichetePostare.tenant_id == tenant_id,
                EtichetePostare.publicat_la >= de_la,
                EtichetePostare.publicat_la < pana_la,
            )
        ).scalars()
    )
    totaluri: dict[str, int] = {}
    masurate = 0
    for p in postari:
        ultimele = colector.ultimele(db, p.livrabil_id, p.canal)
        masurate += bool(ultimele)
        for k, v in ultimele.items():
            totaluri[k] = totaluri.get(k, 0) + int(v)
    cu_rec = sorted(
        (p for p in postari if p.recompensa is not None and p.recompensa_tip == TIP),
        key=lambda p: -(p.recompensa or 0.0),
    )

    def grupuri(dupa: str) -> list[dict[str, Any]]:
        g: dict[str, list[float]] = {}
        for p in cu_rec:
            g.setdefault(etichete.valoare(p, dupa), []).append(p.recompensa or 0.0)
        out = [
            {"valoare": v, "postari": len(r), "la_suta": _la_suta(sum(r) / len(r))}
            for v, r in g.items()
            if len(r) >= MINIM_GRUP and v != etichete.NECUNOSCUT
        ]
        return sorted(out, key=lambda x: (-x["la_suta"], x["valoare"]))

    return {
        "postari_publicate": len(postari),
        "postari_masurate": masurate,
        "totaluri": {k: totaluri[k] for k in CHEI_METRICI if k in totaluri},
        "totaluri_etichetate": [[ETICHETE_METRICI[k], totaluri[k]] for k in CHEI_METRICI if k in totaluri],
        "top": [
            {
                "livrabil_id": str(p.livrabil_id),
                "canal": p.canal,
                "tipar_hook": etichete.valoare(p, "tipar_hook"),
                "la_suta": _la_suta(p.recompensa or 0.0),
            }
            for p in cu_rec[:3]
        ],
        "tipare": grupuri("tipar_hook"),
        "sloturi": grupuri("slot"),
    }


def propozitii(c: dict[str, Any]) -> dict[str, str]:
    """Frazele secțiunilor 2–5, doar din cifrele date. Fără cifre destule, fraza spune asta."""
    if not c["postari_masurate"]:
        return {
            "rezultate": "Nicio postare măsurată luna aceasta: cifrele apar după prima publicare.",
            "ce_a_mers": "",
            "ce_nu_a_mers": "",
            "public": "",
        }
    parti = [
        f"{v} {ETICHETE_METRICI[k].lower()}" for k, v in c["totaluri"].items() if k != "timp_vizionare_s"
    ]
    rezultate = (
        f"Am măsurat {c['postari_masurate']} din {c['postari_publicate']} postări publicate. În total: "
        + (", ".join(parti) + ".")
    )
    lipsa = f"Încă nu sunt destule postări pentru o comparație (cel puțin {MINIM_GRUP} pe grup)."
    tipare, sloturi = c["tipare"], c["sloturi"]
    ce_a_mers = ce_nu = lipsa
    if tipare:
        t = tipare[0]
        ce_a_mers = (
            f"Cel mai bine a mers tiparul de hook „{t['valoare']}”: în medie {_zecimal(t['la_suta'])} "
            f"interacțiuni la 100 de afișări, din {t['postari']} postări."
        )
        if len(tipare) > 1:
            s = tipare[-1]
            ce_nu = (
                f"Cel mai slab a mers tiparul de hook „{s['valoare']}”: în medie {_zecimal(s['la_suta'])} "
                f"interacțiuni la 100 de afișări, din {s['postari']} postări. "
                "Îl folosim mai rar luna viitoare."
            )
        else:
            ce_nu = "Un singur tipar de hook are destule postări; nu avem încă termen de comparație."
    public = lipsa
    if sloturi:
        s = sloturi[0]
        public = (
            f"Publicul a reacționat cel mai bine {s['valoare']}: în medie {_zecimal(s['la_suta'])} "
            f"interacțiuni la 100 de afișări, din {s['postari']} postări."
        )
    return {"rezultate": rezultate, "ce_a_mers": ce_a_mers, "ce_nu_a_mers": ce_nu, "public": public}


def numere_permise(c: dict[str, Any]) -> set[Decimal]:
    """Toate numerele care vin din date și au voie să apară în fraze."""
    permise = {Decimal(c["postari_publicate"]), Decimal(c["postari_masurate"]), *CONSTANTE}
    permise |= {Decimal(v) for v in c["totaluri"].values()}
    for g in (*c["tipare"], *c["sloturi"], *c["top"]):
        permise.add(Decimal(str(g["la_suta"])))
        if "postari" in g:
            permise.add(Decimal(g["postari"]))
    return permise


def verifica(texte: dict[str, str], c: dict[str, Any], *, ignora: tuple[str, ...] = ()) -> list[str]:
    """Controlul „G2 pe cifre”: numerele din fraze care NU vin din date. `ignora`: fragmente fără cifre de
    verificat (numele unui slot conține ora, care vine tot din date)."""
    permise = numere_permise(c)
    sloturi = [g["valoare"] for g in c["sloturi"]]
    probleme: list[str] = []
    for cheie, text in texte.items():
        curat = text
        for fragment in (*sloturi, *ignora):
            curat = curat.replace(fragment, "")
        for a in validare.extrage_afirmatii(curat):
            if a.valoare is not None and a.valoare.normalize() not in {p.normalize() for p in permise}:
                probleme.append(f"{cheie}: „{a.fragment}” nu vine din datele măsurate")
    return probleme
