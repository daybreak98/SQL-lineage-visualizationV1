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


def test_hive_multi_insert_preserves_each_target_and_branch_subquery():
    response = client.post(
        "/api/sql/analyze",
        json={
            "dialect": "hive",
            "sql": (
                "-- \u751f\u4ea7\u6ce8\u91ca\uff1a\u5b57\u7b26\u4e32\u4e2d\u7684 "
                "insert \u4e0d\u80fd\u88ab\u8bef\u5207\u5206\n"
                "from (select id, amount, status, 'insert fake' as marker "
                "      from source_orders) s\n"
                "insert overwrite table target_a\n"
                "select s.id, s.amount where s.status = 'A'\n"
                "insert into table db.target_b (id, status)\n"
                "select s.id, regexp_replace(upper(s.status), '\\\\s+', '') "
                "where exists (select 1 from flags f where f.id = s.id)"
            ),
        },
    )
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert data["confidence_level"] == "high"
    assert {field["name"] for field in data["output_fields"]} == {
        "target_a.id", "target_a.amount", "db.target_b.id", "db.target_b.status",
    }
    node_ids = {node["id"] for node in data["graph_view_model"]["nodes"]}
    assert {"physical_table:source_orders", "physical_table:flags"} <= node_ids
    assert {
        ("physical_column:source_orders.id", "output_column:target_a.id"),
        ("physical_column:source_orders.amount", "output_column:target_a.amount"),
        ("physical_column:source_orders.id", "output_column:db.target_b.id"),
        ("physical_column:source_orders.status", "output_column:db.target_b.status"),
    } <= _edges(data)


def test_hive_multi_insert_shared_cte_rolls_up_to_physical_sources():
    response = client.post(
        "/api/sql/analyze",
        json={
            "dialect": "hive",
            "sql": (
                "with base as (select id, amount, status from source_orders)\n"
                "from base b\n"
                "insert overwrite table target_a partition(dt='2026-01-01')\n"
                "select b.status, sum(b.amount) as total group by b.status\n"
                "insert into table target_b (id, amount)\n"
                "select b.id, b.amount where b.amount > 0 order by b.id"
            ),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert {
        ("physical_column:source_orders.status", "output_column:target_a.status"),
        ("physical_column:source_orders.amount", "output_column:target_a.total"),
        ("physical_column:source_orders.id", "output_column:target_b.id"),
        ("physical_column:source_orders.amount", "output_column:target_b.amount"),
    } <= _edges(data)
