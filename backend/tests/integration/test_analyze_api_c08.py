from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_analyze_c08_returns_source_locations_for_output_columns():
    sql = """select
  order_no,
  user_id as uid
from dwd_order_di"""
    response = client.post("/api/sql/analyze", json={"sql": sql})
    data = response.json()

    assert response.status_code == 200
    assert data["schema_version"] == "0.3.0-c09"
    assert data["analysis_id"] == "analysis:c09"

    locations = data["source_locations"]
    assert locations["output_column:order_no"]["line"] == 2
    assert locations["output_column:order_no"]["col"] == 3
    assert locations["output_column:order_no"]["raw"] == "order_no"
    assert locations["output_column:uid"]["line"] == 3
    assert locations["output_column:uid"]["raw"] == "user_id as uid"


def test_analyze_c08_include_source_location_false_keeps_locations_empty():
    response = client.post(
        "/api/sql/analyze",
        json={
            "sql": "select a as aa from t",
            "analysis_options": {
                "include_graph": True,
                "include_semantics": False,
                "include_diagnostics": True,
                "include_source_location": False,
                "include_expression_lineage": False,
            },
        },
    )
    data = response.json()

    assert data["status"] == "success"
    assert data["source_locations"] == {}


def test_analyze_c08_select_star_locations_are_approximate_when_metadata_expands_columns():
    metadata = {
        "metadata_version": "c08-star",
        "tables": [
            {
                "catalog": "default",
                "schema": "default",
                "table_name": "dwd_order_di",
                "columns": [
                    {"name": "order_no", "data_type": "string"},
                    {"name": "user_id", "data_type": "string"},
                ],
            }
        ],
    }
    client.post("/api/metadata/import/commit", json={"mode": "commit", "payload": metadata})

    response = client.post("/api/sql/analyze", json={"sql": "select * from dwd_order_di"})
    data = response.json()

    locations = data["source_locations"]
    assert locations["output_column:order_no"]["raw"] == "*"
    assert locations["output_column:user_id"]["rangeType"] == "approximate"
    assert any(
        diagnostic["code"] == "SOURCE_LOCATION_APPROXIMATE"
        for diagnostic in data["diagnostics_report"]["diagnostics"]
    )
