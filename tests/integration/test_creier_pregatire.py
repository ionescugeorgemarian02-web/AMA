"""Poarta F4 — comanda `python -m app.creier.pregatire`: creează clientul și sursele unui brand propriu, ca proprietarul să pornească
onboardingul real. Fără rețea: nu pornește colectarea decât cu `--colecteaza`, iar sursele se creează doar ca date."""

from pathlib import Path

import pytest

from app import cercetare
from app.creier import pregatire
from app.db import sesiune_tenant
from tests import materiale_zorilor as mz

pytestmark = pytest.mark.db
NUME = "Brand Propriu de Probă"


def fisier_recenzii(tmp_path: Path, n: int) -> Path:
    f = tmp_path / "recenzii.txt"
    f.write_text(
        "\n\n".join(f"{t} — {mz.AUTORI[k % 6]}" for k, t in enumerate((mz.RECENZII * 2)[:n])),
        encoding="utf-8",
    )
    return f


def test_pregatirea_creeaza_clientul_si_sursele_si_este_idempotenta(tmp_path: Path) -> None:
    f = fisier_recenzii(tmp_path, 24)
    concurenti = [
        "Alt Brand=https://alt.exemplu.test/",
        "Alt Doi=https://doi.exemplu.test/",
        "Trei Fără Site",
    ]
    r = pregatire.pregateste(
        NUME + " 1", site="https://brand.exemplu.test/", recenzii=f, concurenti=concurenti
    )
    assert r.client_nou and not r.avertismente and not r.colectari  # fără --colecteaza nu pornește nimic
    roluri = [x[0] for x in r.surse]
    assert roluri == ["site", "recenzii", "concurent", "concurent", "concurent"]
    with sesiune_tenant(r.client_id) as db:
        surse = {s.nume: s for s in cercetare.surse(db, r.client_id)}
        assert surse[f"Site {NUME} 1"].statut == "site_client" and surse[f"Site {NUME} 1"].tip == "site"
        assert (
            surse[f"Recenzii {NUME} 1"].statut == "recenzii_client"
            and surse["Trei Fără Site"].tip == "manual"
        )
        assert surse["Alt Brand"].statut == "site_concurenta" and surse["Alt Brand"].url_radacina
        assert not cercetare.STATUTE[surse["Alt Brand"].statut].reutilizare_text
        assert len(cercetare.documente(db, surse[f"Recenzii {NUME} 1"].id)) == 1
    r2 = pregatire.pregateste(
        NUME + " 1", site="https://brand.exemplu.test/", recenzii=f, concurenti=concurenti
    )
    assert r2.client_id == r.client_id and not r2.client_nou  # același client
    assert {x[2] for x in r2.surse} == {x[2] for x in r.surse}  # aceleași surse, nicio dublură


def test_avertismente_pentru_prea_putine_recenzii_sau_concurenti(tmp_path: Path) -> None:
    f = fisier_recenzii(tmp_path, 5)
    r = pregatire.pregateste(NUME + " 2", recenzii=f, concurenti=["Unul", "Doi"])
    assert any("5 paragrafe" in a and "20" in a for a in r.avertismente)
    assert any("2 concurenți" in a for a in r.avertismente)


def test_comanda_afiseaza_ce_a_creat_si_refuza_surse_nepermise(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = fisier_recenzii(tmp_path, 22)
    cod = pregatire.main(
        [
            "--client",
            NUME + " 3",
            "--recenzii",
            str(f),
            "--concurent",
            "A",
            "--concurent",
            "B",
            "--concurent",
            "C",
        ]
    )
    iesire = capsys.readouterr().out
    assert (
        cod == 0
        and "client creat" in iesire
        and "/onboarding/" in iesire
        and "sursă (concurent): A" in iesire
    )
    assert pregatire.main(["--client", NUME + " 4", "--recenzii", str(tmp_path / "nu-exista.txt")]) == 2
    # rețele sociale nu se citesc automat (12.1): o sursă „site” către ele este refuzată, nu ignorată
    assert (
        pregatire.main(["--client", NUME + " 5", "--concurent", "Rețea=https://www.facebook.com/pagina"]) == 1
    )
    assert "nepermisă" in capsys.readouterr().err
