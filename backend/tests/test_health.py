from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/api/health")
    assert response.status_code == 200


def test_health_status_is_ok():
    response = client.get("/api/health")
    data = response.json()
    assert data["status"] == "ok"


def test_health_service_field_exists():
    response = client.get("/api/health")
    data = response.json()
    assert "service" in data
    assert data["service"] == "sql-lineage-workbench-backend"


def test_health_version_field_exists():
    response = client.get("/api/health")
    data = response.json()
    assert "version" in data
    assert data["version"] == "0.3.0-c06"
