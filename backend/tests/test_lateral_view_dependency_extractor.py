import sqlglot
from sqlglot import exp

from app.services.lateral_view_dependency_extractor import (
    extract_lateral_view_dependencies,
)


def test_extracts_lateral_output_and_expression_source_column():
    tree = sqlglot.parse_one(
        """
        select b.order_id, amount_item
        from ods_order_log b
        lateral view explode(split(b.refund_amount, ',')) e as amount_item
        """,
        dialect="spark",
    )
    select_node = tree.find(exp.Select)

    dependencies = extract_lateral_view_dependencies(select_node)

    assert [
        (
            dependency.output_alias,
            dependency.output_column,
            dependency.source_table_alias,
            dependency.source_column,
        )
        for dependency in dependencies
    ] == [
        ("e", "amount_item", "b", "refund_amount"),
    ]


def test_does_not_extract_lateral_view_from_nested_select_scope():
    tree = sqlglot.parse_one(
        """
        select nested.order_id
        from (
          select b.order_id, amount_item
          from ods_order_log b
          lateral view explode(b.refund_items) e as amount_item
        ) nested
        """,
        dialect="spark",
    )
    outer_select = tree.find(exp.Select)

    assert extract_lateral_view_dependencies(outer_select) == []
