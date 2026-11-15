from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _edges(sql: str) -> set[tuple[str, str, str]]:
    response = client.post(
        "/api/sql/analyze",
        json={"sql": sql, "dialect": "spark"},
    )
    assert response.status_code == 200
    return {
        (edge["source"], edge["target"], edge["edge_type"])
        for edge in response.json()["graph_view_model"]["edges"]
    }


def test_union_order_by_alias_depends_on_every_branch_position():
    edges = _edges(
        "select user_id as uid, created_at from active_users "
        "union all "
        "select member_id, paid_at from paid_users "
        "order by uid"
    )
    clause = "clause:order_by:query_result:final:1"

    assert {
        (
            "physical_column:active_users.user_id",
            clause,
            "order_dependency",
        ),
        (
            "physical_column:paid_users.member_id",
            clause,
            "order_dependency",
        ),
        (clause, "query_result:final", "order_effect"),
    } <= edges


def test_union_order_by_ordinal_depends_on_every_second_projection():
    edges = _edges(
        "select user_id, created_at from active_users "
        "union all "
        "select member_id, paid_at from paid_users "
        "order by 2 desc"
    )
    clause = "clause:order_by:query_result:final:1"

    assert {
        (
            "physical_column:active_users.created_at",
            clause,
            "order_dependency",
        ),
        (
            "physical_column:paid_users.paid_at",
            clause,
            "order_dependency",
        ),
    } <= edges


def test_intersect_order_expression_maps_output_to_both_branches():
    edges = _edges(
        "select user_id as uid from active_users "
        "intersect "
        "select member_id from paid_users "
        "order by lower(uid)"
    )
    clause = "clause:order_by:query_result:final:1"

    assert {
        (
            "physical_column:active_users.user_id",
            clause,
            "order_dependency",
        ),
        (
            "physical_column:paid_users.member_id",
            clause,
            "order_dependency",
        ),
    } <= edges


def test_union_cte_order_key_rolls_up_all_physical_branches():
    edges = _edges(
        "with current_users as ("
        "select user_id from raw_current_users"
        "), archived_users as ("
        "select member_id from raw_archived_users"
        ") select user_id as uid from current_users "
        "union all "
        "select member_id from archived_users "
        "order by uid"
    )
    clause = "clause:order_by:query_result:final:1"

    assert {
        (
            "physical_column:raw_current_users.user_id",
            clause,
            "order_dependency",
        ),
        (
            "physical_column:raw_archived_users.member_id",
            clause,
            "order_dependency",
        ),
    } <= edges


def test_union_by_name_order_key_maps_reordered_branch_aliases():
    edges = _edges(
        "select user_id as uid, created_at from active_users "
        "union by name "
        "select paid_at as created_at, member_id as uid from paid_users "
        "order by uid"
    )
    clause = "clause:order_by:query_result:final:1"

    assert {
        (
            "physical_column:active_users.user_id",
            clause,
            "order_dependency",
        ),
        (
            "physical_column:paid_users.member_id",
            clause,
            "order_dependency",
        ),
    } <= edges
    assert (
        "physical_column:paid_users.paid_at",
        clause,
        "order_dependency",
    ) not in edges


def test_except_global_order_maps_both_branches():
    edges = _edges(
        "select user_id as uid from active_users "
        "except "
        "select member_id from blocked_users "
        "order by uid"
    )
    clause = "clause:order_by:query_result:final:1"

    assert {
        (
            "physical_column:active_users.user_id",
            clause,
            "order_dependency",
        ),
        (
            "physical_column:blocked_users.member_id",
            clause,
            "order_dependency",
        ),
    } <= edges


def test_order_on_union_inside_cte_attaches_to_cte_owner():
    edges = _edges(
        "with combined as ("
        "select user_id as uid from active_users "
        "union all "
        "select member_id from paid_users "
        "order by uid"
        ") select uid from combined"
    )
    clause = "clause:order_by:cte:combined:1"

    assert {
        (
            "physical_column:active_users.user_id",
            clause,
            "order_dependency",
        ),
        (
            "physical_column:paid_users.member_id",
            clause,
            "order_dependency",
        ),
        (clause, "cte:combined", "order_effect"),
    } <= edges
