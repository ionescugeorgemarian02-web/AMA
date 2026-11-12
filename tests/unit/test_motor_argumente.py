"""F2.1 — fluxurile primesc doar identificatori: conținutul și secretele nu ajung în tabelele bibliotecii."""

import datetime as dt
import uuid
from enum import StrEnum

import pytest

from app.operare.motor import ArgumentNepermis, verifica_argumente


class Canal(StrEnum):
    FACEBOOK = "facebook"


def test_identificatorii_si_valorile_simple_trec() -> None:
    verifica_argumente(
        "f",
        (
            uuid.uuid4(),
            str(uuid.uuid4()),
            3,
            1.5,
            True,
            None,
            dt.datetime.now(dt.UTC),
            dt.date.today(),
            Canal.FACEBOOK,
        ),
        {"livrabil_id": "liv_123", "versiune": 3},
    )


def test_liste_si_dictionare_plate_de_scalari_trec() -> None:
    verifica_argumente(
        "f", ([uuid.uuid4(), uuid.uuid4()], ("a", "b")), {"context": {"tenant_id": "x", "n": 1}}
    )


@pytest.mark.parametrize(
    "valoare",
    [
        "x" * 201,  # un articol întreg în loc de identificator
        b"octeti",
        {"a": {"imbricat": 1}},
        [[1, 2]],
        [{"a": 1}],
        object(),
        {1: "cheie-nu-e-text"},
        list(range(65)),
    ],
)
def test_continutul_si_structurile_adanci_sunt_refuzate(valoare: object) -> None:
    with pytest.raises(ArgumentNepermis):
        verifica_argumente("f", (valoare,), {})
    with pytest.raises(ArgumentNepermis):
        verifica_argumente("f", (), {"x": valoare})


def test_mesajul_spune_ce_sa_faci() -> None:
    with pytest.raises(ArgumentNepermis, match="identificatorul"):
        verifica_argumente("flux.exemplu", ("t" * 500,), {})
