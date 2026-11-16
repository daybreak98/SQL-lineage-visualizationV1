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


def test_subfield_rejects_conflicting_complete_schema_aliases():
    lower, upper = "demo.events", "DEMO.EVENTS"
    schemas = {
        lower: {"columns": ["payload"], "complete": True, "version": "v1", "evidence": "synthetic A"},
        upper: {"columns": ["other"], "complete": True, "version": "v2", "evidence": "synthetic B"},
    }
    with TestClient(app) as client:
        for dialect in ("hive", "spark"):
            for relation, order in ((lower, (lower, upper)), (upper, (upper, lower))):
                response = client.post("/api/sql/subfield-lineage", json={
                    "dialect": dialect,
                    "sql": f"SELECT get_json_object(payload, '$.k') AS k FROM {relation}",
                    "source_schemas": {key: schemas[key] for key in order},
                })
                assert response.status_code == 422
                assert response.json()["detail"] == {
                    "code": "CONFLICTING_SOURCE_SCHEMAS", "relations": [upper, lower],
                }


def test_subfield_keeps_exact_binding_for_a_single_complete_schema():
    relation = "demo.events"
    schema = {"columns": ["payload"], "complete": True, "version": "v1", "evidence": "synthetic A"}
    with TestClient(app) as client:
        response = client.post("/api/sql/subfield-lineage", json={
            "dialect": "spark",
            "sql": "SELECT get_json_object(payload, '$.k') AS k FROM `demo`.`events`",
            "source_schemas": {relation: schema},
        })
    assert response.status_code == 200
    result = response.json()
    assert result["coverage"]["source_schema_binding"]["applied"][relation]["version"] == "v1"
    assert [(use["source"], use["column"], use["path"]) for use in result["uses"]] == [
        ("demo.events", "payload", "$.k")
    ]
    assert result["unknowns"] == []
