"""Atac F15.2 (MEDIU în revizie): ce vede procesul web expus pe internet. Web-ul nu are credențialele
proprietarului schemei (ocolesc RLS), nu publică porturi, iar antetele X-Forwarded-* se cred doar de la
proxy (altfel limitarea pe IP și auditul se pot falsifica)."""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")
ROOT = Path(__file__).resolve().parents[2]
WEB = ("app_blue", "app_green")


def _compose(nume: str) -> dict[str, dict[str, object]]:
    return dict(yaml.safe_load((ROOT / "infra" / "compose" / nume).read_text())["services"])


def test_webul_nu_are_credentialele_proprietarului_si_nu_publica_porturi() -> None:
    for strat in ("base.yml", "production.yml", "staging.yml"):
        for nume, s in _compose(strat).items():
            if nume in WEB:
                env = dict((s or {}).get("environment") or {})  # type: ignore[call-overload]
                assert "AMA_DATABASE_OWNER_URL" not in env, (strat, nume)
                assert "ama_owner" not in str(env.get("AMA_DATABASE_URL", "")), (strat, nume)
            assert "ports" not in (s or {}) or nume == "proxy", (strat, nume)
    assert "AMA_DATABASE_OWNER_URL" in _compose("base.yml")["worker"]["environment"]  # type: ignore[operator]


def test_antetele_proxy_se_cred_doar_de_la_reteaua_proxyului() -> None:
    docker = (ROOT / "Dockerfile").read_text()
    assert "--forwarded-allow-ips=*" not in docker and "FORWARDED_ALLOW_IPS=127.0.0.1" in docker
    baza = (ROOT / "infra" / "compose" / "base.yml").read_text()
    edge = yaml.safe_load((ROOT / "infra" / "compose" / "edge.yml").read_text())
    subretea = edge["networks"]["edge"]["ipam"]["config"][0]["subnet"]
    assert f"FORWARDED_ALLOW_IPS: {subretea}" in baza
    assert "trusted_proxies" not in (ROOT / "infra" / "proxy" / "Caddyfile").read_text(), (
        "Caddy suprascrie X-Forwarded-For doar fără proxy-uri de încredere în fața lui"
    )
