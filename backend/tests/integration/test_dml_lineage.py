from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _analyze(sql: str) -> dict:
    response = client.post(
        "/api/sql/analyze",
        json={"sql": sql, "dialect": "spark"},
    )
    assert response.status_code == 200
    return response.json()


def _edges(data: dict) -> set[tuple[str, str]]:
    return {
        (edge["source"], edge["target"])
        for edge in data["graph_view_model"]["edges"]
    }


def test_insert_target_columns_map_select_sources_by_position():
    data = _analyze(
        "insert into target_orders (order_id, total_amount) "
        "select id, amount from source_orders"
    )

    assert [field["name"] for field in data["output_fields"]] == [
        "order_id",
        "total_amount",
    ]
    node_ids = {node["id"] for node in data["graph_view_model"]["nodes"]}
    assert "physical_table:source_orders" in node_ids
    assert "physical_table:target_orders" not in node_ids
    assert {
        ("physical_column:source_orders.id", "output_column:order_id"),
        ("physical_column:source_orders.amount", "output_column:total_amount"),
    } <= _edges(data)


def test_merge_using_subquery_maps_update_and_insert_sources():
    data = _analyze(
        "merge into target_orders t "
        "using (select id, amount, status from source_orders) s "
        "on t.id = s.id "
        "when matched then update set t.amount = s.amount, t.status = s.status "
        "when not matched then insert (id, amount, status) "
        "values (s.id, s.amount, s.status)"
    )

    assert {field["name"] for field in data["output_fields"]} == {
        "id",
        "amount",
        "status",
    }
    assert {
        ("physical_column:source_orders.id", "output_column:id"),
        ("physical_column:source_orders.amount", "output_column:amount"),
        ("physical_column:source_orders.status", "output_column:status"),
    } <= _edges(data)


def test_merge_using_table_maps_sources_without_non_query_fallback():
    data = _analyze(
        "merge into target_orders t using source_orders s on t.id = s.id "
        "when matched then update set t.amount = s.amount "
        "when not matched then insert (id, amount) values (s.id, s.amount)"
    )

    assert data["status"] == "success"
    assert "non_query_statement" not in data["unsupported_features"]
    assert {
        ("physical_column:source_orders.id", "output_column:id"),
        ("physical_column:source_orders.amount", "output_column:amount"),
    } <= _edges(data)
