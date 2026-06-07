import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
GOLDEN_DIR = Path(__file__).resolve().parents[1] / "golden_cases"


def _sql(name: str) -> str:
    return (GOLDEN_DIR / name).read_text(encoding="utf-8")


def _metadata() -> dict:
    return json.loads((GOLDEN_DIR / "c06_metadata.json").read_text(encoding="utf-8"))


def _commit_metadata() -> dict:
    response = client.post(
        "/api/metadata/import/commit",
        json={"mode": "commit", "payload": _metadata()},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "committed"
    assert data["summary"]["table_count"] == 2
    assert data["summary"]["column_count"] == 5
    return data


def _analyze(sql_file: str) -> dict:
    response = client.post("/api/sql/analyze", json={"sql": _sql(sql_file)})
    assert response.status_code == 200
    data = response.json()
    _assert_analysis_contract(data)
    _assert_graph_integrity(data["graph_view_model"])
    return data


def _assert_analysis_contract(data: dict) -> None:
    assert data["schema_version"]
    assert data["analysis_id"]
    assert data["status"] in {"success", "partial", "failed"}
    assert isinstance(data["diagnostics_report"]["diagnostics"], list)
    assert isinstance(data["stage_statuses"], list)
    assert isinstance(data["output_fields"], list)
    assert isinstance(data["graph_view_model"]["nodes"], list)
    assert isinstance(data["graph_view_model"]["edges"], list)
    assert "complex_sql_guard" in data["capabilities"]
    assert "node_count" in data["summary"]
    assert "edge_count" in data["summary"]


def _assert_graph_integrity(graph: dict) -> None:
    nodes = graph["nodes"]
    edges = graph["edges"]
    node_ids = [node["id"] for node in nodes]
    edge_ids = [edge["id"] for edge in edges]

    assert len(node_ids) == len(set(node_ids))
    assert len(edge_ids) == len(set(edge_ids))

    node_id_set = set(node_ids)
    for edge in edges:
        assert edge["source"] in node_id_set, edge
        assert edge["target"] in node_id_set, edge


def _edge_set(data: dict) -> set[tuple[str, str, str]]:
    return {
        (edge["source"], edge["target"], edge["edge_type"])
        for edge in data["graph_view_model"]["edges"]
    }


def _node_labels_by_type(data: dict, node_type: str) -> set[str]:
    return {
        node["label"]
        for node in data["graph_view_model"]["nodes"]
        if node["node_type"] == node_type
    }


def _diagnostic_codes(data: dict) -> set[str]:
    return {
        diagnostic["code"]
        for diagnostic in data["diagnostics_report"]["diagnostics"]
    }


def test_c10_metadata_golden_can_be_committed_and_queried():
    _commit_metadata()

    tables_response = client.get("/api/metadata/tables")
    assert tables_response.status_code == 200
    table_names = {table["table_name"] for table in tables_response.json()["tables"]}
    assert {"dwd_order_di", "dim_user_df"} <= table_names

    columns_response = client.get("/api/metadata/columns?table_name=dwd_order_di")
    assert columns_response.status_code == 200
    column_names = {column["name"] for column in columns_response.json()["columns"]}
    assert column_names == {"order_no", "user_id", "order_amount"}


def test_c10_output_fields_golden_contract_stays_parseable():
    data = _analyze("c02_output_fields.sql")

    assert data["status"] in {"success", "partial"}
    assert {field["name"] for field in data["output_fields"]} == {"country_name", "order_cnt"}


def test_c10_single_table_golden_lineage_edges_are_stable():
    _commit_metadata()
    data = _analyze("c03_single_table.sql")

    assert data["status"] == "success"
    assert _node_labels_by_type(data, "output_column") == {"order_no", "uid"}
    assert {
        ("physical_column:dwd_order_di.order_no", "output_column:order_no", "column_lineage"),
        ("output_column:order_no", "query_result:final", "output_column_to_result"),
        ("physical_column:dwd_order_di.user_id", "output_column:uid", "column_lineage"),
        ("output_column:uid", "query_result:final", "output_column_to_result"),
    } <= _edge_set(data)


def test_c10_join_alias_golden_lineage_edges_are_stable():
    _commit_metadata()
    data = _analyze("c04_join_alias.sql")

    assert data["status"] == "success"
    assert _node_labels_by_type(data, "table") == {"dim_user_df", "dwd_order_di"}
    assert {
        ("physical_column:dim_user_df.country_name", "output_column:country_name", "column_lineage"),
        ("output_column:country_name", "query_result:final", "output_column_to_result"),
        ("physical_column:dwd_order_di.order_no", "output_column:order_no", "column_lineage"),
        ("output_column:order_no", "query_result:final", "output_column_to_result"),
    } <= _edge_set(data)


def test_c10_cte_golden_structure_path_is_stable():
    data = _analyze("c05_cte_metric.sql")

    assert data["status"] == "success"
    assert data["graph_view_model"]["view_mode"] == "subquery_dependency"
    assert {
        ("physical_table:dwd_order_di", "cte:order_base", "table_to_cte"),
        ("cte:order_base", "cte:metric_base", "cte_dependency"),
        ("cte:metric_base", "query_result:final", "cte_to_result"),
    } <= _edge_set(data)


def test_c10_select_star_golden_expands_with_metadata():
    _commit_metadata()
    data = _analyze("c07_select_star.sql")

    assert data["status"] == "success"
    assert _node_labels_by_type(data, "output_column") == {
        "order_no",
        "user_id",
        "order_amount",
    }


def test_c10_diagnostic_golden_cases_do_not_create_column_lineage():
    _commit_metadata()

    unknown = _analyze("c07_unknown_column.sql")
    assert unknown["status"] == "partial"
    assert "UNKNOWN_COLUMN" in _diagnostic_codes(unknown)
    assert not [
        edge
        for edge in unknown["graph_view_model"]["edges"]
        if edge["edge_type"] == "column_lineage"
    ]

    ambiguous = _analyze("c07_ambiguous_column.sql")
    assert ambiguous["status"] == "partial"
    assert "AMBIGUOUS_COLUMN" in _diagnostic_codes(ambiguous)
    assert not [
        edge
        for edge in ambiguous["graph_view_model"]["edges"]
        if edge["edge_type"] == "column_lineage"
    ]


def test_c10_expression_metric_golden_freezes_current_partial_behavior():
    _commit_metadata()
    data = _analyze("c09_expression_metric.sql")

    assert data["status"] == "partial"
    assert {field["name"] for field in data["output_fields"]} == {"gmv", "order_cnt", "adr"}
    assert "UNSUPPORTED_COMPLEX_QUERY" in _diagnostic_codes(data)
