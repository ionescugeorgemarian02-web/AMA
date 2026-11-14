"""F9.9 — conectorul „Site și blog” pe WordPress (CMS-ul clientului) trece suita de contract, pe REST API
simulat (# SIMULAT); OAuth și limitele nu există la WordPress (parolă de aplicație din panou, fără limită
declarată)."""

import re
from typing import Any

import pytest

from app.connectors.contract import Token
from app.connectors.publicare import DepozitInMemorie
from app.connectors.publicare.blog import ConectorBlog, html_articol
from app.ids import new_id
from app.operare.motor import EroareDefinitiva
from tests.contract.contract_publicare import ContractPublicare, Mediu
from tests.platforme.wordpress import SITE, WordpressSimulat

ARTICOL = {
    "text": "Cum alegi cafeaua de specialitate",
    "titlu": "Cum alegi cafeaua de specialitate",
    "descriere": "Ghid scurt.",
    "corp": [{"titlu": "Boabele", "paragrafe": ["Proaspăt prăjite [1]."]}],
    "surse": [{"titlu": "Ghid", "url": "https://example.org/ghid"}],
}


def cu_adresa(p: dict[str, Any]) -> dict[str, Any]:
    return {**p, "titlu": p["text"], "slug": re.sub(r"[^a-z0-9]+", "-", p["text"].lower()).strip("-")}


class TestConectorBlogWordpress(ContractPublicare):
    @pytest.fixture
    def mediu(self) -> Mediu:
        wp, d, tenant = WordpressSimulat(), DepozitInMemorie(), new_id()
        parola = wp.parola_noua()
        d.pune(tenant, "blog", Token(parola, None, "", SITE))
        return Mediu(
            ConectorBlog(depozit=d, transport=wp.transport),
            wp,
            tenant,
            dict(ARTICOL),
            token=parola,
            adrese=wp.adrese,
            completeaza=cu_adresa,
        )

    def test_autorizarea_oauth(self, mediu: Mediu) -> None:
        with pytest.raises(EroareDefinitiva, match="panou"):
            mediu.conector.url_autorizare("s", "https://ama.exemplu.test/r")

    def test_limitele_sunt_citite_de_la_platforma(self, mediu: Mediu) -> None:
        lim = mediu.conector.limite(mediu.tenant_id)
        assert lim.ramase is None and "fără limită" in lim.sursa


def test_html_articol_scapa_textul() -> None:
    h = html_articol(
        {
            "corp": [{"titlu": "<b>T</b>", "paragrafe": ["a & b"]}],
            "surse": [{"titlu": "S", "url": "https://x.test/?a=1&b=2"}],
        }
    )
    assert "<h2>&lt;b&gt;T&lt;/b&gt;</h2>" in h and "<p>a &amp; b</p>" in h and "a=1&amp;b=2" in h
