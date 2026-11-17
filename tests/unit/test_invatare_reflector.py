"""F11.1 — regulile Reflectorului (nuclee pure): ce iese din rezultate, din verdicte și din decizii."""

from app.invatare import reflector as r
from app.invatare.reflector import Postare


def postari(tipar: str, n: int, recompensa: float, slot: str = "luni, ora 09") -> list[Postare]:
    return [Postare(f"{tipar}-{i}", "facebook", tipar, slot, recompensa) for i in range(n)]


def test_tiparul_peste_si_sub_medie_devine_propunere_cu_dovezi() -> None:
    lot = [*postari("intrebare", 4, 0.08), *postari("cifra", 4, 0.02), *postari("poveste", 2, 0.05)]
    p = {x.cheie: x for x in r.din_rezultate(lot) if ":tipar_hook:" in x.cheie}
    assert set(p) == {"rezultate:tipar_hook:intrebare:mai_des", "rezultate:tipar_hook:cifra:mai_rar"}, (
        "grupul cu două postări nu intră, oricât de bun"
    )
    bun = p["rezultate:tipar_hook:intrebare:mai_des"]
    assert bun.text.startswith(
        "Folosește mai des hook-urile de tip „întrebare”: 8,0 interacțiuni la 100 de afișări"
    )
    assert "din 4 postări" in bun.text and len(bun.dovezi) == 4 and bun.dovezi[0]["la_suta"] == 8.0
    assert not bun.sensibila and bun.sursa == "rezultate"


def test_fara_diferenta_destula_nu_se_propune_nimic() -> None:
    lot = [*postari("intrebare", 5, 0.050), *postari("cifra", 5, 0.055)]
    assert [x for x in r.din_rezultate(lot) if ":tipar_hook:" in x.cheie] == []
    assert r.din_rezultate([]) == []


def test_regula_care_opreste_repetat_devine_lectie_pentru_autor() -> None:
    esecuri = [(f"l{i}", "G3", "G3.fraza_prea_lunga") for i in range(3)]
    esecuri += [
        ("l0", "G3", "G3.fraza_prea_lunga")
    ]  # același livrabil, a doua rundă: nu se numără de două ori
    esecuri += [(f"l{i}", "G2", "G2.pret_fara_fapt") for i in range(3)] + [
        ("l9", "G7", "G7.copiat_din_sursa")
    ]
    p = {x.cheie: x for x in r.din_verdicte(esecuri)}
    assert set(p) == {"verdicte:G3.fraza_prea_lunga", "verdicte:G2.pret_fara_fapt"}
    assert "a oprit 3 livrabile" in p["verdicte:G3.fraza_prea_lunga"].text
    assert p["verdicte:G2.pret_fara_fapt"].sensibila and not p["verdicte:G3.fraza_prea_lunga"].sensibila
    assert p["verdicte:G3.fraza_prea_lunga"].domeniu_tip == "agent"


def test_motivele_de_respingere_repetate_devin_lectii() -> None:
    resp = [(f"l{i}", "hook_slab") for i in range(3)] + [(f"m{i}", "conformitate") for i in range(4)]
    resp += [("x", "prea_lung"), ("y", "altceva"), ("z", "altceva"), ("w", "altceva")]
    p = {x.cheie: x for x in r.din_decizii(resp)}
    assert set(p) == {"decizii:hook_slab", "decizii:conformitate"}, "„altceva” nu spune nimic"
    assert "de 3 ori pentru „Hook slab”" in p["decizii:hook_slab"].text
    assert p["decizii:conformitate"].sensibila and len(p["decizii:conformitate"].dovezi) == 4
