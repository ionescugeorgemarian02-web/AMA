"""F10.3 — nucleele pure ale legării de etichete: slotul local, recompensa (11.4), mediile pe grup."""

import datetime as dt

import pytest

from app.analiza import etichete
from app.analiza.modele import EtichetePostare
from app.continut.scriere import TIPARE


def test_slotul_este_in_ora_locala_cu_ora_de_vara() -> None:
    # 14 noiembrie 2026, 07:30 UTC = 09:30 la București (iarna, UTC+2), sâmbătă
    assert etichete.slot(dt.datetime(2026, 11, 14, 7, 30, tzinfo=dt.UTC)) == (6, 9)
    # 14 iulie 2026, 21:30 UTC = 00:30 a doua zi la București (vara, UTC+3): ziua se schimbă
    assert etichete.slot(dt.datetime(2026, 7, 14, 21, 30, tzinfo=dt.UTC)) == (3, 0)
    assert etichete.eticheta_slot(6, 9) == "sâmbătă, ora 09"


def test_recompensa_postarilor_este_interactiuni_pe_afisari() -> None:
    v = {"afisari": 1000, "aprecieri": 30, "comentarii": 5, "distribuiri": 3, "salvari": 2, "clicuri": 50}
    assert etichete.recompensa(v) == (0.04, "interactiuni_pe_afisari"), "clicurile nu sunt interacțiuni"
    # fără afișări: acoperirea, apoi vizualizările
    assert etichete.recompensa({"acoperire": 500, "aprecieri": 10}) == (0.02, "interactiuni_pe_afisari")
    assert etichete.recompensa({"vizualizari": 200, "aprecieri": 10, "comentarii": 0}) == (
        0.05,
        "interactiuni_pe_afisari",
    )


@pytest.mark.parametrize(
    "valori",
    [
        {},
        {"aprecieri": 10},
        {"afisari": 0, "aprecieri": 3},
        {"afisari": 500},
        {"afisari": "multe", "aprecieri": 1},
    ],
)
def test_fara_cifre_destule_nu_exista_recompensa(valori: dict[str, object]) -> None:
    assert etichete.recompensa(valori) is None


def test_clipul_cu_curba_are_recompensa_retentia_medie() -> None:
    assert etichete.recompensa({"vizualizari": 900, "aprecieri": 60}, 0.4321) == (0.4321, "retentie_medie")


def test_fiecare_tipar_de_hook_are_nume_pe_ecran() -> None:
    assert set(etichete.ETICHETE_HOOK) == set(TIPARE)


def postare(rec: float | None, tip: str | None = "interactiuni_pe_afisari") -> EtichetePostare:
    return EtichetePostare(recompensa=rec, recompensa_tip=tip if rec is not None else None)


def test_mediile_unui_grup_nu_amesteca_tipurile() -> None:
    g = etichete.Grup(
        "întrebare", [postare(0.02), postare(0.04), postare(None), postare(0.5, "retentie_medie")]
    )
    assert g.medii() == {"interactiuni_pe_afisari": (2, 0.03), "retentie_medie": (1, 0.5)}
    assert g.scor("interactiuni_pe_afisari") == 0.03
    assert etichete.Grup("gol", [postare(None)]).scor("interactiuni_pe_afisari") == -1.0


def test_formatul_video_vine_din_lista_de_montaj() -> None:
    assert etichete.format_video({"format": "A"}) == "video_a"
    assert etichete.format_video({"format": "E", "scene": []}) == "video_e"
    assert etichete.format_video({"format": "Z"}) == "video", "un format necunoscut nu devine etichetă"
    assert etichete.format_video(None) == "video" and etichete.format_video({}) == "video"
