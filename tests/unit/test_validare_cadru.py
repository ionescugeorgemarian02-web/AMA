"""F5.1 — nucleele pure ale cadrului de validare: forma verdictului (9.2), agregarea, unirea
instrucțiunilor, cascada
(ordine, oprire) și registrul. Fără bază de date, fără model."""

import datetime as dt
import uuid
from decimal import Decimal

import pytest

from app.validare import agregare, cascada, registru
from app.validare.agregare import Decizie, agrega
from app.validare.intrare import Continut, Intrare, SituatieLivrabil, amprenta_text
from app.validare.registru import DefinitieValidator
from app.validare.verdict import (
    Cost,
    Dovada,
    Rezultat,
    Severitate,
    Treapta,
    Verdict,
    VerdictInvalid,
    avertisment,
    esec,
    trece,
)

D = (Dovada("fragment", "regula"),)


def intrare(text: str = "Un text.", tip: str = "postare", canal: str = "facebook") -> Intrare:
    sit = SituatieLivrabil(uuid.uuid4(), uuid.uuid4(), tip, canal, 1, 0)
    return Intrare(sit, Continut(1, text), dt.datetime(2026, 11, 13, tzinfo=dt.UTC))


# --- forma verdictului
# ---------------------------------------------------------------------------------------


def test_un_esec_cere_dovada_instructiune_si_severitate_de_cel_putin_majora() -> None:
    v = esec("GX", "1", Treapta.V1, dovezi=D, instructiune="  Scoate cuvântul.  ")
    assert v.blocheaza and not v.critic and v.instructiune == "Scoate cuvântul."
    with pytest.raises(VerdictInvalid):
        esec("GX", "1", Treapta.V1, dovezi=(), instructiune="x")
    with pytest.raises(VerdictInvalid):
        esec("GX", "1", Treapta.V1, dovezi=D, instructiune="  ")
    with pytest.raises(VerdictInvalid):
        esec("GX", "1", Treapta.V1, dovezi=D, instructiune="x", severitate=Severitate.MINORA)
    assert esec("GX", "1", Treapta.V1, dovezi=D, instructiune="x", severitate=Severitate.CRITICA).critic


def test_verdictul_trece_nu_are_severitate_iar_scorul_e_intre_0_si_1() -> None:
    assert trece("GX", "1", Treapta.V0).severitate is None
    with pytest.raises(VerdictInvalid):
        Verdict("GX", "1", Treapta.V0, Rezultat.TRECE, Severitate.MINORA)
    with pytest.raises(VerdictInvalid):
        trece("GX", "1", Treapta.V0, scor=1.5)
    with pytest.raises(VerdictInvalid):
        trece("", "1", Treapta.V0)
    with pytest.raises(VerdictInvalid):
        Dovada("f", "  ")


def test_costul_se_aduna_si_fragmentul_dovezii_e_taiat() -> None:
    c = Cost(1, 10, 5, Decimal("0.5"), 3) + Cost(2, 1, 1, Decimal("0.25"), 4)
    assert (c.apeluri_llm, c.tokeni_intrare, c.pret_umbra, c.durata_ms) == (3, 11, Decimal("0.75"), 7)
    assert c.json()["pret_umbra"] == "0.75"
    assert len(Dovada("a" * 1000, "r").fragment) == 300


# --- agregarea
# ------------------------------------------------------------------------------------------------


def _av(cod: str, sev: Severitate, instr: str) -> Verdict:
    return avertisment(cod, "1", Treapta.V1, dovezi=D, instructiune=instr, severitate=sev)


def test_agregarea_fara_probleme_trece() -> None:
    a = agrega([trece("G1", "1", Treapta.V0), trece("G10", "1", Treapta.V1)], prag=4)
    assert a.decizie is Decizie.TRECE and not a.cere_om and a.puncte == 0 and a.instructiune == ""


def test_un_esec_majora_trimite_la_reparatie_iar_unul_critic_in_carantina() -> None:
    m = esec("G2", "1", Treapta.V1, dovezi=D, instructiune="Corectează prețul.")
    c = esec("G3", "1", Treapta.V1, dovezi=D, instructiune="Cerere refuzată.", severitate=Severitate.CRITICA)
    assert agrega([trece("G1", "1", Treapta.V0), m], prag=4).decizie is Decizie.REPARATIE
    assert agrega([m, c], prag=4).decizie is Decizie.CARANTINA, "criticul are întâietate"


def test_avertismentele_se_aduna_iar_peste_prag_merge_la_om() -> None:
    minore = [_av("G10", Severitate.MINORA, f"punct {i}") for i in range(4)]
    a = agrega(minore, prag=4)
    assert a.puncte == 4 and not a.cere_om, "pragul e strict: 4 puncte din 4 nu cer om"
    a = agrega([*minore, _av("G8", Severitate.MAJORA, "hook slab")], prag=4)
    assert a.puncte == 6 and a.cere_om and a.decizie is Decizie.TRECE
    assert not agrega([*minore, *minore], prag=100).cere_om, "pragul e configurabil"


def test_un_esec_nu_cere_om_pentru_avertismente() -> None:
    a = agrega(
        [
            esec("G2", "1", Treapta.V1, dovezi=D, instructiune="x"),
            *[_av("G10", Severitate.MAJORA, str(i)) for i in range(5)],
        ],
        prag=1,
    )
    assert a.decizie is Decizie.REPARATIE and not a.cere_om


def test_instructiunile_tuturor_validatorilor_devin_un_singur_mesaj() -> None:
    b1 = esec("G2", "1", Treapta.V1, dovezi=D, instructiune="Prețul corect este 49 lei.")
    b2 = esec("G3", "1", Treapta.V1, dovezi=D, instructiune="Scoate promisiunea de slăbit.")
    dublura = esec("G9", "1", Treapta.V1, dovezi=D, instructiune="Prețul corect este 49 lei.")
    w = _av("G8", Severitate.MINORA, "Scurtează prima frază.")
    mesaj = agregare.unifica_instructiunile((b1, b2, dublura), (w,))
    linii = mesaj.splitlines()
    assert linii[0].startswith("Textul nu a trecut validarea")
    assert linii[1:] == [
        "1. [G2] Prețul corect este 49 lei.",
        "2. [G3] Scoate promisiunea de slăbit.",
        "3. [G8] Scurtează prima frază.",
    ], "ce blochează primul, instrucțiunea identică o singură dată, fiecare punct își numește validatorul"
    assert agregare.unifica_instructiunile((), ()) == ""
    assert agregare.unifica_instructiunile((), (w,)).startswith("Textul poate fi îmbunătățit")


# --- registrul
# --------------------------------------------------------------------------------------------------


def _def(cod: str, treapta: Treapta, ordine: int = 100, **kw: object) -> DefinitieValidator:
    return DefinitieValidator(cod, f"Validator {cod}", "1", treapta, ordine, **kw)  # type: ignore[arg-type]


def test_registrul_ordoneaza_pe_treapta_apoi_ordine_si_filtreaza_pe_tip_si_canal() -> None:
    with registru.izolat():
        registru.inregistreaza(_def("B", Treapta.V1, 20), lambda i: None)
        registru.inregistreaza(_def("A", Treapta.V1, 10), lambda i: None)
        registru.inregistreaza(_def("Z", Treapta.V0), lambda i: None)
        registru.inregistreaza(_def("E", Treapta.V1, 5, tipuri=frozenset({"email"})), lambda i: None)
        registru.inregistreaza(_def("F", Treapta.V2, canale=frozenset({"tiktok"})), lambda i: None)
        ordine = [p.definitie.cod for p in registru.pasi_pentru("postare", "facebook")]
        assert ordine == ["Z", "A", "B"]
        assert [p.definitie.cod for p in registru.pasi_pentru("email", "email")] == ["Z", "E", "A", "B"]
        assert [p.definitie.cod for p in registru.pasi_pentru("video", "tiktok")] == ["Z", "A", "B", "F"]
    assert not {"A", "B", "Z"} & {d.cod for d in registru.toate()}, "registrul vechi revine după bloc"


def test_judecatorii_si_v4_sunt_optionali_si_treptele_se_potrivesc_cu_modelul() -> None:
    with registru.izolat():
        registru.inregistreaza(_def("A", Treapta.V1), lambda i: None)
        registru.inregistreaza(_def("J", Treapta.V3, foloseste_model=True), lambda i: None)
        registru.inregistreaza(_def("P", Treapta.V4, foloseste_model=True), lambda i: None)
        cod = lambda **kw: [p.definitie.cod for p in registru.pasi_pentru("postare", "facebook", **kw)]  # noqa: E731
        assert cod() == ["A"]
        assert cod(judecatori=True) == ["A", "J"]
        assert cod(judecatori=True, v4=True) == ["A", "J", "P"]
        with pytest.raises(registru.RegistruInvalid):
            registru.inregistreaza(_def("X", Treapta.V1, foloseste_model=True), lambda i: None)
        with pytest.raises(registru.RegistruInvalid):
            registru.inregistreaza(_def("X", Treapta.V3), lambda i: None)
        with pytest.raises(registru.RegistruInvalid):
            registru.inregistreaza(_def("X", Treapta.V5, foloseste_model=True), lambda i: None)


# --- cascada
# ---------------------------------------------------------------------------------------------------


class Jurnal:
    def __init__(self) -> None:
        self.apeluri: list[str] = []

    def pas(self, cod: str, treapta: Treapta, rezultat: str = "trece", **kw: object) -> registru.Pas:
        def f(_i: Intrare) -> Verdict | None:
            self.apeluri.append(cod)
            if rezultat == "nu_se_aplica":
                return None
            if rezultat == "esec":
                return esec(cod, "1", treapta, dovezi=D, instructiune=f"corectează {cod}")
            if rezultat == "avertisment":
                return _av(cod, Severitate.MINORA, f"îmbunătățește {cod}") if treapta is Treapta.V1 else None
            return trece(cod, "1", treapta)

        return registru.Pas(_def(cod, treapta, foloseste_model=not treapta.gratuita, **kw), f)


def test_cascada_se_opreste_dupa_treapta_cu_esec_dar_ruleaza_toti_pasii_treptei() -> None:
    j = Jurnal()
    pasi = [
        j.pas("G1", Treapta.V0),
        j.pas("A", Treapta.V1, "esec"),
        j.pas("B", Treapta.V1, "esec"),  # aceeași treaptă gratuită: rulează și el
        j.pas("C", Treapta.V2),
        j.pas("D", Treapta.V3),
    ]
    verdicte, oprit = cascada.ruleaza_pasii(pasi, intrare())
    assert j.apeluri == ["G1", "A", "B"], "V2 și V3 nu rulează după un eșec în V1"
    assert oprit is Treapta.V1 and [v.validator for v in verdicte if v.blocheaza] == ["A", "B"]


def test_cascada_in_treptele_cu_cost_se_opreste_la_primul_esec() -> None:
    j = Jurnal()
    pasi = [
        j.pas("J1", Treapta.V3, "esec", ordine=1),
        j.pas("J2", Treapta.V3, ordine=2),
        j.pas("P", Treapta.V4),
    ]
    _, oprit = cascada.ruleaza_pasii(pasi, intrare())
    assert j.apeluri == ["J1"], "nu se consumă cotă după primul eșec"
    assert oprit is Treapta.V3


def test_cascada_fara_esec_ruleaza_tot_iar_un_pas_inaplicabil_nu_produce_verdict() -> None:
    j = Jurnal()
    pasi = [j.pas("G1", Treapta.V0), j.pas("N", Treapta.V1, "nu_se_aplica"), j.pas("C", Treapta.V2)]
    verdicte, oprit = cascada.ruleaza_pasii(pasi, intrare())
    assert oprit is None and [v.validator for v in verdicte] == ["G1", "C"]
    assert j.apeluri == ["G1", "N", "C"]


def test_cascada_goala_este_eroare_nu_trecere() -> None:
    with pytest.raises(cascada.FaraValidatori):
        cascada.ruleaza_pasii([], intrare())


def test_un_validator_nu_poate_intoarce_verdictul_altuia() -> None:
    pas = registru.Pas(_def("A", Treapta.V1), lambda i: trece("B", "1", Treapta.V1))
    with pytest.raises(VerdictInvalid):
        cascada.ruleaza_pasii([pas], intrare())
    pas = registru.Pas(_def("A", Treapta.V1), lambda i: trece("A", "1", Treapta.V0))
    with pytest.raises(VerdictInvalid):
        cascada.ruleaza_pasii([pas], intrare())


def test_evaluarea_agrega_si_costul_include_durata() -> None:
    j = Jurnal()
    ev = cascada.evalueaza(
        [j.pas("G1", Treapta.V0), j.pas("W", Treapta.V1, "avertisment")], intrare(), prag=0
    )
    assert ev.agregat.puncte == 1 and ev.agregat.decizie is Decizie.TRECE and ev.agregat.cere_om
    assert all(v.cost.durata_ms >= 0 for v in ev.verdicte)


def test_continutul_expune_toate_bucatile_de_text_si_o_amprenta_stabila() -> None:
    c = Continut(1, "Corp", {"titlu": "Titlu", "hashtaguri": ["#cafea", "#brasov"], "numar": 3, "gol": " "})
    assert [n for n, _ in c.texte()] == ["text", "hashtaguri[0]", "hashtaguri[1]", "titlu"]
    assert c.text_complet == "Corp\n#cafea\n#brasov\nTitlu"
    assert c.amprenta == amprenta_text("Corp", c.campuri) and len(c.amprenta) == 64
    assert amprenta_text("Corp", {"a": 1, "b": 2}) == amprenta_text("Corp", {"b": 2, "a": 1})
