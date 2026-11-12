"""Măsurarea vitezei modelelor locale (F3.5, 6.4): `python -m app.gateway.masurare [--model COD …]`.

Rulează un test de viteză pe fiecare model local de text din registru (două-trei mărimi, 6.3), cu un
prompt fix în română, și scrie tokeni / secundă (mediana a `--cereri` rulări) în registru
(`tokeni_pe_secunda`, `viteza_masurata_la`). Viteza folosită este cea raportată de server
(`timings.predicted_per_second` la llama.cpp, fără timpul de procesare a promptului); dacă serverul nu o
raportează, tokeni de ieșire / durata cererii. Un model pe care serverul nu-l servește (llama.cpp ține UN
model încărcat; Ollama pe mai multe) rămâne nemăsurat, cu motivul afișat; nimic nu se scrie pentru el.

Comanda generează text pe procesor: rulează-o când niciun job greu nu lucrează (pe VPS, cu workerul greu
oprit sau în afara orelor de producție), altfel cifrele sunt prea mici. NEVERIFICAT pe un procesor real:
aici s-a rulat doar împotriva unui server fals în forma API-ului real.
"""

import argparse
import statistics
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import text

from app.db import sesiune_agentie
from app.gateway import ceas, client, registru
from app.gateway.candidat import Candidat
from app.gateway.erori import EroareFurnizor
from app.gateway.tipuri import CerereModel, Mesaj
from app.operare import audit

PROMPT = (
    "Scrie în română, în cinci propoziții, ce avantaje are un program de fidelizare pentru o cafenea de "
    "cartier și cum poate fi anunțat clienților pe rețelele sociale."
)
CERERI_IMPLICIT = 3
TOKENI_IMPLICIT = 96


@dataclass(frozen=True)
class Masuratoare:
    model: str
    tokeni_pe_sec: float | None
    esantioane: tuple[float, ...] = ()
    eroare: str = ""


def viteza(tokeni_iesire: int, secunde: float) -> float | None:
    """Tokeni pe secundă, sau `None` dacă nu se poate calcula (fără tokeni sau durată nulă)."""
    if tokeni_iesire <= 0 or secunde <= 0:
        return None
    return round(tokeni_iesire / secunde, 2)


def mediana(valori: Sequence[float]) -> float:
    return round(float(statistics.median(valori)), 2)


def masoara(c: Candidat, *, cereri: int = CERERI_IMPLICIT, max_tokeni: int = TOKENI_IMPLICIT) -> Masuratoare:
    cerere = CerereModel(mesaje=(Mesaj("user", PROMPT),), max_tokeni=max_tokeni, temperatura=0.0)
    esantioane: list[float] = []
    for _ in range(cereri):
        start = time.perf_counter()
        try:
            r = client.trimite(c.destinatie, None, cerere)
        except EroareFurnizor as exc:
            return Masuratoare(c.cod, None, tuple(esantioane), f"serverul nu a răspuns bine ({exc.fel})")
        v = r.tokeni_pe_sec or viteza(r.tokeni_iesire, time.perf_counter() - start)
        if v is None:
            return Masuratoare(c.cod, None, tuple(esantioane), "răspuns fără tokeni de ieșire")
        esantioane.append(v)
    return Masuratoare(c.cod, mediana(esantioane), tuple(esantioane))


def scrie(m: Masuratoare, c: Candidat) -> None:
    """Notează viteza în registru (și în audit). Nu face nimic pentru o măsurătoare eșuată."""
    if m.tokeni_pe_sec is None:
        return
    with sesiune_agentie() as db:
        db.execute(
            text(
                "UPDATE gateway_modele SET tokeni_pe_secunda = :v, viteza_masurata_la = :la, "
                "actualizat_la = now() "
                "WHERE id = :id"
            ),
            {"v": m.tokeni_pe_sec, "la": ceas.acum(), "id": c.model_id},
        )
        audit.record(
            db, "gateway.viteza_masurata", obiect_tip="model", obiect_id=c.cod, tenant_id=None,
            actor_tip="sistem",
            detalii={"model": c.cod, "viteza": m.tokeni_pe_sec, "esantioane": len(m.esantioane)},
        )  # fmt: skip


def modele_locale(candidati: Sequence[Candidat], doar: Sequence[str] = ()) -> list[Candidat]:
    """Modelele locale de TEXT (fără cele de vectori), eventual filtrate după cod."""
    ok = [c for c in candidati if c.fara_cheie and "embeddings" not in c.capabilitati]
    return [c for c in ok if not doar or c.cod in doar]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.gateway.masurare", description=__doc__.split("\n")[0])
    ap.add_argument(
        "--model", action="append", default=[], help="codul modelului (furnizor/identificator); repetabil"
    )
    ap.add_argument("--cereri", type=int, default=CERERI_IMPLICIT)
    ap.add_argument("--tokeni", type=int, default=TOKENI_IMPLICIT)
    args = ap.parse_args(argv)
    with sesiune_agentie() as db:
        candidati = modele_locale(registru.candidati(db), args.model)
    if not candidati:
        print("niciun model local în registru", file=sys.stderr)
        return 2
    esecuri = 0
    for c in candidati:
        m = masoara(c, cereri=args.cereri, max_tokeni=args.tokeni)
        scrie(m, c)
        if m.tokeni_pe_sec is None:
            esecuri += 1
            print(f"{c.cod}: nemăsurat ({m.eroare})")
        else:
            print(f"{c.cod}: {m.tokeni_pe_sec} tokeni/s (mediana a {len(m.esantioane)} rulări)")
    return 1 if esecuri == len(candidati) else 0


if __name__ == "__main__":
    sys.exit(main())
