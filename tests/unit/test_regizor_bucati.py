"""O bătaie mai lungă decât clipul ales se împarte pe clipuri care o acoperă (găsit de testul live)."""

import uuid

from app.media.modele import Activ
from app.media.regizor import _bucati


def _v(categorie: str = "video") -> Activ:
    return Activ(id=uuid.uuid4(), categorie=categorie)


def test_bataia_lunga_se_imparte_egal_pe_clipurile_urmatoare() -> None:
    a, b, c = _v(), _v(), _v()
    durate = {a.id: 3.0, b.id: 1.0, c.id: 4.0}
    out = _bucati(a, 0.0, 7.0, [a, b, c], durate)
    assert [x[0] for x in out] == [a, c, a]  # b (1 s) nu acoperă o bucată de 2,33 s
    assert out[0][1] == 0.0 and out[-1][2] == 7.0
    assert all(abs((y - x) - 7 / 3) < 0.01 for _, x, y in out)


def test_scena_care_incape_sau_foto_ramane_intreaga() -> None:
    a, f = _v(), _v("foto")
    assert _bucati(a, 1.0, 3.0, [a], {a.id: 5.0}) == [(a, 1.0, 3.0)]
    assert _bucati(f, 0.0, 9.0, [f], {}) == [(f, 0.0, 9.0)]
