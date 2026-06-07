"""
Regression tests for CTE expression schema building.

This file is a reference test suite. Adapt imports and assertion helpers to the
actual project test framework.
"""

import pytest


@pytest.mark.parametrize(
    "sql,cte_name,output_col,expected_inputs,transform_type",
    [
        (
            """
            with search_result as (
              select count(distinct a.search_request_uid) as search_times
              from search_base a
            )
            select search_times from search_result
            """,
            "search_result",
            "search_times",
            {("search_base", "search_request_uid", "cte")},
            "aggregate",
        ),
        (
            """
            with order_metric as (
              select price * quantity as gmv
              from order_base
            )
            select gmv from order_metric
            """,
            "order_metric",
            "gmv",
            {("order_base", "price", "cte"), ("order_base", "quantity", "cte")},
            "expression",
        ),
        (
            """
            with order_metric as (
              select case when order_status = 'DONE' then amount else 0 end as valid_amount
              from order_base
            )
            select valid_amount from order_metric
            """,
            "order_metric",
            "valid_amount",
            {("order_base", "order_status", "cte"), ("order_base", "amount", "cte")},
            "case_when",
        ),
    ],
)
def test_cte_expression_dependencies(sql, cte_name, output_col, expected_inputs, transform_type):
    """
    Adapt this test to the actual project:
        result = analyze_sql(sql)
        schema = result.internal.cte_schemas[cte_name]
    """
    result = analyze_sql_for_test(sql)
    dep = result.cte_schemas[cte_name.lower()][output_col.lower()]

    actual_inputs = {
        (ref.relation_name, ref.column_name, ref.relation_kind)
        for ref in dep.input_columns
    }
    assert actual_inputs == expected_inputs
    assert dep.transform_type == transform_type
    assert dep.origin == "expression_analyzer"


def test_qualified_column_resolves_alias_not_alias_as_table():
    sql = """
    with metric as (
      select count(distinct o.user_id) as order_user_cnt
      from order_base o
      join user_base u on o.user_id = u.user_id
    )
    select order_user_cnt from metric
    """
    result = analyze_sql_for_test(sql)
    dep = result.cte_schemas["metric"]["order_user_cnt"]
    assert [(r.relation_name, r.column_name, r.relation_kind) for r in dep.input_columns] == [
        ("order_base", "user_id", "cte")
    ]


def test_bare_column_ambiguous_should_not_guess():
    sql = """
    with metric as (
      select count(distinct user_id) as user_cnt
      from order_base o
      join user_base u on o.user_id = u.user_id
    )
    select user_cnt from metric
    """
    result = analyze_sql_for_test(
        sql,
        metadata={
            "order_base": ["user_id"],
            "user_base": ["user_id"],
        },
    )
    assert any(d.code == "AMBIGUOUS_COLUMN" for d in result.diagnostics)
    dep = result.cte_schemas["metric"].get("user_cnt")
    assert dep is None or dep.input_columns == []


def test_count_star_does_not_generate_unknown_star():
    sql = """
    with metric as (
      select count(*) as order_cnt
      from order_base
    )
    select order_cnt from metric
    """
    result = analyze_sql_for_test(sql)
    dep = result.cte_schemas["metric"]["order_cnt"]
    assert dep.transform_type == "aggregate"
    assert dep.dependency_type == "relation_rowset"
    assert dep.input_columns == []


def test_constant_expression_has_no_column_dependency():
    sql = """
    with flags as (
      select 1 as is_valid
      from order_base
    )
    select is_valid from flags
    """
    result = analyze_sql_for_test(sql)
    dep = result.cte_schemas["flags"]["is_valid"]
    assert dep.transform_type == "constant"
    assert dep.dependency_type == "none"
    assert dep.input_columns == []


# -----------------------------------------------------------------------------
# Test adapter placeholder.
# -----------------------------------------------------------------------------


def analyze_sql_for_test(sql: str, metadata=None):
    """
    Replace with the project's actual test helper.

    Expected return object shape:
        result.cte_schemas[cte_name][output_col] -> ColumnDependency
        result.diagnostics -> list[Diagnostic]
    """
    raise NotImplementedError("Wire to project analyze/build_cte_schemas test helper.")
