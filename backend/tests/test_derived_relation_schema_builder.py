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
