"""F3.5 — nucleele pure: viteza, mediana, sămânța locală, cererea adaptorului local."""

import pytest

from app.gateway import inventar, inventar_local
from app.gateway.adaptoare import adaptor_pentru
from app.gateway.masurare import mediana, viteza
from app.gateway.tipuri import CerereModel, Destinatie, Mesaj


def test_viteza_si_mediana() -> None:
    assert viteza(100, 4.0) == 25.0
    assert viteza(0, 4.0) is None and viteza(10, 0.0) is None
    assert mediana([30.0, 10.0, 20.0]) == 20.0 and mediana([10.0, 20.0]) == 15.0


def test_semanta_locala_este_coerenta_cu_inventarul() -> None:
    coduri = {f["cod"] for f in inventar_local.FURNIZORI}
    assert coduri == {"local", "vectori"}
    for f in inventar_local.FURNIZORI:
        assert f["tip_api"] in inventar.TIPURI_API and f["cheie_env"].startswith("AMA_CHEIE_")
        assert f["url_baza"].startswith("http://") and f["uz_comercial"] is None  # licența se confirmă
    locale = [m for m in inventar_local.MODELE if m[0] == "local"]
    assert len(locale) == 3  # două-trei mărimi (F3.5)
    assert all(set(m[4]) <= set(inventar.CAPABILITATI) and m[0] in coduri for m in inventar_local.MODELE)
    [vectori] = [m for m in inventar_local.MODELE if "embeddings" in m[4]]
    assert vectori[5] == 384


def test_cererea_locala_cere_gramatica_din_schema_si_nu_trimite_cheie() -> None:
    dest = Destinatie("local", "local", "http://local-llm:8080/v1", "m", {})
    schema = {"type": "object", "properties": {"eticheta": {"type": "string"}}}
    cerere = CerereModel(mesaje=(Mesaj("user", "x"),), schema_json=schema)
    http = adaptor_pentru("local").cerere(dest, None, cerere)
    assert (
        str(http.url) == "http://local-llm:8080/v1/chat/completions" and "authorization" not in http.headers
    )
    import json

    corp = json.loads(http.content)
    assert corp["response_format"]["json_schema"]["schema"] == schema and corp["cache_prompt"] is True


def test_raspunsul_de_vectori_cu_forma_gresita_este_eroare_de_server() -> None:
    import httpx

    from app.gateway.erori import EroareFurnizor

    a = adaptor_pentru("local")
    bun = httpx.Response(
        200, json={"data": [{"index": 1, "embedding": [1, 2]}, {"index": 0, "embedding": [3, 4]}]}
    )
    assert a.raspuns_vectori(bun, 2)[0] == [[3.0, 4.0], [1.0, 2.0]]  # în ordinea textelor
    for rau in (httpx.Response(200, json={"x": 1}), bun):
        with pytest.raises(EroareFurnizor):
            a.raspuns_vectori(rau, 3)
