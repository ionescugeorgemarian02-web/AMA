"""F1.5 — primitivele: parole (argon2id), criptare în repaus, TOTP și coduri de recuperare."""

import pytest

from app.config import get_settings
from app.conturi import criptare, parole, totp

pytestmark = pytest.mark.usefixtures("chei_de_test")


def test_parola_hash_argon2id_si_verificare() -> None:
    h = parole.hash_parola("o-parola-lunga-si-buna")
    assert h.startswith("$argon2id$")
    assert parole.verifica(h, "o-parola-lunga-si-buna")
    assert not parole.verifica(h, "alta-parola-lunga-aici")
    assert not parole.verifica(
        None, "orice-parola-lunga"
    )  # utilizator necunoscut: fals, dar cu aceeași muncă
    assert not parole.verifica("nu-este-un-hash", "x")


@pytest.mark.parametrize(
    ("parola", "email", "cuvant"),
    [
        ("scurta", "", "cel puțin 12"),
        ("a" * 129, "", "cel mult"),
        ("ana@exemplu.test", "ANA@exemplu.test", "email"),
    ],
)
def test_politica_de_parole(parola: str, email: str, cuvant: str) -> None:
    with pytest.raises(parole.ParolaInvalida, match=cuvant):
        parole.valideaza(parola, email)


def test_parola_de_12_caractere_este_acceptata() -> None:
    parole.valideaza("a" * 12)


def test_criptare_dus_intors_si_legata_de_rand() -> None:
    blob = criptare.cripteaza(b"JBSWY3DPEHPK3PXP", aad=b"utilizator-1")
    assert b"JBSWY3DPEHPK3PXP" not in blob
    assert criptare.decripteaza(blob, aad=b"utilizator-1") == b"JBSWY3DPEHPK3PXP"
    with pytest.raises(Exception, match=r".*"):  # InvalidTag: alt rând, același text criptat
        criptare.decripteaza(blob, aad=b"utilizator-2")
    assert criptare.cripteaza(b"x", aad=b"a") != criptare.cripteaza(b"x", aad=b"a")  # nonce aleator


def test_criptare_refuza_continut_alterat() -> None:
    blob = bytearray(criptare.cripteaza(b"secret", aad=b"a"))
    blob[-1] ^= 1
    with pytest.raises(Exception, match=r".*"):
        criptare.decripteaza(bytes(blob), aad=b"a")


def test_fara_cheie_principala_nu_se_cripteaza(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMA_MASTER_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(criptare.CheieLipsa):
            criptare.cripteaza(b"x", aad=b"a")
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_hmac_depinde_de_scop_si_valoare() -> None:
    assert criptare.hmac_valoare("a", "x") == criptare.hmac_valoare("a", "x")
    assert criptare.hmac_valoare("a", "x") != criptare.hmac_valoare("b", "x")
    assert criptare.hmac_valoare("a", "x") != criptare.hmac_valoare("a", "y")


def test_jetoane_de_256_de_biti() -> None:
    a, b = criptare.jeton_nou(), criptare.jeton_nou()
    assert a != b and len(a) >= 43
    assert len(criptare.hash_jeton(a)) == 32


def test_totp_accepta_fereastra_si_refuza_reluarea() -> None:
    secret = totp.secret_nou()
    t = 1_800_000_000.0
    cod = totp.cod_pentru(secret, t)
    pas = totp.pas_valid(secret, cod, ultim_pas=None, acum=t)
    assert pas == totp.pas_curent(t)
    assert totp.pas_valid(secret, cod, ultim_pas=pas, acum=t) is None  # același pas: reluare
    assert totp.pas_valid(secret, cod, ultim_pas=pas, acum=t + 10) is None
    assert totp.pas_valid(secret, totp.cod_pentru(secret, t + 30), ultim_pas=pas, acum=t + 30) == pas + 1
    # decalaj de ceas de un pas este tolerat; doi pași nu
    assert totp.pas_valid(secret, cod, ultim_pas=None, acum=t + 30) == pas
    assert totp.pas_valid(secret, cod, ultim_pas=None, acum=t + 90) is None


@pytest.mark.parametrize("cod", ["", "12345", "1234567", "abcdef", "12 34 5", "１２３４５６"])
def test_totp_refuza_formate_invalide(cod: str) -> None:
    assert totp.pas_valid(totp.secret_nou(), cod, ultim_pas=None) is None


def test_uri_otpauth() -> None:
    uri = totp.uri_provizionare("JBSWY3DPEHPK3PXP", "ana@exemplu.test")
    assert uri.startswith("otpauth://totp/AMA:ana%40exemplu.test?secret=JBSWY3DPEHPK3PXP")


def test_coduri_de_recuperare() -> None:
    coduri = totp.coduri_recuperare_noi()
    assert len(coduri) == len(set(coduri)) == 10
    assert all(len(c) == 19 and c.count("-") == 3 for c in coduri)
    assert totp.normalizeaza_cod_recuperare("ab12-cd34") == "AB12CD34"
