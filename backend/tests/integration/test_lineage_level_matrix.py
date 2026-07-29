import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _analyze(sql: str, dialect: str = "spark") -> dict:
    response = client.post("/api/sql/analyze", json={"sql": sql, "dialect": dialect})
    assert response.status_code == 200
    return response.json()


def _edge_set(data: dict) -> set[tuple[str, str, str]]:
    return {
        (edge["source"], edge["target"], edge["edge_type"])
        for edge in data["graph_view_model"]["edges"]
    }


@pytest.mark.parametrize(
    ("case_id", "dialect", "sql", "expected_tables", "expected_column_edges"),
    [
        (
            "simple_projection",
            "spark",
            "select user_id, order_amount * 1.1 as gross_amount from dwd_order_di",
            {"dwd_order_di"},
            {
                ("physical_column:dwd_order_di.user_id", "output_column:user_id"),
                ("physical_column:dwd_order_di.order_amount", "output_column:gross_amount"),
            },
        ),
        (
            "generic_projection",
            "generic",
            "select user_id, coalesce(order_amount, 0) as gross_amount from dwd_order_di",
            {"dwd_order_di"},
            {
                ("physical_column:dwd_order_di.user_id", "output_column:user_id"),
                ("physical_column:dwd_order_di.order_amount", "output_column:gross_amount"),
            },
        ),
        (
            "join_projection",
            "spark",
            "select o.order_id, u.country_name from fact_order o left join dim_user u on o.user_id=u.user_id",
            {"fact_order", "dim_user"},
            {
                ("physical_column:fact_order.order_id", "output_column:order_id"),
                ("physical_column:dim_user.country_name", "output_column:country_name"),
            },
        ),
        (
            "cte_aggregation",
            "spark",
            "with base as (select user_id,order_amount,is_valid from fact_order), "
            "agg as (select user_id,sum(order_amount) gmv,count(case when is_valid=1 then 1 end) valid_cnt "
            "from base group by user_id) select user_id,gmv,valid_cnt from agg",
            {"fact_order"},
            {
                ("physical_column:fact_order.user_id", "output_column:user_id"),
                ("physical_column:fact_order.order_amount", "output_column:gmv"),
                ("physical_column:fact_order.is_valid", "output_column:valid_cnt"),
            },
        ),
        (
            "window_function",
            "spark",
            "select user_id,order_id,row_number() over(partition by user_id order by event_time desc) rn from fact_order",
            {"fact_order"},
            {
                ("physical_column:fact_order.user_id", "output_column:rn"),
                ("physical_column:fact_order.event_time", "output_column:rn"),
            },
        ),
        (
            "case_coalesce",
            "spark",
            "select user_id,case when status='paid' then coalesce(pay_amount,0) else 0 end paid_amount from fact_order",
            {"fact_order"},
            {
                ("physical_column:fact_order.status", "output_column:paid_amount"),
                ("physical_column:fact_order.pay_amount", "output_column:paid_amount"),
            },
        ),
        (
            "insert_partition",
            "hive",
            "insert overwrite table ads_user_gmv partition(dt='2026-07-16') "
            "select user_id,sum(order_amount) gmv from fact_order where dt='2026-07-16' group by user_id",
            {"fact_order"},
            {
                ("physical_column:fact_order.user_id", "output_column:user_id"),
                ("physical_column:fact_order.order_amount", "output_column:gmv"),
            },
        ),
        (
            "multi_cte_join",
            "spark",
            "with orders as (select order_id,user_id,amount from fact_order), "
            "users as (select user_id,country from dim_user) "
            "select u.country,sum(o.amount) gmv from orders o join users u on o.user_id=u.user_id group by u.country",
            {"fact_order", "dim_user"},
            {
                ("physical_column:dim_user.country", "output_column:country"),
                ("physical_column:fact_order.amount", "output_column:gmv"),
            },
        ),
    ],
)
def test_common_sql_shapes_have_valid_table_and_column_lineage(
    case_id: str,
    dialect: str,
    sql: str,
    expected_tables: set[str],
    expected_column_edges: set[tuple[str, str]],
):
    data = _analyze(sql, dialect)
    graph = data["graph_view_model"]
    nodes = graph["nodes"]
    edges = graph["edges"]
    node_ids = {node["id"] for node in nodes}

    assert data["status"] == "success", case_id
    assert expected_tables <= {
        node["label"] for node in nodes if node["node_type"] == "table"
    }
    assert expected_column_edges <= {
        (edge["source"], edge["target"])
        for edge in edges
        if edge["edge_type"] == "column_lineage"
    }
    assert all(edge["source"] in node_ids and edge["target"] in node_ids for edge in edges)
    assert all(
        edge["source"] != edge["target"]
        for edge in edges
        if edge["edge_type"] == "column_lineage"
    )


def test_inline_subquery_has_subquery_table_and_column_levels():
    data = _analyze(
        """
        select s.user_id, s.gmv
        from (
          select user_id, sum(order_amount) as gmv
          from fact_order
          group by user_id
        ) s
        """
    )

    assert data["status"] == "success"
    assert data["graph_view_model"]["view_mode"] == "subquery_dependency"
    assert {
        ("physical_table:fact_order", "subquery:s", "table_to_subquery"),
        ("subquery:s", "query_result:final", "subquery_to_result"),
        ("physical_column:fact_order.user_id", "output_column:user_id", "column_lineage"),
        ("physical_column:fact_order.order_amount", "output_column:gmv", "column_lineage"),
    } <= _edge_set(data)


def test_union_all_rolls_up_each_branch_by_output_position():
    data = _analyze(
        """
        select user_id, amount from order_a
        union all
        select uid, total_amount from order_b
        """
    )

    assert data["status"] == "success"
    assert {
        ("physical_column:order_a.user_id", "output_column:user_id", "column_lineage"),
        ("physical_column:order_b.uid", "output_column:user_id", "column_lineage"),
        ("physical_column:order_a.amount", "output_column:amount", "column_lineage"),
        ("physical_column:order_b.total_amount", "output_column:amount", "column_lineage"),
    } <= _edge_set(data)


def test_union_all_inside_cte_rolls_up_every_branch():
    data = _analyze(
        """
        with combined as (
          select id, amount from order_a
          union all
          select user_id, total_amount from order_b
        )
        select id, amount from combined
        """
    )

    assert data["status"] == "success"
    assert {
        ("physical_column:order_a.id", "output_column:id", "column_lineage"),
        ("physical_column:order_b.user_id", "output_column:id", "column_lineage"),
        ("physical_column:order_a.amount", "output_column:amount", "column_lineage"),
        ("physical_column:order_b.total_amount", "output_column:amount", "column_lineage"),
    } <= _edge_set(data)


def test_union_all_inside_inline_subquery_rolls_up_every_branch():
    data = _analyze(
        """
        select id
        from (
          select id from order_a
          union all
          select user_id from order_b
        ) combined
        """
    )

    assert data["status"] == "success"
    assert {
        ("physical_column:order_a.id", "output_column:id", "column_lineage"),
        ("physical_column:order_b.user_id", "output_column:id", "column_lineage"),
    } <= _edge_set(data)
    assert not any(
        edge[0].startswith("physical_column:subquery:")
        for edge in _edge_set(data)
        if edge[2] == "column_lineage"
    )


def test_nested_inline_expression_rolls_up_to_root_physical_column():
    data = _analyze(
        """
        select c.z
        from (
          select b.y * 2 as z
          from (
            select a.x + 1 as y
            from source_a a
          ) b
        ) c
        """
    )

    assert data["status"] == "success"
    assert (
        "physical_column:source_a.x",
        "output_column:z",
        "column_lineage",
    ) in _edge_set(data)
    assert not any(
        edge[0] == "physical_column:b.y"
        for edge in _edge_set(data)
        if edge[2] == "column_lineage"
    )
    assert {
        node["id"]
        for node in data["graph_view_model"]["nodes"]
        if node["node_type"] == "output_column"
    } == {"output_column:z"}


def test_lateral_view_output_rolls_up_to_explode_input():
    data = _analyze(
        """
        select t.user_id, item_id
        from user_items t
        lateral view explode(t.item_ids) e as item_id
        """,
        dialect="hive",
    )

    assert {
        ("physical_column:user_items.user_id", "output_column:user_id", "column_lineage"),
        ("physical_column:user_items.item_ids", "output_column:item_id", "column_lineage"),
    } <= _edge_set(data)


def test_nested_cte_lateral_view_does_not_block_final_select_lineage():
    data = _analyze(
        """
        with exploded as (
          select t.user_id, item_id
          from user_items t
          lateral view explode(t.item_ids) e as item_id
        ),
        item_counts as (
          select user_id, count(item_id) as item_count
          from exploded
          group by user_id
        )
        select user_id, item_count
        from item_counts
        """,
        dialect="hive",
    )

    assert {
        ("physical_column:user_items.user_id", "output_column:user_id", "column_lineage"),
        ("physical_column:user_items.item_ids", "output_column:item_count", "column_lineage"),
    } <= _edge_set(data)


def test_scalar_subquery_preserves_structure_and_inner_column_dependency():
    data = _analyze(
        """
        select
          o.order_id,
          (select max(p.pay_amount) from payment p where p.order_id=o.order_id) as max_pay
        from fact_order o
        """
    )

    assert data["graph_view_model"]["view_mode"] == "subquery_dependency"
    assert {
        "physical_table:payment",
        "subquery:max_pay",
        "query_result:final",
    } <= {node["id"] for node in data["graph_view_model"]["nodes"]}
    assert (
        "physical_column:payment.pay_amount",
        "output_column:max_pay",
        "column_lineage",
    ) in _edge_set(data)


def test_unqualified_scalar_subquery_column_uses_inner_select_scope():
    data = _analyze(
        """
        select
          o.order_id,
          (select max(pay_amount) from payment p where p.order_id=o.order_id) as max_pay
        from fact_order o
        """
    )

    assert data["status"] == "success"
    assert (
        "physical_column:payment.pay_amount",
        "output_column:max_pay",
        "column_lineage",
    ) in _edge_set(data)
    assert not any(
        diagnostic["code"] == "AMBIGUOUS_COLUMN"
        and "pay_amount" in diagnostic["message"]
        for diagnostic in data["diagnostics_report"]["diagnostics"]
    )


def test_constant_outputs_remain_visible_without_fake_source_edges():
    data = _analyze(
        "select user_id, 1 as flag, current_date() as run_date from fact_order"
    )

    assert data["status"] == "success"
    node_ids = {node["id"] for node in data["graph_view_model"]["nodes"]}
    assert {"output_column:user_id", "output_column:flag", "output_column:run_date"} <= node_ids
    assert not any(
        edge["target"] in {"output_column:flag", "output_column:run_date"}
        and edge["edge_type"] == "column_lineage"
        for edge in data["graph_view_model"]["edges"]
    )


def test_cte_set_operation_constants_do_not_report_unknown_derived_columns():
    data = _analyze(
        """
        with sources as (
          select order_id, 'online' as source_type from online_orders
          union all
          select order_id, 'offline' as source_type from offline_orders
        )
        select source_type
        from sources
        """
    )

    assert data["status"] == "success"
    assert not any(
        diagnostic["code"] in {"UNKNOWN_COLUMN", "UNKNOWN_DERIVED_COLUMN"}
        and "source_type" in diagnostic["message"]
        for diagnostic in data["diagnostics_report"]["diagnostics"]
    )
    assert not any(
        edge["target"] == "output_column:source_type"
        and edge["edge_type"] == "column_lineage"
        for edge in data["graph_view_model"]["edges"]
    )


def test_correlated_exists_is_visible_in_subquery_structure():
    data = _analyze(
        """
        select o.order_id
        from fact_order o
        where exists (
          select 1 from payment p where p.order_id=o.order_id
        )
        """
    )

    assert data["status"] == "success"
    assert data["graph_view_model"]["view_mode"] == "subquery_dependency"
    assert {
        "physical_table:fact_order",
        "physical_table:payment",
        "subquery:exists_subquery_1",
        "query_result:final",
    } <= {node["id"] for node in data["graph_view_model"]["nodes"]}
    assert {
        ("physical_table:payment", "subquery:exists_subquery_1", "table_to_subquery"),
        ("subquery:exists_subquery_1", "query_result:final", "subquery_to_result"),
    } <= _edge_set(data)


def test_ddl_only_script_returns_partial_empty_graph_instead_of_server_error():
    data = _analyze(
        "drop table t; create table t(a int); msck repair table t"
    )

    assert data["status"] == "partial"
    assert data["output_fields"] == []
    assert data["graph_view_model"]["nodes"] == []
    assert data["graph_view_model"]["edges"] == []
    assert any(
        diagnostic["code"] == "UNSUPPORTED_SQL_STRUCTURE"
        for diagnostic in data["diagnostics_report"]["diagnostics"]
    )
