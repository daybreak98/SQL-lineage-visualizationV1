import sqlglot

from app.services.derived_relation_schema_builder import build_derived_relation_schemas


def test_builds_top_level_inline_subquery_schemas():
    tree = sqlglot.parse_one(
        """
        select
            ab_exp_id,
            device_id as ab_exp_value,
            user_id_type
        from (
            select
                ab_exp_id,
                case ab_shuntbase
                    when 'APP_UID' then 'uid'
                    when 'USERID' then 'user_id'
                end as user_id_type
            from ods_abtest_rule_info
        ) rule
        join (
            select clientcode as device_id
            from ods_abtest_sdk_log_endtime_hotel
        ) ab
        on ab.device_id = rule.ab_exp_id
        """,
        dialect="hive",
    )

    result = build_derived_relation_schemas(tree, dialect="hive")

    assert set(result.schemas) == {"rule", "ab"}

    rule_schema = result.schemas["rule"]
    assert {
        (dep.output.column_name, tuple((inp.relation_name, inp.column_name) for inp in dep.inputs))
        for dep in rule_schema.output_columns.values()
    } == {
        ("ab_exp_id", (("ods_abtest_rule_info", "ab_exp_id"),)),
        ("user_id_type", (("ods_abtest_rule_info", "ab_shuntbase"),)),
    }

    ab_schema = result.schemas["ab"]
    assert {
        (dep.output.column_name, tuple((inp.relation_name, inp.column_name) for inp in dep.inputs))
        for dep in ab_schema.output_columns.values()
    } == {
        ("device_id", (("ods_abtest_sdk_log_endtime_hotel", "clientcode"),)),
    }


def test_cte_case_expression_resolves_all_alias_columns():
    tree = sqlglot.parse_one(
        """
        with order_base as (
          select
            case when o.is_valid = 1 then o.order_no end as valid_order_no
          from dwd_order_di o
        )
        select valid_order_no from order_base
        """,
        dialect="hive",
    )

    result = build_derived_relation_schemas(tree, dialect="hive")
    dep = result.schemas["order_base"].get_dependency("valid_order_no")

    assert dep is not None
    assert {
        (source.relation_name, source.column_name)
        for source in dep.inputs
    } == {
        ("dwd_order_di", "is_valid"),
        ("dwd_order_di", "order_no"),
    }


def test_cte_lateral_view_output_resolves_explode_input_column():
    tree = sqlglot.parse_one(
        """
        with exploded as (
          select
            b.order_id,
            amount_item
          from ods_order_log b
          lateral view explode(split(b.refund_amount, ',')) e as amount_item
        )
        select amount_item from exploded
        """,
        dialect="spark",
    )

    result = build_derived_relation_schemas(tree, dialect="spark")
    dep = result.schemas["exploded"].get_dependency("amount_item")

    assert dep is not None
    assert dep.transform_type == "lateral_view"
    assert {
        (source.relation_name, source.column_name)
        for source in dep.inputs
    } == {
        ("ods_order_log", "refund_amount"),
    }


def test_cte_set_operation_merges_branch_dependencies_by_ordinal():
    tree = sqlglot.parse_one(
        """
        with combined as (
          select id, amount from order_a
          union all
          select user_id, total_amount from order_b
        )
        select id, amount from combined
        """,
        dialect="spark",
    )

    result = build_derived_relation_schemas(tree, dialect="spark")
    schema = result.schemas["combined"]

    assert {
        (source.relation_name, source.column_name)
        for source in schema.get_dependency("id").inputs
    } == {
        ("order_a", "id"),
        ("order_b", "user_id"),
    }
    assert {
        (source.relation_name, source.column_name)
        for source in schema.get_dependency("amount").inputs
    } == {
        ("order_a", "amount"),
        ("order_b", "total_amount"),
    }


def test_inline_set_operation_merges_branch_dependencies_by_ordinal():
    tree = sqlglot.parse_one(
        """
        select id
        from (
          select id from order_a
          union all
          select user_id from order_b
        ) combined
        """,
        dialect="spark",
    )

    result = build_derived_relation_schemas(tree, dialect="spark")
    dependency = result.schemas["combined"].get_dependency("id")

    assert dependency is not None
    assert {
        (source.relation_name, source.column_name)
        for source in dependency.inputs
    } == {
        ("order_a", "id"),
        ("order_b", "user_id"),
    }


def test_nested_inline_subqueries_build_inner_schema_before_outer_schema():
    tree = sqlglot.parse_one(
        """
        select c.z
        from (
          select b.y * 2 as z
          from (
            select a.x + 1 as y
            from source_a a
          ) b
        ) c
        """,
        dialect="spark",
    )

    result = build_derived_relation_schemas(tree, dialect="spark")

    assert set(result.schemas) == {"b", "c"}
    inner = result.schemas["b"].get_dependency("y")
    outer = result.schemas["c"].get_dependency("z")
    assert inner is not None
    assert outer is not None
    assert {(source.relation_name, source.column_name) for source in inner.inputs} == {
        ("source_a", "x"),
    }
    assert {
        (source.relation_name, source.column_name, source.relation_kind)
        for source in outer.inputs
    } == {
        ("b", "y", "subquery"),
    }
