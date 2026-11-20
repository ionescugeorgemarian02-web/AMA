"""Selecția materialului pe scene (F-editorial): pură, deterministă, sigla nu intră niciodată în scene."""

import uuid

from app.media import selectie
from app.media.selectie import Candidat, CerereScena

SIGLA = Candidat(uuid.UUID(int=1), "logo", "foto", "sigla Atelierul Spița", "logo propus pentru Atelierul Spița")
TRANSMISIE = Candidat(uuid.UUID(int=2), "fotografie", "foto", "transmisie: lanț pe pinion", "foto din atelier")
SCENE = [
    CerereScena("Frânele scârțâie?", "", obligatorie=False),
    CerereScena("Reglăm frânele.", "mecanic care reglează etrierul frânei pe roata din față"),
    CerereScena("Curățăm transmisia.", "lanțul uns pe pinionul transmisiei"),
    CerereScena("Primești devizul.", "deviz scris pe tejghea"),
    CerereScena("Programează revizia.", "", obligatorie=False),
]


def test_doar_sigla_inseamna_toate_scenele_lipsa() -> None:
    alegeri = selectie.alege(SCENE, [SIGLA])
    assert len(alegeri) == len(SCENE)
    assert all(a.lipsa for a in alegeri)
    assert alegeri[2].subiect == "lanțul uns pe pinionul transmisiei"
    assert "niciun material" in alegeri[1].motiv


def test_sigla_si_transmisia_scena_despre_transmisie_alege_fotografia() -> None:
    alegeri = selectie.alege(SCENE, [SIGLA, TRANSMISIE])
    assert alegeri[2].activ_id == TRANSMISIE.id and alegeri[2].scor > 0
    assert "transmisiei" in alegeri[2].motiv or "pinionul" in alegeri[2].motiv
    assert alegeri[1].lipsa and alegeri[3].lipsa
    assert all(a.activ_id != SIGLA.id for a in alegeri)
    # hook-ul și apelul nu au indicație proprie: refolosesc primul cadru ales, cu motivul scris
    assert alegeri[0].activ_id == TRANSMISIE.id and "refolosește" in alegeri[0].motiv
    assert selectie.alege(SCENE, [TRANSMISIE, SIGLA]) == alegeri  # determinist, indiferent de ordine


def test_coperta_exportul_si_licenta_invalida_sunt_excluse() -> None:
    cop = Candidat(uuid.UUID(int=3), "coperta", "foto", "transmisie", "")
    exp = Candidat(uuid.UUID(int=4), "export", "video", "transmisie", "")
    fara = Candidat(uuid.UUID(int=5), "fotografie", "foto", "transmisie", "", licenta_ok=False)
    incert = Candidat(uuid.UUID(int=6), None, "foto", "transmisie", "")
    assert all(a.lipsa for a in selectie.alege(SCENE[2:3], [cop, exp, fara, incert]))


def test_potrivirea_pe_prefix_fara_diacritice_si_fara_umplutura() -> None:
    assert selectie.cuvinte("Cadru cu frânele, pentru transmisia") == ["franele", "transmisia"]
    assert selectie.se_potrivesc("transmisia", "transmisie")
    assert selectie.se_potrivesc("franei", "frane")
    assert not selectie.se_potrivesc("frana", "fraza")
    assert not selectie.se_potrivesc("transmisie", "transport")
    scor, gasite = selectie.potrivire("lanț pe pinion", "transmisie: lanțul pe pinionul din spate")
    assert scor == 1.0 and gasite == ["lant", "pinion"]


def test_la_egalitate_prefera_activul_nefolosit() -> None:
    a = Candidat(uuid.UUID(int=7), "fotografie", "foto", "roata bicicletei", "")
    b = Candidat(uuid.UUID(int=8), "fotografie", "foto", "roata bicicletei", "")
    alegeri = selectie.alege([CerereScena("x", "roata bicicletei"), CerereScena("y", "roata bicicletei")], [a, b])
    assert {x.activ_id for x in alegeri} == {a.id, b.id}
