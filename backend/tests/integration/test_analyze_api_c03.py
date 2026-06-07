from fastapi.testclient import TestClient

from app.domain import diagnostics_model as diag_codes
from app.main import app

client = TestClient(app)


def test_analyze_c03_returns_column_graph_for_simple_select():
    response = client.post("/api/sql/analyze", json={"sql": "select a from t"})
    data = response.json()

    assert response.status_code == 200
    assert data["schema_version"] == "0.3.0-c09"
    assert data["analysis_id"] == "analysis:c09"
    assert data["status"] == "success"

    graph = data["graph_view_model"]
    assert graph["view_mode"] == "table"
    node_ids = {node["id"] for node in graph["nodes"]}
    assert "physical_table:t" in node_ids
    assert "query_result:final" in node_ids
    assert "physical_column:t.a" in node_ids
    assert "output_column:a" in node_ids
    edges = {(edge["source"], edge["target"], edge["edge_type"]) for edge in graph["edges"]}
    assert ("physical_table:t", "query_result:final", "table_to_result") in edges
    assert ("physical_column:t.a", "output_column:a", "column_lineage") in edges
    assert ("output_column:a", "query_result:final", "output_column_to_result") in edges


def test_analyze_c03_golden_case_single_table_lineage():
    sql = """select
  order_no,
  user_id as uid
from dwd_order_di"""
    response = client.post("/api/sql/analyze", json={"sql": sql, "dialect": "spark"})
    data = response.json()

    assert data["status"] == "success"
    graph = data["graph_view_model"]
    edges = {(edge["source"], edge["target"]) for edge in graph["edges"]}
    assert ("physical_table:dwd_order_di", "query_result:final") in edges
    assert ("physical_column:dwd_order_di.order_no", "output_column:order_no") in edges
    assert ("output_column:order_no", "query_result:final") in edges
    assert ("physical_column:dwd_order_di.user_id", "output_column:uid") in edges
    assert ("output_column:uid", "query_result:final") in edges

    node_ids = {node["id"] for node in graph["nodes"]}
    assert all(source in node_ids and target in node_ids for source, target in edges)


def test_analyze_c03_alias_output_field_keeps_output_fields_and_graph():
    response = client.post("/api/sql/analyze", json={"sql": "select a as aa from t"})
    data = response.json()

    assert data["status"] == "success"
    assert data["output_fields"][0]["name"] == "aa"
    assert data["output_fields"][0]["expression"] == "a"
    edges = {
        (edge["source"], edge["target"])
        for edge in data["graph_view_model"]["edges"]
    }
    assert ("physical_table:t", "query_result:final") in edges
    assert ("physical_column:t.a", "output_column:aa") in edges
    assert ("output_column:aa", "query_result:final") in edges


def test_analyze_c03_unqualified_join_still_returns_partial_not_fake_success():
    response = client.post(
        "/api/sql/analyze",
        json={"sql": "select a from t join u on t.id = u.id"},
    )
    data = response.json()

    assert data["status"] == "partial"
    node_ids = {node["id"] for node in data["graph_view_model"]["nodes"]}
    assert {"physical_table:t", "physical_table:u", "query_result:final"}.issubset(node_ids)
    edges = {(edge["source"], edge["target"]) for edge in data["graph_view_model"]["edges"]}
    assert ("physical_table:t", "query_result:final") in edges
    assert ("physical_table:u", "query_result:final") in edges
    assert any(
        diagnostic["code"] == diag_codes.AMBIGUOUS_COLUMN
        for diagnostic in data["diagnostics_report"]["diagnostics"]
    )


def test_analyze_c03_select_star_returns_partial_with_specific_diagnostic():
    response = client.post("/api/sql/analyze", json={"sql": "select * from t"})
    data = response.json()

    assert data["status"] == "partial"
    node_ids = {node["id"] for node in data["graph_view_model"]["nodes"]}
    assert {"physical_table:t", "query_result:final"}.issubset(node_ids)
    assert bool({"select_star", "metadata_missing"} & set(data["unsupported_features"]))
    star_diags = {diagnostic["code"] for diagnostic in data["diagnostics_report"]["diagnostics"]}
    assert star_diags & {"SELECT_STAR_METADATA_REQUIRED", "METADATA_MISSING", "UNSUPPORTED_SELECT_STAR"}


def test_analyze_c03_include_graph_false_keeps_graph_empty():
    response = client.post(
        "/api/sql/analyze",
        json={
            "sql": "select a from t",
            "analysis_options": {
                "include_graph": False,
                "include_semantics": False,
                "include_diagnostics": True,
                "include_source_location": True,
                "include_expression_lineage": False,
            },
        },
    )
    data = response.json()

    assert data["status"] == "success"
    assert data["output_fields"][0]["name"] == "a"
    assert data["graph_view_model"]["nodes"] == []
    assert data["graph_view_model"]["edges"] == []
