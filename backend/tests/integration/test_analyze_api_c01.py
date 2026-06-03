from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_analyze_returns_200():
    response = client.post(
        "/api/sql/analyze",
        json={"sql": "select a from t"},
    )
    assert response.status_code == 200


def test_analyze_success_sql_returns_output_fields():
    response = client.post(
        "/api/sql/analyze",
        json={"sql": "select a from t"},
    )
    data = response.json()
    assert data["status"] == "success"
    assert len(data["output_fields"]) == 1
    assert data["output_fields"][0]["name"] == "a"


def test_analyze_aliased_field():
    response = client.post(
        "/api/sql/analyze",
        json={"sql": "select a as aa from t"},
    )
    data = response.json()
    assert data["status"] == "success"
    assert data["output_fields"][0]["name"] == "aa"
    assert data["output_fields"][0]["expression"] == "a"


def test_analyze_failed_sql_returns_failed_status():
    response = client.post(
        "/api/sql/analyze",
        json={"sql": "select from"},
    )
    data = response.json()
    assert data["status"] == "failed"


def test_analyze_failed_sql_has_parse_error_diagnostic():
    response = client.post(
        "/api/sql/analyze",
        json={"sql": "select from"},
    )
    data = response.json()
    diag_report = data["diagnostics_report"]
    assert diag_report["error_count"] >= 1
    assert any(
        d["code"] == "SQL_PARSE_ERROR" for d in diag_report["diagnostics"]
    )


def test_analyze_count_star():
    response = client.post(
        "/api/sql/analyze",
        json={"sql": "select count(*) as cnt from t"},
    )
    data = response.json()
    assert data["status"] == "partial"
    assert data["output_fields"][0]["name"] == "cnt"
    assert data["output_fields"][0]["expression"] == "COUNT(*)"
    assert any(
        diagnostic["code"] == "UNSUPPORTED_COMPLEX_QUERY"
        for diagnostic in data["diagnostics_report"]["diagnostics"]
    )


def test_analyze_graph_has_c03_column_lineage():
    response = client.post(
        "/api/sql/analyze",
        json={"sql": "select a from t"},
    )
    data = response.json()
    graph = data["graph_view_model"]
    node_ids = {node["id"] for node in graph["nodes"]}
    assert {"physical_table:t", "query_result:final"}.issubset(node_ids)
    assert {"physical_column:t.a", "output_column:a"}.issubset(node_ids)
    edges = {(edge["source"], edge["target"]) for edge in graph["edges"]}
    assert ("physical_table:t", "query_result:final") in edges
    assert ("physical_column:t.a", "output_column:a") in edges


def test_analyze_returns_schema_version():
    response = client.post(
        "/api/sql/analyze",
        json={"sql": "select 1"},
    )
    data = response.json()
    assert data["schema_version"] == "0.3.0-c05"


def test_analyze_returns_analysis_id():
    response = client.post(
        "/api/sql/analyze",
        json={"sql": "select 1"},
    )
    data = response.json()
    assert "analysis_id" in data


def test_analyze_empty_sql_fails():
    response = client.post(
        "/api/sql/analyze",
        json={"sql": ""},
    )
    data = response.json()
    assert data["status"] == "failed"
