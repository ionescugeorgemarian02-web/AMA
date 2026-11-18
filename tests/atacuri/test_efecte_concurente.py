"""Atac F15.2 (MEDIU în revizie): două joburi pe același efect de sistem (email, plată, reclamă) nu trimit de
două ori, chiar dacă rulează simultan și conectorul e lent."""

import threading
import time
from collections.abc import Iterator

import pytest

from app.connectors import registru
from app.connectors.contract import EfectSistem, RezultatPlatforma
from app.db import sesiune_agentie
from app.operare import motor
from app.operare.efecte import sistem
from tests.conftest import BazaTest

pytestmark = pytest.mark.db


class EmailLent:
    def __init__(self) -> None:
        self.trimise: list[str] = []

    def trimite(self, e: EfectSistem) -> RezultatPlatforma:
        time.sleep(0.5)  # cât lucrează conectorul, a doua încercare încearcă și ea
        self.trimise.append(e.idem)
        return RezultatPlatforma(id_extern=f"m-{len(self.trimise)}")


@pytest.fixture
def lent() -> Iterator[EmailLent]:
    c = EmailLent()
    registru.inregistreaza_sistem("email", c)  # type: ignore[arg-type]
    yield c
    registru.uita_sistem()


def test_doua_incercari_simultane_pe_acelasi_efect_de_sistem_trimit_o_data(
    baza: BazaTest, lent: EmailLent
) -> None:
    with sesiune_agentie() as db:
        e = sistem.cere(
            db, "email", cheie="atac:email-dublu", payload={"catre": "a@exemplu.ro", "subiect": "s", "text": "t"},
            porneste=False,
        )  # fmt: skip
        eid = e.id
    rezultate: list[str] = []

    def incearca() -> None:
        try:
            rezultate.append(sistem.incearca(eid))
        except motor.EroareTemporara:
            rezultate.append("reincercare")

    fire = [threading.Thread(target=incearca) for _ in range(2)]
    for f in fire:
        f.start()
    for f in fire:
        f.join()
    assert sorted(rezultate) == ["reincercare", "trimis"], rezultate
    assert len(lent.trimise) == 1, lent.trimise
    assert sistem.incearca(eid) == "trimis" and len(lent.trimise) == 1, "reîncercarea vede efectul trimis"
