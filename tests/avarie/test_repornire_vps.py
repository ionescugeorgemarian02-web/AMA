"""F15.1, docs/25 §25.3: VPS-ul repornește complet -> toate serviciile revin singure și cozile reiau.

Aici: fiecare serviciu permanent din fișierele compose are politica de repornire (Docker îl readuce la
pornirea mașinii), iar cele de o singură dată (`migrate`) rulează și ies. Reluarea cozilor după o cădere
completă o dovedesc testele din `tests/chaos` (catalogul A13). # NEVERIFICAT: repornirea reală a VPS-ului
(Docker activat la pornire, `systemctl is-enabled docker`) se face pe staging, cu `scripts/avarie.sh`.
"""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")  # vine cu uv.lock (dependență a uneltelor), doar pentru citirea compose

COMPOSE = Path(__file__).resolve().parents[2] / "infra" / "compose"
O_SINGURA_DATA = {"migrate"}


def _servicii(nume: str) -> dict[str, dict[str, object]]:
    return dict(yaml.safe_load((COMPOSE / nume).read_text())["services"])


def test_toate_serviciile_au_politica_de_repornire() -> None:
    baza = _servicii("base.yml")
    for strat in ("production.yml", "staging.yml"):
        servicii = {**{k: dict(v or {}) for k, v in baza.items()}}
        for k, v in _servicii(strat).items():
            servicii[k] = {**servicii.get(k, {}), **(v or {})}
        for k, v in servicii.items():
            if k in O_SINGURA_DATA:
                assert v.get("restart") == "no", (strat, k)
            else:
                assert v.get("restart") in ("unless-stopped", "always"), (strat, k, v.get("restart"))
    for k, v in _servicii("edge.yml").items():
        assert (v or {}).get("restart") in ("unless-stopped", "always"), ("edge", k)
    assert {"postgres", "worker", "app_blue", "app_green"} <= set(baza)
