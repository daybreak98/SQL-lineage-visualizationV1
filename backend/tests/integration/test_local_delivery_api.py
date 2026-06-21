from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_untrusted_host_is_rejected():
    response = client.get("/api/health", headers={"host": "evil.example"})

    assert response.status_code == 400


def test_remote_origin_is_not_granted_cors_access():
    response = client.get(
        "/api/health",
        headers={"origin": "https://evil.example"},
    )

    assert "access-control-allow-origin" not in response.headers


def test_local_origin_is_granted_cors_access_without_credentials():
    response = client.get(
        "/api/health",
        headers={"origin": "http://127.0.0.1:5173"},
    )

    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "access-control-allow-credentials" not in response.headers
