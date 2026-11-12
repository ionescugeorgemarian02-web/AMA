"""F1.3/F1.4 — gărzi de arhitectură: accesul la bază trece prin `app/db`, iar contextele privilegiate au locuri știute."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"

# Cine are voie să deschidă un context privilegiat (autentificare, agenție). Orice alt loc cere o decizie explicită.
CONTEXT_AUTH = {"app/conturi/web.py", "app/conturi/dependente.py", "app/db/motor.py", "app/db/__init__.py"}
CONTEXT_AGENTIE = {
    "app/conturi/cli.py",
    "app/db/motor.py",
    "app/db/__init__.py",
    # Procese fără utilizator, deci fără alt context posibil; fiecare e păzit înainte de a deschide contextul:
    "app/operare/livrare.py",  # rutele interne ale deployer-ului: jeton comparat în timp constant (F1.8)
    "app/operare/notificari.py",  # trimiterea către abonații agenției (alerte critice), fără cerere de utilizator
    "app/connectors/telegram/bot.py",  # webhook: antet-secret + chat permis, verificate înainte (F1.10)
    # Procesul worker (F2.7): fără utilizator; scrie semnale de viață și coada de erori la nivel de agenție.
    "app/operare/watchdog.py",
    "app/operare/semnale.py",  # semnale de viață + verificarea de sănătate a serviciului `worker`
    # Producția (F2.4, F2.8): joburi programate, fără utilizator; întrerupătorul global și expirarea aprobărilor
    # citesc toți clienții (rezultatele de pe o oră, termenele de pe toate cererile).
    "app/productie/fluxuri.py",
    # Executorul de efecte (F2.5): jobul programat `efecte.tic` și punerea efectelor în coadă citesc efectele
    # tuturor clienților (cele rămase după o oprire); încercările propriu-zise rulează pe clientul efectului.
    "app/operare/efecte/executor.py",
    # Gateway-ul de modele (F3.3, F3.4): contoarele de cotă, blocajele și sănătatea furnizorilor sunt la nivel de
    # agenție (nu țin date de client) și se scriu din orice proces care face un apel, în tranzacții proprii și scurte.
    "app/gateway/limitator.py",
    "app/gateway/sanatate.py",
}


def _surse() -> dict[str, str]:
    return {str(p.relative_to(ROOT)): p.read_text(encoding="utf-8") for p in APP.rglob("*.py")}


def test_conexiunile_la_baza_se_deschid_doar_in_app_db() -> None:
    sablon = re.compile(r"\b(create_engine|psycopg\.connect|AsyncEngine|create_async_engine)\b")
    gasite = [p for p, s in _surse().items() if sablon.search(s) and not p.startswith("app/db/")]
    assert not gasite, f"conexiuni create în afara app/db (ocolesc contextul de client): {gasite}"


def test_contextul_de_autentificare_are_locuri_cunoscute() -> None:
    gasite = {p for p, s in _surse().items() if re.search(r"\bsesiune_auth\b|auth\s*=\s*True", s)}
    assert gasite <= CONTEXT_AUTH, f"context `auth` folosit în locuri noi: {sorted(gasite - CONTEXT_AUTH)}"


def test_contextul_de_agentie_are_locuri_cunoscute() -> None:
    gasite = {p for p, s in _surse().items() if re.search(r"\bsesiune_agentie\b|agency\s*=\s*True", s)}
    assert gasite <= CONTEXT_AGENTIE, (
        f"scop de agenție folosit în locuri noi: {sorted(gasite - CONTEXT_AGENTIE)}"
    )
