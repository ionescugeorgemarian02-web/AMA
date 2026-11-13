"""F3.6 — testul comparativ pe română, cu furnizori falși de calități diferite. „Gata când”: fiecare model are scor pe fiecare
profil, iar rutarea folosește scorurile (dovedit mai jos). NEVERIFICAT: rularea pe modele reale și evaluarea umană reală."""

import json
import uuid
import zlib
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import Engine, text

from app.db import sesiune_agentie
from app.gateway import criterii, evaluare, registru
from app.gateway.profiluri import PROFILURI
from app.operare import motor
from app.operare.motor import Coada
from tests.furnizor_fals import CerereInregistrata, FurnizorFals
from tests.gateway_utile import CeasControlat, FabricaModele, gazda
from tests.integration.test_gateway_apeluri import apeleaza

pytestmark = pytest.mark.db
SARCINI = evaluare.incarca_sarcini()
PROFILURI_NUME = sorted(p.nume for p in PROFILURI)
FRAZA = "Vă așteptăm cu drag, într-o atmosferă plăcută, în fiecare zi. "
GRESIT = {"pozitiv": "spam", "negativ": "pozitiv", "neutru": "spam", "intrebare": "spam", "reclamatie": "pozitiv",
          "spam": "neutru", "acceptat": "respins", "respins": "acceptat", "continua": "opreste", "opreste": "pivot",
          "pivot": "continua"}  # fmt: skip


def _pliat(t: str) -> str:
    return criterii.plie(t)


def raspuns_pentru(s: evaluare.Sarcina, calitate: str) -> dict[str, Any]:
    """Ce ar răspunde un model de o calitate dată: `bun` (corect, cu diacritice), `mediu` (fără diacritice, o treime din
    răspunsurile scurte greșite), `slab` (răspunsuri greșite sau prea scurte)."""
    c = s.criterii
    gresit_aici = calitate == "slab" or (calitate == "mediu" and zlib.crc32(s.id.encode()) % 3 == 0)
    if "raspuns_exact" in c:
        camp, valoare = c["raspuns_exact"]["camp"], c["raspuns_exact"]["valoare"]
        rasp = GRESIT[valoare] if gresit_aici else valoare
        motiv = (
            "Nu."
            if calitate == "slab"
            else "Motivul este că datele din descriere susțin această decizie, în mod clar."
        )
        if calitate == "mediu":
            motiv = _pliat(motiv)
        out: dict[str, Any] = {camp: rasp, "dovezi": ["d"], "incredere": 0.8}
        if camp != "eticheta":
            out["motiv"] = motiv
        return out
    ob = " ".join(c.get("cuvinte_obligatorii", [])) if calitate != "slab" else ""
    text_ = ob + ". "
    while len(text_) < c.get("lungime_min", 0) + 5:
        text_ += FRAZA
    text_ = text_[: c.get("lungime_max", 10_000)]
    if calitate == "slab":
        text_ = "Ok."
    if calitate == "mediu":
        text_ = text_.translate(str.maketrans("ăâîșțĂÂÎȘȚ", "aaistAAIST"))
    return {"text": text_, "dovezi": ["d"], "incredere": 0.8}


def furnizor_de_calitate(calitati: dict[str, str]) -> Callable[[CerereInregistrata], str]:
    def text_pentru(c: CerereInregistrata) -> str:
        continut = c.corp["messages"][-1]["content"]
        s = next(t for t in SARCINI if t.instructiune in continut and t.intrare in continut)
        return json.dumps(raspuns_pentru(s, calitati[c.gazda]), ensure_ascii=False)

    return text_pentru


@pytest.fixture(autouse=True)
def _mediu(cheie_proba: str, ceas_controlat: CeasControlat, fals: FurnizorFals) -> None:
    fals.tokeni = (200, 100)


class Trei:
    def __init__(self, f: FabricaModele) -> None:
        self.slab = f.model(
            f.furnizor(), identificator="slab", nivel="T1", pret_umbra_intrare=0.1, pret_umbra_iesire=0.1
        )
        self.mediu = f.model(f.furnizor(), identificator="mediu", nivel="T2")
        self.bun = f.model(f.furnizor(), identificator="bun", nivel="T3")
        self.calitati = {gazda(self.slab): "slab", gazda(self.mediu): "mediu", gazda(self.bun): "bun"}


@pytest.fixture
def trei(fabrica_modele: FabricaModele, fals: FurnizorFals) -> Trei:
    t = Trei(fabrica_modele)
    fals.text = furnizor_de_calitate(t.calitati)
    return t


def scoruri(m: Any) -> dict[str, float]:
    with sesiune_agentie() as db:
        c = next(x for x in registru.candidati(db) if x.cod == m.cod)
    return c.scor


def test_fiecare_model_are_scor_pe_fiecare_profil_si_scorurile_urmeaza_calitatea(trei: Trei) -> None:
    rulari = {n: evaluare.ruleaza(getattr(trei, n).cod) for n in ("slab", "mediu", "bun")}
    for n, r in rulari.items():
        assert r.stare == "terminata" and r.facute == r.total == 72
        assert sorted(scoruri(getattr(trei, n))) == PROFILURI_NUME  # câte un scor pe fiecare profil din 8.2
    slab, mediu, bun = (scoruri(getattr(trei, n)) for n in ("slab", "mediu", "bun"))
    for p in PROFILURI_NUME:
        assert bun[p] == 1.0
        assert slab[p] < mediu[p] < bun[p], (p, slab[p], mediu[p], bun[p])
    # istoricul păstrează fiecare rulare, cu scorul ei
    with sesiune_agentie() as db:
        istoric = [
            r
            for r in evaluare.istoric(db, 50)
            if r["model_cod"] in {trei.slab.cod, trei.mediu.cod, trei.bun.cod}
        ]
    assert len(istoric) == 3 and all(r["stare"] == "terminata" and r["in_registru"] for r in istoric)
    assert next(r for r in istoric if r["model_cod"] == trei.bun.cod)["scor"]["creatie"]["final"] == 1.0


@pytest.fixture
def lant_creatie(admin_engine: Engine, trei: Trei) -> Iterator[None]:
    """Lanțul profilului seminței `creatie`, înlocuit cu cele trei modele în ordinea cea mai proastă (slab primul)."""
    with admin_engine.connect() as c:
        original = c.execute(
            text("SELECT lant, nivel_min FROM gateway_profiluri WHERE nume = 'creatie'")
        ).one()
    with admin_engine.begin() as c:
        c.execute(
            text("UPDATE gateway_profiluri SET lant = :l, nivel_min = 'T1' WHERE nume = 'creatie'"),
            {"l": [trei.slab.cod, trei.mediu.cod, trei.bun.cod]},
        )
    yield
    with admin_engine.begin() as c:
        c.execute(
            text("UPDATE gateway_profiluri SET lant = :l, nivel_min = :n WHERE nume = 'creatie'"),
            {"l": list(original[0]), "n": original[1]},
        )


def test_rutarea_foloseste_scorurile_modelul_bun_ajunge_primul(
    tenant: uuid.UUID, trei: Trei, lant_creatie: None, fabrica_modele: FabricaModele, fals: FurnizorFals
) -> None:
    prompt = fabrica_modele.prompt("creatie")
    calitate = fals.text
    fals.text = '{"eticheta": "x", "dovezi": [], "incredere": 0.5}'
    # înainte de test, fără scoruri: contează lanțul, deci ajunge la primul din el (slab)
    assert apeleaza(tenant, prompt).model == trei.slab.cod
    fals.text = calitate  # la evaluare, fiecare furnizor răspunde la calitatea lui
    for n in ("slab", "mediu", "bun"):
        evaluare.ruleaza(getattr(trei, n).cod, profiluri=["creatie"])
    fals.text = '{"eticheta": "x", "dovezi": [], "incredere": 0.5}'
    fals.cereri.clear()
    assert apeleaza(tenant, prompt).model == trei.bun.cod  # scorul bate poziția în lanț
    assert [c.gazda for c in fals.cereri] == [gazda(trei.bun)]
    # modelul bun cade: urmează cel mediu (scor), nu cel slab
    fals.scenariu(gazda(trei.bun), permanent="5xx")
    assert apeleaza(tenant, prompt).model == trei.mediu.cod


def test_cota_epuizata_opreste_rularea_si_ea_continua_fara_sa_refaca_ce_s_a_facut(
    fabrica_modele: FabricaModele, fals: FurnizorFals, ceas_controlat: CeasControlat
) -> None:
    m = fabrica_modele.model(fabrica_modele.furnizor(cereri_zi=5), identificator="strans", nivel="T2")
    fals.text = furnizor_de_calitate({gazda(m): "bun"})
    r = evaluare.ruleaza(m.cod, profiluri=["clasificare"])  # P3: plafonul zilei e 90% din 5 = 4
    assert (r.stare, r.facute, r.total) == ("amanata", 4, 12) and r.amanata_pana_la is not None
    assert scoruri(m) == {}  # nimic în registru până nu se termină rularea
    ceas_controlat.avanseaza(86_400)
    r2 = evaluare.ruleaza(m.cod, rulare_id=r.id, profiluri=["clasificare"])
    assert (r2.stare, r2.facute) == ("amanata", 8)
    ceas_controlat.avanseaza(86_400)
    r3 = evaluare.ruleaza(m.cod, rulare_id=r.id, profiluri=["clasificare"])
    assert r3.stare == "terminata" and r3.facute == 12 and scoruri(m) == {"clasificare": 1.0}
    assert len(fals.cereri_la(gazda(m))) == 12  # fiecare sarcină o dată, nicio refacere


def test_nota_umana_se_importa_din_csv_si_schimba_scorul_din_registru(trei: Trei, om: uuid.UUID) -> None:
    r = evaluare.ruleaza(trei.bun.cod, profiluri=["creatie"])
    assert scoruri(trei.bun) == {"creatie": 1.0}
    csv_text = "sarcina_id,nota\n" + "\n".join(f"creatie-{i:02d},2" for i in range(1, 5))
    with sesiune_agentie() as db:
        assert evaluare.importa_note(db, r.id, csv_text, utilizator_id=om) == 4
    assert scoruri(trei.bun)["creatie"] == pytest.approx(0.6 * 1.0 + 0.4 * 0.25)  # nota medie 2 din 5 → 0,25
    with sesiune_agentie() as db:
        rez = evaluare.rezultate(db, r.id)
        assert sum(1 for x in rez if x["nota_umana"] == 2 and x["nota_de"] == om) == 4
        for rau in (
            "sarcina_id,nota\ncreatie-01,9",
            "sarcina_id,nota\ncreatie-01,abc",
            "x,y\n1,2",
            "sarcina_id,nota\nnu-99,3",
        ):
            with pytest.raises(evaluare.NotaInvalida):
                evaluare.importa_note(db, r.id, rau, utilizator_id=om)


def test_un_model_care_raspunde_in_afara_schemei_primeste_zero_pe_acele_sarcini(
    fabrica_modele: FabricaModele, fals: FurnizorFals
) -> None:
    m = fabrica_modele.model(fabrica_modele.furnizor(), identificator="stricat", nivel="T2")
    fals.scenariu(gazda(m), permanent="schema_gresita")
    r = evaluare.ruleaza(m.cod, profiluri=["clasificare"], pe_profil=3)
    assert r.stare == "terminata" and r.scor is not None and r.scor["clasificare"]["final"] == 0.0
    with sesiune_agentie() as db:
        rez = evaluare.rezultate(db, r.id)
    assert {x["stare"] for x in rez} == {"invalid"} and all(x["raspuns"] is None for x in rez)


def test_fluxul_de_evaluare_ruleaza_pe_coada_de_invatare_si_se_reprogrameaza_la_amanare(
    fabrica_modele: FabricaModele, fals: FurnizorFals, porneste_executor: Any, ceas_controlat: CeasControlat
) -> None:
    from app.gateway import fluxuri

    m = fabrica_modele.model(fabrica_modele.furnizor(cereri_zi=5), identificator="flux", nivel="T2")
    fals.text = furnizor_de_calitate({gazda(m): "bun"})
    assert fluxuri.coada_pentru(m.cod) is Coada.INVATARE
    porneste_executor()
    job = motor.trimite(fluxuri.evalueaza, m.cod, "", coada=Coada.INVATARE, cheie="evaluare-flux-proba")
    assert motor.asteapta_flux(job, timeout_sec=60).stare is motor.StareJob.TERMINAT
    with sesiune_agentie() as db:
        [rulare] = [r for r in evaluare.istoric(db, 50) if r["model_cod"] == m.cod]
    assert (
        rulare["stare"] == "amanata"
        and rulare["sarcini_facute"] == 4
        and rulare["amanata_pana_la"] > ceas_controlat.t  # ceasul aplicației e cel controlat, nu cel real
    )
