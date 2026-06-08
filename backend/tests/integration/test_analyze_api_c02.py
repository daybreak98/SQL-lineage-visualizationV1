from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_golden_case_c02():
    sql = """select
  country_name,
  count(order_no) as order_cnt
from dwd_order_di
group by country_name"""
    response = client.post("/api/sql/analyze", json={"sql": sql, "dialect": "spark"})
    data = response.json()

    assert data["status"] == "success"
    assert len(data["output_fields"]) == 2
    assert data["diagnostics_report"]["error_count"] == 0
    assert data["diagnostics_report"]["warning_count"] == 0

    names = [f["name"] for f in data["output_fields"]]
    assert "country_name" in names
    assert "order_cnt" in names

    edges = {
        (edge["source"], edge["target"])
        for edge in data["graph_view_model"]["edges"]
        if edge["edge_type"] == "column_lineage"
    }
    assert edges == {
        ("physical_column:dwd_order_di.country_name", "output_column:country_name"),
        ("physical_column:dwd_order_di.order_no", "output_column:order_cnt"),
    }


def test_simple_select_output_field():
    response = client.post("/api/sql/analyze", json={"sql": "select a from t"})
    data = response.json()

    assert data["status"] == "success"
    assert data["output_fields"][0]["name"] == "a"
    assert data["output_fields"][0]["expression"] == "a"


def test_alias_output_field():
    response = client.post("/api/sql/analyze", json={"sql": "select a as aa from t"})
    data = response.json()

    assert data["status"] == "success"
    assert data["output_fields"][0]["name"] == "aa"
    assert data["output_fields"][0]["expression"] == "a"


def test_count_output_field():
    response = client.post("/api/sql/analyze", json={"sql": "select count(*) as cnt from t"})
    data = response.json()

    assert data["output_fields"][0]["name"] == "cnt"
    assert data["output_fields"][0]["expression"] == "COUNT(*)"


def test_parse_error_sql():
    response = client.post("/api/sql/analyze", json={"sql": "select from"})
    data = response.json()

    assert data["status"] == "failed"
    assert len(data["output_fields"]) == 0
    assert data["diagnostics_report"]["error_count"] >= 1
    assert any(
        d["code"] == "SQL_PARSE_ERROR"
        for d in data["diagnostics_report"]["diagnostics"]
    )


def test_graph_model_has_column_lineage_on_success():
    response = client.post("/api/sql/analyze", json={"sql": "select a from t"})
    data = response.json()

    graph = data["graph_view_model"]
    node_ids = {node["id"] for node in graph["nodes"]}
    assert {"physical_table:t", "query_result:final"}.issubset(node_ids)
    assert {"physical_column:t.a", "output_column:a"}.issubset(node_ids)
    edges = {(edge["source"], edge["target"]) for edge in graph["edges"]}
    assert ("physical_table:t", "query_result:final") in edges
    assert ("physical_column:t.a", "output_column:a") in edges
    assert ("output_column:a", "query_result:final") in edges


def test_graph_model_empty_on_failure():
    response = client.post("/api/sql/analyze", json={"sql": "select from"})
    data = response.json()

    graph = data["graph_view_model"]
    assert graph["nodes"] == []
    assert graph["edges"] == []


def test_analyze_multiple_columns():
    response = client.post("/api/sql/analyze", json={"sql": "select a, b, c as cc from t"})
    data = response.json()

    assert data["status"] == "success"
    assert len(data["output_fields"]) == 3
    assert data["output_fields"][2]["name"] == "cc"


def test_analyze_column_graph_replaces_empty_c02_graph():
    response = client.post("/api/sql/analyze", json={"sql": "select a from t"})
    data = response.json()

    assert data["status"] == "success"
    assert len(data["graph_view_model"]["nodes"]) == 4
    assert len(data["graph_view_model"]["edges"]) == 3
