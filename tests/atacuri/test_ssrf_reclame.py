"""Atac F15.2: linkul unei reclame (dat de client) nu poate face platforma să citească adrese interne."""

import httpx
import pytest

from app.reclame import pagina

INTERNE = [
    "http://169.254.169.254/latest/meta-data/",
    "http://127.0.0.1:8000/healthz",
    "http://localhost/",
    "http://10.0.0.5/",
    "http://[::1]/",
    "http://postgres.internal/",
    "file:///etc/passwd",
    "http://user:pass@exemplu.ro/",  # pragma: allowlist secret
    "http://exemplu.ro:5432/",
]


@pytest.mark.parametrize("url", INTERNE)
def test_adresele_interne_nu_se_cer_deloc(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    cerute: list[str] = []
    monkeypatch.setattr(httpx, "get", lambda u, **kw: cerute.append(u))
    assert pagina.get_sigur(url) is None and cerute == []


def test_redirectionarea_spre_metadate_e_oprita_la_pasul_urmator(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.cercetare import ssrf

    monkeypatch.setattr(ssrf, "rezolva_sistem", lambda gazda, port: ["93.184.216.34"])
    cerute: list[str] = []

    def get(u: str, **kw: object) -> httpx.Response:
        cerute.append(u)
        return httpx.Response(
            302, headers={"location": "http://169.254.169.254/"}, request=httpx.Request("GET", u)
        )

    monkeypatch.setattr(httpx, "get", get)
    assert pagina.get_sigur("https://pagina-clientului.ro/oferta") is None
    assert cerute == ["https://pagina-clientului.ro/oferta"], "a doua cerere (spre metadate) nu pleacă"
