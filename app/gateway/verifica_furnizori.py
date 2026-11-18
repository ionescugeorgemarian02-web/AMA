"""Verificarea furnizorilor din catalogul G-pool: un apel mic la fiecare furnizor activ (cu toate secretele).

    python -m app.gateway.verifica_furnizori                 # primul model al fiecărui furnizor activ
    python -m app.gateway.verifica_furnizori --toate-modelele
    python -m app.gateway.verifica_furnizori --furnizor groq --furnizor cloudflare --json

Pentru primul test live, după ce cheile sunt puse în mediu (sau în seif). Cererea are câțiva tokeni („Răspunde
doar cu OK”); nu trece prin rutare, cote sau registru (furnizorii pot fi încă `inactiv` acolo) și nu se
scrie în jurnalul de apeluri, dar fiecare furnizor lasă o urmă (`gateway` / `verificare_furnizor`). Cheile nu
apar în ieșire: doar numele secretelor care lipsesc.

Coduri de ieșire: 0 = toți furnizorii activi au răspuns; 1 = cel puțin unul a eșuat;
2 = niciun furnizor activ.
"""

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass

from app.gateway import client, secrete
from app.gateway.catalog import FURNIZORI_POOL, MODELE_POOL, POOL, FurnizorPool, ModelPool
from app.gateway.erori import EroareFurnizor
from app.gateway.tipuri import CerereModel, Destinatie, Mesaj
from app.operare import urme

PROMPT = "Răspunde doar cu: OK"
TIMEOUT_SEC = 45.0


@dataclass(frozen=True)
class Rezultat:
    furnizor: str
    stare: str  # ok | eroare | dezactivat | fara_model
    model: str = ""
    durata_ms: int = 0
    tokeni: int = 0
    detaliu: str = ""


def destinatie(f: FurnizorPool, m: ModelPool) -> Destinatie:
    """Adresa și parametrii din catalog, completați din secrete (fără cheie)."""
    url = f.url_baza
    if f.url_din and (v := secrete.citeste(f.url_din)) and v.startswith("https://"):
        url = v
    parametri = {p: secrete.citeste(s) or "" for s, p in f.parametri_din.items()}
    return Destinatie(f.cod, f.tip_api, url, m.model, parametri, frozenset(m.capabilitati))


def verifica_model(f: FurnizorPool, m: ModelPool) -> Rezultat:
    cerere = CerereModel(mesaje=(Mesaj("user", PROMPT),), max_tokeni=16, temperatura=0.0)
    start = time.monotonic()
    try:
        r = client.trimite(destinatie(f, m), secrete.cheie(f.cod), cerere, timeout_sec=TIMEOUT_SEC)
    except EroareFurnizor as exc:
        return Rezultat(
            f.cod, "eroare", m.model, int((time.monotonic() - start) * 1000), detaliu=str(exc)[:200]
        )
    durata = int((time.monotonic() - start) * 1000)
    if not r.text.strip():
        return Rezultat(f.cod, "eroare", m.model, durata, r.tokeni_intrare + r.tokeni_iesire, "răspuns gol")
    return Rezultat(f.cod, "ok", m.model, durata, r.tokeni_intrare + r.tokeni_iesire, r.text.strip()[:40])


def verifica(furnizori: list[str] | None = None, *, toate_modelele: bool = False) -> list[Rezultat]:
    rezultate: list[Rezultat] = []
    for f in FURNIZORI_POOL:
        if furnizori and f.cod not in furnizori:
            continue
        lipsesc = secrete.lipsa(f.cod)
        if lipsesc:
            rezultate.append(Rezultat(f.cod, "dezactivat", detaliu="lipsesc: " + ", ".join(lipsesc)))
            continue
        modele = [m for m in MODELE_POOL if m.furnizor == f.cod]
        if not modele:
            rezultate.append(Rezultat(f.cod, "fara_model", detaliu="niciun model în catalog"))
            continue
        for m in modele if toate_modelele else modele[:1]:
            r = verifica_model(f, m)
            rezultate.append(r)
            urme.emite(
                "gateway", "verificare_furnizor", rezultat="ok" if r.stare == "ok" else "esec",
                motiv=r.detaliu if r.stare != "ok" else "", obiect_tip="furnizor", obiect_id=f.cod,
                durata_ms=r.durata_ms, iesiri={"model": r.model},
            )  # fmt: skip
    return rezultate


def cod_iesire(rezultate: list[Rezultat]) -> int:
    incercate = [r for r in rezultate if r.stare in ("ok", "eroare")]
    if not incercate:
        return 2
    return 0 if all(r.stare == "ok" for r in incercate) else 1


def tabel(rezultate: list[Rezultat]) -> str:
    randuri = [f"{'furnizor':<14} {'stare':<11} {'durata':>8}  model / detaliu"]
    for r in rezultate:
        durata = f"{r.durata_ms} ms" if r.durata_ms else ""
        text = " — ".join(x for x in (r.model, r.detaliu) if x)
        randuri.append(f"{r.furnizor:<14} {r.stare:<11} {durata:>8}  {text}")
    active = sum(1 for r in rezultate if r.stare in ("ok", "eroare"))
    ok = sum(1 for r in rezultate if r.stare == "ok")
    randuri.append(f"\n{ok} din {active} verificări reușite; {len(POOL)} furnizori în catalog.")
    return "\n".join(randuri)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m app.gateway.verifica_furnizori", description=__doc__.split("\n")[0]
    )
    p.add_argument(
        "--furnizor", action="append", choices=sorted(POOL), help="doar acest furnizor (se repetă)"
    )
    p.add_argument("--toate-modelele", action="store_true", help="câte un apel la fiecare model din catalog")
    p.add_argument("--json", action="store_true", help="ieșire JSON")
    a = p.parse_args(argv)
    rezultate = verifica(a.furnizor, toate_modelele=a.toate_modelele)
    if a.json:
        print(json.dumps([asdict(r) for r in rezultate], ensure_ascii=False, indent=2))
    else:
        print(tabel(rezultate))
    return cod_iesire(rezultate)


if __name__ == "__main__":
    sys.exit(main())
