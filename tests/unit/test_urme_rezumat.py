"""FT.1 — rezumatul unei urme: fără secrete, fără date personale în clar, mărginit."""

import uuid
from decimal import Decimal

from app.operare.urme import mascheaza, rezuma


def test_cheile_secrete_sunt_ascunse_la_orice_adancime() -> None:
    r = rezuma({"parola": "x", "date": {"access_token": "abc", "Authorization": "Bearer z"}, "ok": 1})
    assert r == {
        "parola": "[ascuns]",
        "date": {"access_token": "[ascuns]", "Authorization": "[ascuns]"},
        "ok": 1,
    }


def test_datele_personale_sunt_mascate_in_texte() -> None:
    t = mascheaza(
        "Scrie-i Ioanei la ioana.pop@exemplu.ro sau 0722 123 456; CNP 1960101123456, RO49AAAA1B31007593840000"
    )
    assert "@" not in t and "0722" not in t and "1960101123456" not in t and "RO49" not in t
    assert {"[email]", "[telefon]", "[cnp]", "[iban]"} <= set(t.replace(",", " ").replace(";", " ").split())
    assert mascheaza("antet Bearer abc.def") == "antet [ascuns]"


def test_marginile_si_tipurile() -> None:
    r = rezuma({"lista": list(range(30)), "text": "a" * 500, "id": uuid.UUID(int=1), "bani": Decimal("1.5")})
    assert len(r["lista"]) == 21 and r["lista"][-1] == "… încă 10"
    assert len(r["text"]) == 200 and r["text"].endswith("…")
    assert r["id"] == str(uuid.UUID(int=1)) and r["bani"] == 1.5
    adanc = rezuma({"a": {"b": {"c": {"d": {"e": 1}}}}})
    assert adanc == {"a": {"b": {"c": {"d": "[…]"}}}}
