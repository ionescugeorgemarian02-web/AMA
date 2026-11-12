"""F3.2 — ieșiri structurate: validarea răspunsului, o singură reparație, eroare tipizată. Fără rețea: răspunsuri
fabricate trec printr-o funcție `trimite` dată."""

from typing import Literal

import pytest

from app.gateway.iesire import Iesire, extrage_json, schema_json, valideaza
from app.gateway.structurat import IesireNevalida, ruleaza_structurat
from app.gateway.tipuri import Mesaj, RaspunsModel


class Clasificare(Iesire):
    eticheta: Literal["pozitiv", "negativ", "neutru"]


VALID = '{"eticheta": "negativ", "dovezi": ["a întârziat"], "incredere": 0.8}'
MESAJE = (Mesaj("system", "Clasifică."), Mesaj("user", "Livrarea a întârziat."))


def raspuns(text: str, i: int = 10, o: int = 5) -> RaspunsModel:
    return RaspunsModel(text=text, tokeni_intrare=i, tokeni_iesire=o)


class Furnizor:
    """Un furnizor fals care dă pe rând răspunsurile primite și își amintește conversațiile."""

    def __init__(self, *texte: str) -> None:
        self.texte = list(texte)
        self.conversatii: list[tuple[Mesaj, ...]] = []

    def __call__(self, mesaje: tuple[Mesaj, ...]) -> RaspunsModel:
        self.conversatii.append(mesaje)
        return raspuns(self.texte.pop(0))


def test_schema_are_campurile_obligatorii_ale_oricarei_iesiri() -> None:
    sj = schema_json(Clasificare)
    assert {"dovezi", "incredere", "eticheta"} <= set(sj["properties"])
    assert sj["additionalProperties"] is False
    assert "eticheta" in sj["required"] and "incredere" in sj["required"]


@pytest.mark.parametrize(
    "text",
    [VALID, f"```json\n{VALID}\n```", f"Iată rezultatul:\n{VALID}\nSper că ajută.", f"  \n{VALID}  "],
)
def test_extragerea_json_din_formele_obisnuite(text: str) -> None:
    v = valideaza(text, Clasificare)
    assert v.valid and isinstance(v.obiect, Clasificare) and v.obiect.eticheta == "negativ"
    assert extrage_json(text).startswith("{")


def test_raspuns_invalid_spune_ce_camp_e_gresit_fara_a_repeta_valorile() -> None:
    v = valideaza('{"eticheta": "Ion Popescu 0722123456", "incredere": 7}', Clasificare)
    assert not v.valid
    assert "eticheta" in v.eroare and "incredere" in v.eroare
    assert "Ion Popescu" not in v.eroare and "0722123456" not in v.eroare
    assert "JSON invalid" in valideaza('{"eticheta": ', Clasificare).eroare


def test_raspuns_valid_din_prima_nu_cere_reparatie() -> None:
    f = Furnizor(VALID)
    r = ruleaza_structurat(f, MESAJE, Clasificare, nativ=True)
    assert not r.reparat and len(f.conversatii) == 1 and r.obiect.incredere == 0.8  # type: ignore[attr-defined]
    assert f.conversatii[0] == MESAJE  # cu schemă nativă, mesajele nu se ating


def test_fara_schema_nativa_schema_intra_in_instructiuni() -> None:
    f = Furnizor(VALID)
    ruleaza_structurat(f, MESAJE, Clasificare, nativ=False)
    sistem = f.conversatii[0][0]
    assert sistem.rol == "system" and sistem.continut.startswith("Clasifică.")
    assert "JSON" in sistem.continut and '"eticheta"' in sistem.continut


def test_o_singura_reparatie_cu_eroarea_exacta_si_raspunsul_gresit() -> None:
    f = Furnizor('{"eticheta": "bun", "incredere": 0.5}', VALID)
    r = ruleaza_structurat(f, MESAJE, Clasificare, nativ=True)
    assert r.reparat and len(f.conversatii) == 2
    reparatie = f.conversatii[1]
    assert reparatie[: len(MESAJE)] == MESAJE
    assert reparatie[-2].rol == "assistant" and "bun" in reparatie[-2].continut
    assert (
        reparatie[-1].rol == "user"
        and "eticheta" in reparatie[-1].continut
        and "schema" in reparatie[-1].continut
    )
    assert r.eroare_initiala and "eticheta" in r.eroare_initiala
    assert (r.tokeni_intrare, r.tokeni_iesire) == (20, 10)  # ambele apeluri se contorizează


def test_dupa_reparatie_esuata_eroare_tipizata_fara_a_treia_cerere() -> None:
    f = Furnizor("nu e json", '{"eticheta": 5}', VALID)
    with pytest.raises(IesireNevalida) as exc:
        ruleaza_structurat(f, MESAJE, Clasificare, nativ=True)
    assert len(f.conversatii) == 2 and len(f.texte) == 1  # al treilea răspuns nu a fost cerut
    assert "eticheta" in exc.value.eroare and len(exc.value.raspunsuri) == 2
