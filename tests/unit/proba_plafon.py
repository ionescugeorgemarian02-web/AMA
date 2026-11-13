"""Fișier-sondă pentru `test_plafon_de_timp.py` (nu se colectează singur: numele nu începe cu `test_`)."""

import time


def test_blocat() -> None:
    time.sleep(30)  # depășește plafonul de 1 s impus de testul care îl rulează


def test_rapid() -> None:
    assert True
