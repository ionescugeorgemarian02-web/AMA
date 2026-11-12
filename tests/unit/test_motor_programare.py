"""F2.6 — partea pură a planificatorului: cron, nume, fus orar, context."""

import pytest

from app.operare import motor
from app.operare.motor.programare import cron_complet
from tests.integration import fluxuri_programare as probe


def test_cron_cu_cinci_campuri_ruleaza_la_minut() -> None:
    assert cron_complet("* * * * *") == "0 * * * * *"
    assert cron_complet("*/15 9-17 * * 1-5") == "0 */15 9-17 * * 1-5"
    assert cron_complet("  30   18 * *  *  ") == "0 30 18 * * *"


def test_cron_cu_sase_campuri_pastreaza_secundele() -> None:
    assert cron_complet("*/2 * * * * *") == "*/2 * * * * *"


@pytest.mark.parametrize("cron", ["", "* * * *", "* * * * * * *", "un cron"])
def test_cron_cu_numar_gresit_de_campuri(cron: str) -> None:
    with pytest.raises(motor.ProgramareInvalida, match="câmpuri"):
        cron_complet(cron)


@pytest.mark.parametrize("nume", ["", "A", "1x", "cu spatiu", "x" * 100])
def test_nume_de_programare_nepermis(nume: str) -> None:
    with pytest.raises(motor.ProgramareInvalida, match="nume"):
        motor.programeaza_recurent(nume, "* * * * *", probe.tic)


def test_fus_orar_necunoscut() -> None:
    with pytest.raises(motor.ProgramareInvalida, match="fus orar"):
        motor.programeaza_recurent("proba.fus", "* * * * *", probe.tic, fus_orar="Marte/Olympus")


def test_contextul_primeste_doar_identificatori() -> None:
    with pytest.raises(motor.ProgramareInvalida, match="context"):
        motor.programeaza_recurent("proba.ctx", "* * * * *", probe.tic, context={"text": "x" * 500})
    with pytest.raises(motor.ProgramareInvalida, match="context"):
        motor.programeaza_recurent("proba.ctx", "* * * * *", probe.tic, context={"a": {"b": 1}})


def test_programarea_declarata_are_forma_completa() -> None:
    p = motor.programeaza_recurent("proba.forma", "30 18 * * 1-5", probe.tic, context={"tenant_id": "t1"})
    assert (p.cron, p.fus_orar, p.coada, p.flux) == (
        "0 30 18 * * 1-5",
        "Europe/Bucharest",
        "io",
        "programare.tic",
    )
    assert p in motor.programari_declarate()


def test_o_functie_fara_decorator_nu_poate_fi_programata() -> None:
    def oarecare(moment: object, context: object) -> None: ...

    with pytest.raises(TypeError, match="nu este un flux"):
        motor.programeaza_recurent("proba.nedecorata", "* * * * *", oarecare)
