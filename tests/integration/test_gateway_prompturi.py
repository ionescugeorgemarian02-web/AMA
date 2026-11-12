"""F3.7 — registrul de prompturi pe Postgres real: versiuni, stări, versiunea activă nu se modifică (impus în bază),
fișierele din repo."""

from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from app.db import sesiune_agentie
from app.gateway import prompturi
from app.gateway.prompturi import PromptInvalid
from tests.gateway_utile import Clasificare, FabricaModele

pytestmark = pytest.mark.db
SCHEMA = "tests.gateway_utile.Clasificare"


def nou(f: FabricaModele, **kw: object) -> str:
    return f.prompt("clasificare", activ=False, **kw)  # type: ignore[arg-type]


def stari(nume: str) -> dict[int, str]:
    with sesiune_agentie() as db:
        return {p.versiune: p.stare for p in prompturi.lista(db, nume=nume)}


def test_o_versiune_noua_se_creeaza_ciorna_si_se_numeroteaza_in_continuare(
    fabrica_modele: FabricaModele,
) -> None:
    nume = nou(fabrica_modele)
    with sesiune_agentie() as db:
        v2 = prompturi.creeaza(db, nume, profil="clasificare", sablon="Altfel: {{text}}", schema=Clasificare)
        assert (v2.versiune, v2.stare) == (2, "ciorna")
        assert v2.schema_nume == SCHEMA and v2.schema_json["properties"]["eticheta"]
    assert stari(nume) == {1: "ciorna", 2: "ciorna"}


def test_activarea_retrage_versiunea_anterioara_si_exista_o_singura_versiune_activa(
    fabrica_modele: FabricaModele,
) -> None:
    nume = fabrica_modele.prompt("clasificare")  # v1 activ
    with sesiune_agentie() as db:
        prompturi.creeaza(db, nume, profil="clasificare", sablon="V2 {{text}}", schema=Clasificare)
        prompturi.activeaza(db, nume, 2)
    assert stari(nume) == {1: "retras", 2: "activ"}
    with sesiune_agentie() as db:
        activ = prompturi.rezolva(db, nume)
        v1 = prompturi.rezolva(db, f"{nume}@1")
        assert activ is not None and activ.versiune == 2 and activ.sablon == "V2 {{text}}"
        assert v1 is not None and v1.stare == "retras"  # o versiune anume se poate cere oricând (evaluări)
        assert prompturi.rezolva(db, f"{nume}@9") is None and prompturi.rezolva(db, "nu.exista") is None


def test_baza_refuza_modificarea_unei_versiuni_active_sau_retrase(
    fabrica_modele: FabricaModele, admin_engine: Engine
) -> None:
    nume = fabrica_modele.prompt("clasificare")
    for camp in ("sablon", "sistem", "profil", "schema_nume"):
        with pytest.raises(DBAPIError, match="nu se modifică"), admin_engine.begin() as c:
            c.execute(text(f"UPDATE gateway_prompturi SET {camp} = 'x' WHERE nume = :n"), {"n": nume})
    with sesiune_agentie() as db, pytest.raises(PromptInvalid, match="nu mai e ciornă"):
        prompturi.modifica_ciorna(db, nume, 1, sablon="altceva")
    with sesiune_agentie() as db:
        prompturi.retrage(db, nume, 1)
    with pytest.raises(DBAPIError, match="nu se modifică"), admin_engine.begin() as c:
        c.execute(text("UPDATE gateway_prompturi SET sablon = 'x' WHERE nume = :n"), {"n": nume})
    with pytest.raises(DBAPIError, match="tranziție nepermisă"), admin_engine.begin() as c:
        c.execute(text("UPDATE gateway_prompturi SET stare = 'activ' WHERE nume = :n"), {"n": nume})
    with pytest.raises(DBAPIError, match="tranziție nepermisă"), admin_engine.begin() as c:
        c.execute(text("UPDATE gateway_prompturi SET stare = 'ciorna' WHERE nume = :n"), {"n": nume})


def test_baza_refuza_doua_versiuni_active_cu_acelasi_nume(
    fabrica_modele: FabricaModele, admin_engine: Engine
) -> None:
    nume = fabrica_modele.prompt("clasificare")
    with sesiune_agentie() as db:
        prompturi.creeaza(db, nume, profil="clasificare", sablon="V2 {{text}}", schema=Clasificare)
    with pytest.raises(DBAPIError, match="gateway_prompturi_un_activ"), admin_engine.begin() as c:
        c.execute(
            text("UPDATE gateway_prompturi SET stare = 'activ' WHERE nume = :n AND versiune = 2"), {"n": nume}
        )


def test_ciorna_se_poate_edita_pana_la_activare(fabrica_modele: FabricaModele) -> None:
    nume = nou(fabrica_modele)
    with sesiune_agentie() as db:
        prompturi.modifica_ciorna(db, nume, 1, sablon="Nou {{text}}")
        p = prompturi.rezolva(db, f"{nume}@1")
        assert p is not None and p.sablon == "Nou {{text}}"
        prompturi.activeaza(db, nume, 1)
        with pytest.raises(PromptInvalid, match="se activează doar o ciornă"):
            prompturi.activeaza(db, nume, 1)


def test_profil_necunoscut_si_nume_nepermis(fabrica_modele: FabricaModele) -> None:
    with sesiune_agentie() as db:
        with pytest.raises(PromptInvalid, match="profil necunoscut"):
            prompturi.creeaza(db, "ok.nume", profil="nu_exista", sablon="x", schema=Clasificare)
        with pytest.raises(PromptInvalid, match="nume de prompt"):
            prompturi.creeaza(db, "Nume Rau", profil="clasificare", sablon="x", schema=Clasificare)


def test_crearea_si_activarea_lasa_urma_in_audit(fabrica_modele: FabricaModele, admin_engine: Engine) -> None:
    nume = fabrica_modele.prompt("clasificare")
    with admin_engine.connect() as c:
        actiuni = [
            r[0]
            for r in c.execute(
                text("SELECT actiune FROM jurnal_audit WHERE obiect_id = :o ORDER BY creat_la"),
                {"o": f"{nume}@1"},
            )
        ]
    assert actiuni == ["gateway.prompt_creat", "gateway.prompt_activat"]


FISIER = """---
profil: clasificare
schema: {schema}
stare: {stare}
---
@@sistem
Ești un clasificator.
@@utilizator
{corp} {{{{text}}}}
"""


def test_fisierele_din_repo_intra_in_baza_si_versiunile_nu_se_modifica(
    fabrica_modele: FabricaModele, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prompturi, "PREFIXE_SCHEMA", ("app.", "tests."))
    nume = f"t{id(tmp_path):x}.din_fisier"
    fabrica_modele.prompturi.append(nume)

    def fisier(v: int, stare: str, corp: str) -> None:
        (tmp_path / f"{nume}.v{v}.md").write_text(
            FISIER.format(schema=SCHEMA, stare=stare, corp=corp), encoding="utf-8"
        )

    fisier(1, "activ", "Prima")
    with sesiune_agentie() as db:
        assert prompturi.sincronizeaza(db, tmp_path) == [f"{nume}@1"]
        assert prompturi.sincronizeaza(db, tmp_path) == []  # idempotent
        p = prompturi.rezolva(db, nume)
        assert p is not None and p.sablon == "Prima {{text}}" and p.sistem == "Ești un clasificator."
    # modificarea unei versiuni active din fișier este o EROARE: fișierul trebuie să devină o versiune nouă
    fisier(1, "activ", "Schimbată pe furiș")
    with sesiune_agentie() as db, pytest.raises(PromptInvalid, match="versiunile nu se modifică"):
        prompturi.sincronizeaza(db, tmp_path)
    fisier(1, "activ", "Prima")
    fisier(2, "ciorna", "A doua")
    with sesiune_agentie() as db:
        assert prompturi.sincronizeaza(db, tmp_path) == [f"{nume}@2"]
    fisier(2, "ciorna", "A doua, îmbunătățită")  # o ciornă se poate rescrie
    with sesiune_agentie() as db:
        assert prompturi.sincronizeaza(db, tmp_path) == [f"{nume}@2"]
    assert stari(nume) == {1: "activ", 2: "ciorna"}
    fisier(2, "activ", "A doua, îmbunătățită")  # ciorna din fișier devine activă
    with sesiune_agentie() as db:
        assert prompturi.sincronizeaza(db, tmp_path) == [f"{nume}@2"]
    assert stari(nume) == {1: "retras", 2: "activ"}
