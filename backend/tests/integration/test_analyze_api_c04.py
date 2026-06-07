from fastapi.testclient import TestClient

from app.domain import diagnostics_model as diag_codes
from app.main import app

client = TestClient(app)


def test_analyze_c04_golden_join_alias_lineage():
    sql = """select
  u.country_name,
  o.order_no
from dim_user_df u
join dwd_order_di o
  on u.user_id = o.user_id"""

    response = client.post("/api/sql/analyze", json={"sql": sql, "dialect": "spark"})
    data = response.json()

    assert response.status_code == 200
    assert data["schema_version"] == "0.3.0-c09"
    assert data["analysis_id"] == "analysis:c09"
    assert data["status"] == "success"

    graph = data["graph_view_model"]
    assert graph["view_mode"] == "table"
    edges = {(edge["source"], edge["target"]) for edge in graph["edges"]}
    assert ("physical_table:dim_user_df", "query_result:final") in edges
    assert ("physical_table:dwd_order_di", "query_result:final") in edges
    assert (
        "physical_column:dim_user_df.country_name",
        "output_column:country_name",
    ) in edges
    assert (
        "physical_column:dwd_order_di.order_no",
        "output_column:order_no",
    ) in edges

    node_ids = {node["id"] for node in graph["nodes"]}
    assert all(source in node_ids and target in node_ids for source, target in edges)


def test_analyze_c04_single_table_alias_lineage():
    response = client.post(
        "/api/sql/analyze",
        json={"sql": "select o.order_no from dwd_order_di o"},
    )
    data = response.json()

    assert data["status"] == "success"
    edges = {
        (edge["source"], edge["target"])
        for edge in data["graph_view_model"]["edges"]
    }
    assert ("physical_table:dwd_order_di", "query_result:final") in edges
    assert ("physical_column:dwd_order_di.order_no", "output_column:order_no") in edges


def test_analyze_c04_unknown_table_alias_returns_partial_diagnostic():
    response = client.post("/api/sql/analyze", json={"sql": "select x.a from t"})
    data = response.json()

    assert data["status"] == "partial"
    node_ids = {node["id"] for node in data["graph_view_model"]["nodes"]}
    assert {"physical_table:t", "query_result:final"}.issubset(node_ids)
    assert ("physical_table:t", "query_result:final") in {
        (edge["source"], edge["target"])
        for edge in data["graph_view_model"]["edges"]
    }
    assert any(
        diagnostic["code"] == diag_codes.UNKNOWN_TABLE_ALIAS
        for diagnostic in data["diagnostics_report"]["diagnostics"]
    )


def test_analyze_c04_unqualified_join_field_is_ambiguous():
    response = client.post(
        "/api/sql/analyze",
        json={"sql": "select a from t1 join t2 on t1.id = t2.id"},
    )
    data = response.json()

    assert data["status"] == "partial"
    node_ids = {node["id"] for node in data["graph_view_model"]["nodes"]}
    assert {"physical_table:t1", "physical_table:t2", "query_result:final"}.issubset(node_ids)
    edges = {(edge["source"], edge["target"]) for edge in data["graph_view_model"]["edges"]}
    assert ("physical_table:t1", "query_result:final") in edges
    assert ("physical_table:t2", "query_result:final") in edges
    assert any(
        diagnostic["code"] == diag_codes.AMBIGUOUS_COLUMN
        for diagnostic in data["diagnostics_report"]["diagnostics"]
    )


def test_analyze_c04_partial_can_return_known_edges_and_diagnostics():
    response = client.post(
        "/api/sql/analyze",
        json={
            "sql": (
                "select u.country_name, a "
                "from dim_user_df u "
                "join dwd_order_di o on u.user_id = o.user_id"
            )
        },
    )
    data = response.json()

    assert data["status"] == "partial"
    edges = {
        (edge["source"], edge["target"])
        for edge in data["graph_view_model"]["edges"]
    }
    assert ("physical_table:dim_user_df", "query_result:final") in edges
    assert ("physical_table:dwd_order_di", "query_result:final") in edges
    assert ("physical_column:dim_user_df.country_name", "output_column:country_name") in edges
    assert any(
        diagnostic["code"] == diag_codes.AMBIGUOUS_COLUMN
        for diagnostic in data["diagnostics_report"]["diagnostics"]
    )
