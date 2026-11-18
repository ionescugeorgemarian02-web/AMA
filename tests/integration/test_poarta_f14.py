"""Poarta F14: un prompt optimizat a bătut campionul, a fost promovat și a fost măsurat față de grupul de control.

Totul trece prin componentele reale: gateway-ul (cu un furnizor SIMULAT prin HTTP, `FurnizorFals`), registrul
de prompturi, optimizatorul (cu promptul real de reflecție din `prompts/`), validarea (conformitatea G10),
criteriile setului de aur, rutarea și jobul promovărilor, testul A/B formal și urmele. Livrabilele sunt simulate:
fiecare primește un exemplu din setul de aur, se produce prin gateway cu versiunea rutată și se scorează ca în
optimizator (în locul verdictului cascadei, NECONECTAT în producție)."""

import datetime as dt
import functools
import json
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from app import gateway
from app.db import sesiune_agentie
from app.invatare import optimizator, promovare, teste_ab
from tests.furnizor_fals import CerereInregistrata, FurnizorFals
from tests.gateway_utile import FabricaModele
from tests.integration import utile_optimizare as u

pytestmark = pytest.mark.db
ACUM = dt.datetime.now(dt.UTC)
FISIER_REFLECTIE = Path(__file__).resolve().parents[2] / "prompts" / "invatare.reflectie.v1.md"
SET = u.set_aur()


def model_fals(cerere: CerereInregistrata) -> str:
    """# SIMULAT: modelul din spatele gateway-ului. Reflecția propune instrucțiunea bună; generatorul de hook-uri
    folosește cuvintele-cheie din brief doar dacă mesajul de sistem i-o cere (la o treime din briefuri, doar
    unul din două, ca scorurile să varieze)."""
    corp = cerere.text_prompt
    if "Exemplele ratate" in corp:
        return json.dumps({"incredere": 0.7, "instructiuni": [
            {"instructiune": u.INSTRUCTIUNE_SLABA, "motiv": "hook-urile lungi se citesc greu"},
            {"instructiune": u.INSTRUCTIUNE_BUNA, "motiv": "exemplele ratate nu foloseau cuvintele-cheie din brief"},
        ]}, ensure_ascii=False)  # fmt: skip
    i, ex = next((i, e) for i, e in enumerate(SET) if e.variabile["brief"] in corp)
    iesire = u.model_simulat_text(
        u.INSTRUCTIUNE_BUNA in corp, ex.criterii["cuvinte_obligatorii"], partial=i % 3 == 0
    )
    return json.dumps({"incredere": 0.8, **iesire}, ensure_ascii=False)


def livrabile(nume: str, n: int, *, start: int) -> dict[str, int]:
    """n livrabile: rutarea reală, producția prin gateway, scorul pe criteriile exemplului și conformitatea G10."""
    grupuri = {"campion": 0, "candidat": 0}
    for k in range(start, start + n):
        ex, cheie = SET[k % len(SET)], f"livrabil-{k}"
        with sesiune_agentie() as db:
            r = promovare.ruteaza(db, nume, cheie)
            assert r.promovare_id is not None and r.grup is not None
            for ref, grup, umbra in ((r.folosit, r.grup, False), (r.umbra, "candidat", True)):
                if ref is None:
                    continue
                scor, conform, _ = optimizator.evalueaza_iesire(ex, optimizator.executor_gateway(db, ref, ex))
                promovare.observa(
                    db, r.promovare_id, grup=grup, cheie=cheie, scor=scor, conform=conform, umbra=umbra
                )
            grupuri[r.grup] += 1
    return grupuri


def test_poarta_f14(
    cheie_proba: str,
    ceas_controlat: object,
    fals: FurnizorFals,
    fabrica_modele: FabricaModele,
    admin_engine: Engine,
) -> None:
    fals.text = model_fals
    model = fabrica_modele.model(fabrica_modele.furnizor())
    profil = fabrica_modele.profil([model.cod])
    nume = u.prompt_de_proba(profil=profil)
    reflectie = f"{nume}_reflectie"
    f = gateway.prompturi.citeste_fisier(FISIER_REFLECTIE)
    with sesiune_agentie() as db:
        gateway.prompturi.creeaza(db, reflectie, profil=profil, sablon=f.sablon, sistem=f.sistem,
                                  schema=optimizator.PropunereReflectie)  # fmt: skip
        gateway.prompturi.activeaza(db, reflectie, 1)
    fabrica_modele.prompturi += [nume, reflectie]

    # 1. Optimizatorul, prin gateway: candidatul bate campionul pe setul de test
    with sesiune_agentie() as db:
        o = optimizator.optimizeaza(
            db,
            nume,
            exemple=SET,
            propunator=functools.partial(optimizator.propunator_gateway, prompt=reflectie),
        )
        assert o.stare == "candidat", o.motiv
        assert o.scor_candidat is not None and o.scor_campion is not None
        assert o.scor_candidat >= o.scor_campion + optimizator.MARJA
        assert o.raport["test"]["candidat"]["conformitate"] >= o.raport["test"]["campion"]["conformitate"]
        pid = promovare.porneste(db, o.id, acum=ACUM).id
    antrenare, test = optimizator.imparte(SET)
    assert len(fals.cereri) == 1 + 3 * len(antrenare) + 2 * len(
        test
    )  # reflecția; 3 versiuni pe antrenare, 2 pe test

    # 2. Umbra, canarul, producția: jobul promovărilor face trecerile
    livrabile(nume, 20, start=0)
    assert promovare.ruleaza(acum=ACUM) == 1 and etapa(pid) == "canar"
    n = livrabile(nume, 400, start=100)  # ~10% pe candidat: cel puțin MINIM_CANAR livrabile ale lui
    assert promovare.MINIM_CANAR <= n["candidat"] <= 70
    assert promovare.ruleaza(acum=ACUM) == 1 and etapa(pid) == "productie"
    with sesiune_agentie() as db:
        activ = gateway.prompturi.rezolva(db, nume)
        assert activ is not None and activ.versiune == o.candidat_versiune  # promovat: 90% din trafic
        p = promovare.istoric(db, nume)[0]
        assert p.test_ab_id is not None
        t = db.get(teste_ab.ExperimentFormal, p.test_ab_id)
        assert t is not None and t.stare == "in_curs" and t.varianta_a == f"{nume}@1" and len(t.ipoteza) > 10
        n_cerut = t.n_pe_varianta

    # 3. Măsurarea față de grupul de control (10% pe campionul vechi), cu testul formal declarat dinainte
    n = livrabile(nume, 700, start=1000)
    assert n["campion"] >= n_cerut and 0.05 <= n["campion"] / 700 <= 0.16
    assert promovare.ruleaza(acum=ACUM) == 1 and etapa(pid) == "promovat"
    with sesiune_agentie() as db:
        p = promovare.istoric(db, nume)[0]
        t = db.get(teste_ab.ExperimentFormal, p.test_ab_id)
        assert t is not None and t.verdict == "castiga_b" and t.rezultat["p"] < t.alfa
        assert t.rezultat["n_folosit"] == n_cerut <= min(t.rezultat["n_a"], t.rezultat["n_b"])
        assert p.castig["concluzie"] == "castiga_b" and p.castig["medie_b"] > p.castig["medie_a"]
        assert [x["in"] for x in p.istoric] == ["umbra", "canar", "productie", "promovat"]
        assert promovare.ruteaza(db, nume, "dupa").folosit == nume
        activ = gateway.prompturi.rezolva(db, nume)
        assert (
            activ is not None
            and u.INSTRUCTIUNE_BUNA in activ.sistem
            and activ.sistem.startswith(u.SISTEM_CAMPION)
        )

    # 4. Urmele: rularea, fiecare etapă, declararea și verdictul testului
    with admin_engine.connect() as c:
        urme = c.execute(
            text(
                "SELECT componenta, actiune FROM urme WHERE (componenta = 'invatare.optimizator' AND actiune = "
                "'optimizeaza' AND obiect_id = :n) OR (componenta = 'invatare.promovari' AND obiect_id = :p) OR "
                "(componenta = 'invatare.teste_ab' AND obiect_id = :t) ORDER BY la, id"
            ),
            {"n": nume, "p": str(pid), "t": str(p.test_ab_id)},
        ).all()  # fmt: skip
    assert [a for _, a in urme] == [
        "optimizeaza", "etapa_umbra", "etapa_canar", "declara", "etapa_productie", "verdict", "etapa_promovat",
    ]  # fmt: skip


def etapa(pid: object) -> str:
    with sesiune_agentie() as db:
        p = db.get(promovare.Promovare, pid)
        assert p is not None
        return p.etapa
