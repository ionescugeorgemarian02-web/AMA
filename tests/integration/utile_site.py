"""Ajutoare pentru testele F7: cutia poștală simulată și așteptarea efectelor de sistem."""

import re
import time
from collections.abc import Callable, Iterator

import pytest

from app.connectors import email, registru


@pytest.fixture
def cutie() -> Iterator[email.CutiePostalaSimulata]:
    c = email.CutiePostalaSimulata()
    registru.inregistreaza_sistem(email.TIP, c)
    yield c
    registru.uita_sistem()


def asteapta[T](f: Callable[[], T | None], *, secunde: float = 20.0) -> T:
    sfarsit = time.monotonic() + secunde
    while time.monotonic() < sfarsit:
        r = f()
        if r:
            return r
        time.sleep(0.1)
    raise AssertionError("condiția nu s-a îndeplinit la timp")


def link_din(text: str, cale: str) -> str:
    m = re.search(r"https?://\S+" + re.escape(cale) + r"\S+", text)
    assert m, f"mesajul nu conține un link {cale}"
    return m.group(0)
