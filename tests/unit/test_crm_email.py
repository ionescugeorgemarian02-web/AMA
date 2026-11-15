"""F12.2 — nucleul pur al emailului către abonați și garda: emailul comercial are o singură ușă."""

import datetime as dt
import re
from pathlib import Path

from app.crm import email

ACUM = dt.datetime(2026, 11, 15, 12, tzinfo=dt.UTC)
# Fișierele care trimit emailuri TRANZACȚIONALE (confirmări, facturi, acces). Orice alt loc care cere un
# email trebuie să treacă prin `app.crm.email.trimite`, singurul care verifică suprimarea și consimțământul.
TRANZACTIONALE = {"app/site/audit.py", "app/finante/abonamente.py", "app/portal/cont.py"}
EXECUTORUL = "app/operare/efecte/sistem.py"  # ușa însăși (exemplul din documentația ei)


def test_jetonul_de_dezabonare_este_semnat_si_nu_expira() -> None:
    j = email.jeton_dezabonare("  Ana@Zorilor.example ")
    assert email.email_din_jeton(j) == "ana@zorilor.example"
    corp, _, semn = j.partition(".")
    assert email.email_din_jeton(corp + "." + "0" * 32) is None
    assert (
        email.email_din_jeton(email.jeton_dezabonare("alt@zorilor.example").partition(".")[0] + "." + semn)
        is None
    )
    for gresit in ("", "abc", ".", "###.###", corp):
        assert email.email_din_jeton(gresit) is None


def test_volumul_creste_treptat_pe_saptamani() -> None:
    assert email.limita_zilnica(None, ACUM) == 50
    limite = [email.limita_zilnica(ACUM - dt.timedelta(days=z), ACUM) for z in (0, 6, 7, 14, 21, 28, 400)]
    assert limite == [50, 50, 100, 200, 400, 800, 800]


def test_pragurile_de_oprire() -> None:
    assert not email.praguri_depasite(10, 5, 5), "sub 50 de trimiteri, ratele nu opresc nimic"
    assert not email.praguri_depasite(1000, 20, 1), "exact pe prag nu oprește"
    assert email.praguri_depasite(1000, 21, 0), "peste 2% respingeri"
    assert email.praguri_depasite(1000, 0, 2), "peste 0,1% plângeri"


def test_emailul_comercial_are_o_singura_usa() -> None:
    radacina = Path(__file__).resolve().parents[2]
    cer_email = re.compile(r"sistem\.cere\(\s*db,\s*\"email\"")
    gasite = {
        str(f.relative_to(radacina))
        for f in (radacina / "app").rglob("*.py")
        if cer_email.search(f.read_text(encoding="utf-8"))
    } - {EXECUTORUL}
    assert gasite - TRANZACTIONALE == {"app/crm/email.py"}, (
        "un loc nou trimite emailuri: dacă sunt comerciale, trec prin app.crm.email.trimite; dacă sunt "
        f"tranzacționale, adaugă fișierul în lista din acest test: {sorted(gasite - TRANZACTIONALE)}"
    )
    sursa = (radacina / "app/crm/email.py").read_text(encoding="utf-8")
    assert '"categorie": "marketing"' in sursa and "List-Unsubscribe-Post" in sursa
