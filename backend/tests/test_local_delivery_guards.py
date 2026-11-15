from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.local_delivery import (
    LocalDeliveryGuardMiddleware,
    MAX_REQUEST_BODY_BYTES,
    MAX_SQL_CHARS,
    is_loopback_client,
)
from app.models import AnalyzeRequest, ConvertSqlRequest, FormatSqlRequest


def test_loopback_client_detection_rejects_remote_addresses():
    assert is_loopback_client("127.0.0.1")
    assert is_loopback_client("::1")
    assert is_loopback_client("testclient")
    assert not is_loopback_client("203.0.113.10")
    assert not is_loopback_client(None)


def test_sql_request_models_reject_oversized_sql():
    oversized_sql = "x" * (MAX_SQL_CHARS + 1)

    for model, payload in (
        (AnalyzeRequest, {"sql": oversized_sql}),
        (FormatSqlRequest, {"sql": oversized_sql}),
        (ConvertSqlRequest, {"sql": oversized_sql}),
    ):
        try:
            model(**payload)
        except ValueError:
            continue
        raise AssertionError(f"{model.__name__} accepted oversized SQL")


def test_request_body_limit_returns_413_before_endpoint_execution():
    app = FastAPI()
    app.add_middleware(LocalDeliveryGuardMiddleware)

    @app.post("/api/sql/analyze")
    def analyze():
        return {"ok": True}

    response = TestClient(app).post(
        "/api/sql/analyze",
        content=b"x" * (MAX_REQUEST_BODY_BYTES + 1),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Request body too large"


def test_busy_sql_endpoint_returns_429():
    app = FastAPI()
    app.add_middleware(
        LocalDeliveryGuardMiddleware,
        max_concurrent_sql_requests=0,
    )

    @app.post("/api/sql/analyze")
    def analyze():
        return {"ok": True}

    response = TestClient(app).post("/api/sql/analyze", json={"sql": "select 1"})

    assert response.status_code == 429
    assert response.json()["detail"] == "SQL service is busy"


def test_slow_sql_endpoint_returns_504():
    app = FastAPI()
    app.add_middleware(
        LocalDeliveryGuardMiddleware,
        sql_timeout_seconds=0.01,
    )

    @app.post("/api/sql/analyze")
    def analyze():
        time.sleep(0.05)
        return {"ok": True}

    response = TestClient(app).post("/api/sql/analyze", json={"sql": "select 1"})

    assert response.status_code == 504
    assert response.json()["detail"] == "SQL request timed out"
