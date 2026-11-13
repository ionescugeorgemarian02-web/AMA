"""Pregătirea onboardingului real al unui brand propriu (poarta F4).

Comanda: `python -m app.creier.pregatire --client …`.

Creează clientul (sau îl regăsește după nume) și sursele lui: site-ul (statut „site-ul clientului”), un fișier
cu recenzii (statut „recenzii ale clientului”, text lipit) și 3–5 concurenți (statut „site public al
concurenței”). Cu `--colecteaza` pornește și colectarea site-urilor (flux durabil; cere un worker pornit).
Nu pornește niciun model și nu aprobă nimic: interviul, brieful, ghidul, publicul, harta pieței și strategia
se parcurg apoi din panou (`/onboarding/<id>`, `/creier/client/<id>`, `/campanii/<id>`), iar aprobările sunt
ale proprietarului.

    python -m app.creier.pregatire --client CariereAI --site https://exemplu.ro --recenzii recenzii.txt \\
        --concurent "Alt Brand=https://alt.exemplu.ro" --concurent "Alt Doi=https://doi.exemplu.ro" \\
        --concurent "Trei"
"""

import argparse
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

PRAG_RECENZII = 20


@dataclass
class Raport:
    client_id: uuid.UUID
    client_nou: bool
    surse: list[tuple[str, str, uuid.UUID]] = field(default_factory=list)  # (rol, nume, id)
    colectari: list[uuid.UUID] = field(default_factory=list)
    avertismente: list[str] = field(default_factory=list)


def pregateste(
    nume: str,
    *,
    site: str | None = None,
    recenzii: Path | None = None,
    concurenti: Sequence[str] = (),
    colecteaza: bool = False,
) -> Raport:
    """Clientul și sursele lui. Idempotent pe client și pe sursă (după nume): rulat din nou, nu dublează."""
    from app import cercetare, onboarding
    from app.conturi.servicii import Actor, cauta_clienti, creeaza_client
    from app.db import sesiune_agentie, sesiune_tenant

    with sesiune_agentie() as db:
        gasiti = cauta_clienti(db, nume)
        client = gasiti[0] if gasiti else creeaza_client(db, nume, actor=Actor.cli())
        raport = Raport(client_id=client.id, client_nou=not gasiti)
    tenant = raport.client_id
    with sesiune_tenant(tenant) as db:
        existente = {(s.nume, s.statut): s for s in cercetare.surse(db, tenant)}

        def sursa(
            rol: str, nume_sursa: str, tip: str, statut: str, url: str | None = None
        ) -> cercetare.SursaColectare:
            s = existente.get((nume_sursa, statut)) or cercetare.creeaza_sursa(
                db, tenant_id=tenant, tip=tip, statut_cod=statut, nume=nume_sursa, url=url
            )
            raport.surse.append((rol, nume_sursa, s.id))
            return s

        if site:
            sursa("site", f"Site {nume}", "site", "site_client", site)
        if recenzii:
            s = sursa("recenzii", f"Recenzii {nume}", "manual", "recenzii_client")
            continut = recenzii.read_text(encoding="utf-8")
            paragrafe = [p for p in (x.strip() for x in continut.split("\n\n")) if p]
            cercetare.adauga_text(db, tenant_id=tenant, sursa_id=s.id, titlu=recenzii.name, text=continut)
            if len(paragrafe) < PRAG_RECENZII:
                raport.avertismente.append(
                    f"fișierul de recenzii are {len(paragrafe)} paragrafe; profilul de public cere "
                    f"cel puțin {PRAG_RECENZII} de citate"
                )
        for c in concurenti:
            nume_c, _, adresa = c.partition("=")
            sursa(
                "concurent",
                nume_c.strip(),
                "site" if adresa.strip() else "manual",
                "site_concurenta",
                adresa.strip() or None,
            )
        n_conc = sum(1 for r in raport.surse if r[0] == "concurent")
        if n_conc and not (onboarding.piata.MIN_CONCURENTI <= n_conc <= onboarding.piata.MAX_CONCURENTI):
            raport.avertismente.append(
                f"{n_conc} concurenți; harta pieței cere între {onboarding.piata.MIN_CONCURENTI} "
                f"și {onboarding.piata.MAX_CONCURENTI}"
            )
    if colecteaza:
        for rol, _, sid in raport.surse:
            if rol in ("site", "concurent") and _este_site(tenant, sid):
                raport.colectari.append(cercetare.porneste_colectare(tenant, sid))
    return raport


def _este_site(tenant: uuid.UUID, sursa_id: uuid.UUID) -> bool:
    from app import cercetare
    from app.db import sesiune_tenant

    with sesiune_tenant(tenant) as db:
        return cercetare.sursa(db, sursa_id).tip == "site"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.creier.pregatire", description=__doc__.split("\n")[0])
    ap.add_argument("--client", required=True, help="numele brandului (clientul se creează dacă nu există)")
    ap.add_argument("--site", help="adresa site-ului brandului")
    ap.add_argument(
        "--recenzii",
        type=Path,
        help="fișier .txt cu recenzii / comentarii / întrebări, câte unul pe paragraf",
    )
    ap.add_argument(
        "--concurent",
        action="append",
        default=[],
        help='"Nume=https://adresa" sau doar "Nume"; repetabil (3–5)',
    )
    ap.add_argument(
        "--colecteaza", action="store_true", help="pornește colectarea site-urilor (cere un worker pornit)"
    )
    args = ap.parse_args(argv)
    if args.recenzii and not args.recenzii.is_file():
        print(f"fișier inexistent: {args.recenzii}", file=sys.stderr)
        return 2
    from app import cercetare

    try:
        r = pregateste(
            args.client,
            site=args.site,
            recenzii=args.recenzii,
            concurenti=args.concurent,
            colecteaza=args.colecteaza,
        )
    except (cercetare.ColectareInvalida, cercetare.SursaInterzisa) as exc:
        print(f"sursă nepermisă: {exc}", file=sys.stderr)
        return 1
    print(f"client {'creat' if r.client_nou else 'existent'}: {r.client_id}")
    for rol, nume, sid in r.surse:
        print(f"  sursă ({rol}): {nume} [{sid}]")
    for c in r.colectari:
        print(f"  colectare pornită: {c}")
    for a in r.avertismente:
        print(f"  ATENȚIE: {a}")
    print(
        f"Urmează, în panou: /onboarding/{r.client_id} (interviu), /creier/client/{r.client_id}, "
        f"/campanii/{r.client_id}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
