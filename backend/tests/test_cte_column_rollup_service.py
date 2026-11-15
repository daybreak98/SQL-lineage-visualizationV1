from app.domain.cte_rollup_models import (
    ColumnDependency, ColumnRef, DerivedRelationSchema,
)
from app.services.cte_column_rollup_service import CteColumnRollupService


def cref(relation, column, kind):
    return ColumnRef(relation_name=relation, column_name=column, relation_kind=kind)


def dep(output_relation, output_column, inputs, output_kind="cte", transform="projection"):
    return ColumnDependency(
        output=cref(output_relation, output_column, output_kind),
        inputs=inputs,
        transform_type=transform,
    )


def schema(name, dependencies):
    s = DerivedRelationSchema(relation_name=name, relation_kind="cte")
    for d in dependencies:
        s.add_dependency(d)
    return s


def test_multilevel_cte_projection_rollup():
    order_base = schema("order_base", [
        dep("order_base", "user_id", [cref("dwd_order_di", "user_id", "table")]),
    ])
    metric_base = schema("metric_base", [
        dep("metric_base", "user_id", [cref("order_base", "user_id", "cte")]),
    ])
    immediate = [dep("final", "user_id", [cref("metric_base", "user_id", "cte")], output_kind="output")]

    result = CteColumnRollupService({"order_base": order_base, "metric_base": metric_base}).rollup(immediate)
    roots = result.root_dependencies[0].inputs
    assert [(r.relation_name, r.column_name) for r in roots] == [("dwd_order_di", "user_id")]
    assert result.diagnostics == []


def test_aggregate_dependency_rollup():
    order_base = schema("order_base", [
        dep("order_base", "order_no", [cref("dwd_order_di", "order_no", "table")]),
    ])
    metric_base = schema("metric_base", [
        dep("metric_base", "cnt", [cref("order_base", "order_no", "cte")], transform="aggregate"),
    ])
    immediate = [dep("final", "cnt", [cref("metric_base", "cnt", "cte")], output_kind="output")]
    result = CteColumnRollupService({"order_base": order_base, "metric_base": metric_base}).rollup(immediate)
    roots = result.root_dependencies[0].inputs
    assert [(r.relation_name, r.column_name) for r in roots] == [("dwd_order_di", "order_no")]


def test_missing_derived_column_degrades():
    metric_base = schema("metric_base", [])
    immediate = [dep("final", "x", [cref("metric_base", "missing_col", "cte")], output_kind="output")]
    result = CteColumnRollupService({"metric_base": metric_base}).rollup(immediate)
    roots = result.root_dependencies[0].inputs
    assert [(r.relation_name, r.column_name) for r in roots] == [("metric_base", "missing_col")]
    assert any(d.code == "UNKNOWN_DERIVED_COLUMN" for d in result.diagnostics)


def test_cycle_protection():
    a = schema("a", [dep("a", "x", [cref("b", "x", "cte")])])
    b = schema("b", [dep("b", "x", [cref("a", "x", "cte")])])
    immediate = [dep("final", "x", [cref("a", "x", "cte")], output_kind="output")]
    result = CteColumnRollupService({"a": a, "b": b}).rollup(immediate)
    assert result.root_dependencies[0].inputs
    assert any(d.code == "CYCLIC_DERIVED_RELATION" for d in result.diagnostics)
