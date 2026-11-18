"""F14.1 — Optimizatorul de prompturi. „Gata când”: o rulare produce un candidat cu scor pe setul de test."""

from typing import Any

import pytest
from sqlalchemy import Engine, text

from app import gateway
from app.db import sesiune_agentie
from app.invatare import optimizator
from app.invatare.optimizator import OptimizareRefuzata
from tests.integration import utile_optimizare as u

pytestmark = pytest.mark.db


def test_o_rulare_produce_un_candidat_cu_scor_pe_test(admin_engine: Engine) -> None:
    nume = u.prompt_de_proba()
    with sesiune_agentie() as db:
        o = optimizator.optimizeaza(
            db, nume, executor=u.model_simulat, propunator=u.propunator_simulat, exemple=u.set_aur()
        )
        oid = o.id
    with sesiune_agentie() as db:
        o = next(x for x in optimizator.istoric(db, nume) if x.id == oid)
        assert o.stare == "candidat" and o.candidat_versiune == 3  # v2 = varianta slabă, v3 = cea bună
        assert o.scor_candidat is not None and o.scor_campion is not None
        assert o.scor_candidat >= o.scor_campion + optimizator.MARJA
        assert o.raport["test"]["candidat"]["n"] == o.raport["exemple"]["test"] >= 2
        assert u.INSTRUCTIUNE_BUNA in o.raport["ce_s_a_schimbat"]["schimbare"]
        assert len(o.raport["variante"]) == 2
        stari = {p.versiune: p.stare for p in gateway.prompturi.lista(db, nume=nume)}
        assert stari == {1: "activ", 2: "retras", 3: "ciorna"}  # campionul rămâne activ până la F14.2
        cand = gateway.prompturi.rezolva(db, f"{nume}@3")
        assert cand is not None and cand.sistem.startswith(u.SISTEM_CAMPION)  # doar s-a adăugat
    with admin_engine.connect() as c:
        urme = c.execute(
            text(
                "SELECT actiune, rezultat FROM urme WHERE componenta = 'invatare.optimizator' AND obiect_id LIKE :n"
            ),
            {"n": f"{nume}%"},
        ).all()
    assert ("optimizeaza", "ok") in urme and sum(a == "scoreaza" for a, _ in urme) == 5


def test_fara_castig_nu_ramane_candidat() -> None:
    nume = u.prompt_de_proba()
    with sesiune_agentie() as db:
        o = optimizator.optimizeaza(
            db, nume, executor=u.model_simulat, propunator=u.propunator_inutil, exemple=u.set_aur()
        )
        assert o.stare == "fara_candidat" and o.candidat_versiune is None and "marja" in o.motiv
        assert {p.versiune: p.stare for p in gateway.prompturi.lista(db, nume=nume)} == {
            1: "activ",
            2: "retras",
        }


def test_conformitatea_scazuta_respinge_candidatul() -> None:
    nume = u.prompt_de_proba()

    def model_neconform(db: Any, referinta: str, ex: optimizator.Exemplu) -> dict[str, Any] | None:
        iesire = u.model_simulat(db, referinta, ex)
        if referinta.endswith("@2") and iesire is not None:  # candidatul scrie fără diacritice
            iesire["hookuri"][0]["text"] += " Afla ce pregatim saptamana aceasta in cartier si dupa."
        return iesire

    def propunator(db: Any, campion: Any, picate: Any) -> list[optimizator.Varianta]:
        return [
            optimizator.Varianta(campion.sistem + "\n" + u.INSTRUCTIUNE_BUNA, campion.sablon, "bună", "x")
        ]

    with sesiune_agentie() as db:
        o = optimizator.optimizeaza(
            db, nume, executor=model_neconform, propunator=propunator, exemple=u.set_aur()
        )
    assert o.stare == "fara_candidat" and "conformitate" in o.motiv


def test_propunatorul_prin_gateway_si_refuzurile(monkeypatch: pytest.MonkeyPatch) -> None:
    nume = u.prompt_de_proba()
    cerute: list[str] = []

    def apeleaza_fals(db: Any, **kw: Any) -> Any:  # SIMULAT: gateway-ul
        cerute.append(kw["prompt"])
        assert kw["schema"] is optimizator.PropunereReflectie and "esecuri" in kw["variabile"]
        iesire = optimizator.PropunereReflectie(
            incredere=0.7,
            instructiuni=[{"instructiune": u.INSTRUCTIUNE_BUNA, "motiv": "lipsesc cuvintele-cheie"}],
        )
        return type("R", (), {"iesire": iesire})()

    monkeypatch.setattr(gateway, "apeleaza", apeleaza_fals)
    with sesiune_agentie() as db:
        o = optimizator.optimizeaza(db, nume, executor=u.model_simulat, exemple=u.set_aur())
        assert cerute == [optimizator.PROMPT_REFLECTIE] and o.stare == "candidat"
        with pytest.raises(OptimizareRefuzata, match="versiune activă"):
            optimizator.optimizeaza(db, "proba.nu_exista", executor=u.model_simulat, exemple=u.set_aur())
        with pytest.raises(OptimizareRefuzata, match="prea mic"):
            optimizator.optimizeaza(db, nume, executor=u.model_simulat, exemple=u.set_aur()[:2])
