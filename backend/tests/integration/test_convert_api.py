from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_convert_sql_returns_converted_payload():
    response = client.post(
        "/api/sql/convert",
        json={
            "sql": "select `user_id` from t",
            "source_dialect": "hive",
            "target_dialect": "spark",
            "pretty": True,
        },
    )
    data = response.json()

    assert data["status"] == "success"
    assert data["source_dialect"] == "hive"
    assert data["target_dialect"] == "spark"
    assert data["converted_sql"]
    assert isinstance(data["elapsed_ms"], int)
    assert data["diagnostics"] == []


def test_convert_sql_accepts_sr_alias():
    response = client.post(
        "/api/sql/convert",
        json={
            "sql": "select 1",
            "source_dialect": "sr",
            "target_dialect": "hive",
            "pretty": True,
        },
    )
    data = response.json()

    assert data["status"] == "success"
    assert data["source_dialect"] == "starrocks"
    assert data["target_dialect"] == "hive"
