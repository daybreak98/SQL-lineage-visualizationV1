from fastapi.testclient import TestClient

from app.main import app


def test_subfield_route_preserves_distinct_paths_and_roles():
    with TestClient(app) as client:
        response = client.post("/api/sql/subfield-lineage", json={
            "dialect": "spark",
            "sql": (
                "SELECT get_json_object(payload, '$.PhotoId') AS id "
                "FROM events WHERE get_json_object(payload, '$.photoid') = 'x'"
            ),
        })
    assert response.status_code == 200
    result = response.json()
    assert isinstance(result["coverage"], (dict, str))
    rendered = str(result["uses"])
    assert "PhotoId" in rendered and "photoid" in rendered
    assert "events" in rendered
