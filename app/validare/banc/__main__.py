"""`python -m app.validare.banc`: rulează bancul și afișează scorurile; salvează rularea (nivel de
agenție)."""

import argparse
import json
import sys

from app.db import sesiune_agentie
from app.validare import exemple
from app.validare.banc import depozit, executie, seturi


def text_scoruri(sc: dict) -> str:  # type: ignore[type-arg]
    def pr(x: float | None) -> str:
        return "–" if x is None else f"{x * 100:.1f}%"

    linii = [
        f"Banc de evaluare: {sc['exemple']} exemple, seturi {sc['amprenta_seturi'][:12]}, "
        f"{sc['durata_ms']} ms"
    ]
    if sc["omise"]:
        linii.append("Omise (cer vectori prin gateway): " + ", ".join(sc["omise"]))
    linii.append("")
    linii.append(
        f"{'Validator':<10}{'N':>4}{'TP':>5}{'FP':>5}{'FN':>5}{'TN':>5}{'Precizie':>10}{'Recall':>9}{'Fals+':>8}"
    )
    for g, v in sc["validatori"].items():
        linii.append(
            f"{g:<10}{v['exemple']:>4}{v['tp']:>5}{v['fp']:>5}{v['fn']:>5}{v['tn']:>5}"
            f"{pr(v['precizie']):>10}{pr(v['recall']):>9}{pr(v['rata_fals_pozitive']):>8}"
        )
    r, b, p = sc["rele"], sc["bune"], sc["poarta"]
    linii += [
        "",
        f"Materiale rele blocate: {r['blocate']}/{r['total']} ({pr(r['rata_blocare'])}), "
        "prinse de validatorul vizat: "
        f"{r['prinse_de_validatorul_tinta']}",
        f"Materiale bune respinse pe nedrept: {b['respinse']}/{b['total']} ({pr(b['rata_respingere'])})",
        f"Poarta F5 (≥ 95% blocate, ≤ 10% respinse pe nedrept): {'TRECE' if p['trece'] else 'NU TRECE'}",
    ]
    return "\n".join(linii)


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(prog="python -m app.validare.banc", description=__doc__)
    a.add_argument("--json", action="store_true", help="scorurile ca JSON")
    a.add_argument("--fara-salvare", action="store_true", help="nu salvează rularea în `banc_rulari`")
    args = a.parse_args(argv)
    with sesiune_agentie() as db:
        promovate = exemple.promovate_ca_exemple(db)
        rulare = None if args.fara_salvare else depozit.porneste(db, utilizator_id=None)
        rulare_id = rulare.id if rulare else None
    try:
        sc = executie.ruleaza(seturi.incarca(promovate=promovate))
    except Exception as exc:
        if rulare_id:
            with sesiune_agentie() as db:
                depozit.esueaza(db, rulare_id, f"{type(exc).__name__}: {exc}")
        raise
    if rulare_id:
        with sesiune_agentie() as db:
            depozit.termina(db, rulare_id, sc)
    print(json.dumps(sc, ensure_ascii=False, indent=2) if args.json else text_scoruri(sc))
    return 0 if sc["poarta"]["trece"] else 1


if __name__ == "__main__":
    sys.exit(main())
