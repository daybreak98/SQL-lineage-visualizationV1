from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _edge_set(data: dict) -> set[tuple[str, str, str]]:
    return {
        (edge["source"], edge["target"], edge["edge_type"])
        for edge in data["graph_view_model"]["edges"]
    }


def _diagnostic_codes(data: dict) -> set[str]:
    return {
        diagnostic["code"]
        for diagnostic in data["diagnostics_report"]["diagnostics"]
    }


def test_insert_select_inline_subquery_join_rolls_up_column_lineage():
    sql = """
    insert overwrite table ihotel_default.dwd_abtest_rule_info_di
    partition (dt='${zdt.addDay(-1).format("yyyy-MM-dd")}',user_id_type)
    select
        ab_exp_id,
        ab_version,
        ab_rule_version,
        device_id as ab_exp_value,
        user_id_type
    from (
        select
            ab_exp_id,
            ab_version,
            ab_rule_version,
            case ab_shuntbase
                when 'APP_UID' then 'uid'
                when 'USERID'  then 'user_id'
            end as user_id_type
        from ods_abtest_rule_info
        where dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
          and source = 'hotel'
          and ab_shuntbase in ('APP_UID','USERID')
    ) rule
    join (
        select expid, version, ruleversion, clientcode as device_id, dt, logdate
        from ods_abtest_sdk_log_endtime_hotel
        where dt='${zdt.addDay(-1).format("yyyyMMdd")}'
          and clientcode is not NULL
          and expid is not NULL
          and version is not NULL
          and ruleversion is not NULL
    ) ab
    on ab.expid = rule.ab_exp_id
       and ab.version = rule.ab_version
       and ab.ruleversion = rule.ab_rule_version
    group by 1,2,3,4,5
    """

    response = client.post("/api/sql/analyze", json={"sql": sql, "dialect": "hive"})

    assert response.status_code == 200
    data = response.json()
    assert "AMBIGUOUS_COLUMN" not in _diagnostic_codes(data)

    assert {
        ("physical_column:ods_abtest_rule_info.ab_exp_id", "output_column:ab_exp_id", "column_lineage"),
        ("physical_column:ods_abtest_rule_info.ab_version", "output_column:ab_version", "column_lineage"),
        (
            "physical_column:ods_abtest_rule_info.ab_rule_version",
            "output_column:ab_rule_version",
            "column_lineage",
        ),
        (
            "physical_column:ods_abtest_sdk_log_endtime_hotel.clientcode",
            "output_column:ab_exp_value",
            "column_lineage",
        ),
        ("physical_column:ods_abtest_rule_info.ab_shuntbase", "output_column:user_id_type", "column_lineage"),
    } <= _edge_set(data)
