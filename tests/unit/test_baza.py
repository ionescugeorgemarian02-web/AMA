"""F1.1 — aplicația pornește, răspunde la verificarea de sănătate, scrie jurnale structurate."""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.ids import new_id
from app.logging import JsonFormatter, correlation_id
from app.main import create_app
from app.operare import health


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_healthz_raspunde(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.headers["x-request-id"]


def test_request_id_primit_este_pastrat(client: TestClient) -> None:
    r = client.get("/healthz", headers={"x-request-id": "abc-12345678"})
    assert r.headers["x-request-id"] == "abc-12345678"


def test_request_id_invalid_este_inlocuit(client: TestClient) -> None:
    r = client.get("/healthz", headers={"x-request-id": "x"})
    assert r.headers["x-request-id"] != "x"


def test_readyz_semnaleaza_dependenta_cazuta(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def cazut() -> None:
        raise ConnectionError("nu răspunde")

    monkeypatch.setattr(health, "_checks", {"proba": cazut})
    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["checks"]["proba"].startswith("eroare")


def test_fara_documentatie_api_in_productie(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config

    monkeypatch.setattr(
        config, "get_settings", lambda: Settings(env="prod", secret_key="s" * 32, master_key="m" * 32)
    )
    monkeypatch.setattr("app.main.get_settings", config.get_settings)
    c = TestClient(create_app())
    assert c.get("/docs").status_code == 404
    assert c.get("/openapi.json").status_code == 404


def test_productia_refuza_pornirea_fara_secrete() -> None:
    with pytest.raises(RuntimeError, match="Secrete"):
        Settings(env="prod").require_secrets()


def test_configurare_din_mediu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMA_LOG_LEVEL", "DEBUG")
    assert Settings().log_level == "DEBUG"


def test_jurnal_json_cu_corelare() -> None:
    token = correlation_id.set("cid-1")
    try:
        record = logging.LogRecord("t", logging.INFO, __file__, 1, "salut %s", ("lume",), None)
        record.client = "x"
        out = json.loads(JsonFormatter().format(record))
    finally:
        correlation_id.reset(token)
    assert out["msg"] == "salut lume"
    assert out["correlation_id"] == "cid-1"
    assert out["client"] == "x"
    assert out["level"] == "INFO"


def test_id_uri_ordonate_in_timp() -> None:
    import time

    a = new_id()
    time.sleep(0.002)
    b = new_id()
    assert a.version == 7 and b.version == 7
    assert a < b
    assert len({new_id() for _ in range(1000)}) == 1000
