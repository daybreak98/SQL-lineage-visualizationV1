from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_template_sql_response_includes_guard_fields():
    response = client.post(
        "/api/sql/analyze",
        json={
            "sql": 'select order_id from ods_order_log where dt = ${zdt.addDay(-1).format("yyyyMMdd")}',
            "dialect": "spark",
        },
    )
    data = response.json()

    assert data["status"] == "success"
    assert data["sql_text_bundle"]["has_analysis_sql"] is True
    assert data["capabilities"]["complex_sql_guard"] is True
    assert any(diagnostic["code"] == "TEMPLATE_SQL_DETECTED" for diagnostic in data["diagnostics_report"]["diagnostics"])


def test_lateral_view_response_returns_guard_diagnostics():
    response = client.post(
        "/api/sql/analyze",
        json={
            "sql": (
                "select b.order_id, amount_item from ods_order_log b "
                "lateral view explode(split(b.refund_amount, ',')) e as amount_item "
                "where b.dt = '20260101'"
            ),
            "dialect": "spark",
        },
    )
    data = response.json()

    assert data["status"] == "partial"
    assert "lateral_view" in data["unsupported_features"]
    assert any(diagnostic["code"] == "UNSUPPORTED_LATERAL_VIEW" for diagnostic in data["diagnostics_report"]["diagnostics"])


def test_partial_fallback_response_exposes_segments_and_parse_attempts():
    response = client.post(
        "/api/sql/analyze",
        json={
            "sql": (
                "with a as (select id from t1), "
                "broken as (select from), "
                "c as (select id from t2) "
                "select a.id from a join c on a.id = c.id"
            ),
            "dialect": "spark",
        },
    )
    data = response.json()

    assert data["status"] == "partial"
    assert data["parse_attempts"]
    assert any(segment["segment_type"] == "cte_item" for segment in data["segments"])
    assert any(diagnostic["code"] == "PARTIAL_PARSE_RESULT" for diagnostic in data["diagnostics_report"]["diagnostics"])


def test_preflight_error_response_is_not_high_success():
    response = client.post(
        "/api/sql/analyze",
        json={
            "sql": "select a from t",
            "dialect": "spark",
            "options": {"max_sql_chars": 5},
        },
    )
    data = response.json()

    assert data["status"] == "partial"
    assert data["confidence_level"] != "high"
    assert data["diagnostics_report"]["error_count"] == 1
    assert any(diagnostic["code"] == "ANALYSIS_TIMEOUT" for diagnostic in data["diagnostics_report"]["diagnostics"])


def test_shell_script_selects_insert_source_query_before_parse():
    response = client.post(
        "/api/sql/analyze",
        json={
            "sql": """
set hive.exec.dynamic.partition=true;
add jar hdfs:///tmp/udf.jar;
create temporary function parse_json as 'com.demo.ParseJson';
insert overwrite table app.order_metric partition(dt='20260101')
select
  user_id,
  sum(order_amount) as gmv
from dwd_order_di
group by user_id;
""",
            "dialect": "spark",
        },
    )
    data = response.json()

    assert data["status"] == "success"
    assert data["analysis_sql"].lstrip().lower().startswith("select")
    assert data["capabilities"]["statement_clean"] is True
    assert data["capabilities"]["statement_count"] == 4
    assert data["capabilities"]["skipped_statement_count"] == 3
    assert data["capabilities"]["selected_statement_kind"] == "insert_source_query"
    assert any(
        attempt["target"].startswith("insert_source_0003:")
        for attempt in data["parse_attempts"]
    )
    diagnostic_codes = {diagnostic["code"] for diagnostic in data["diagnostics_report"]["diagnostics"]}
    assert "MULTI_STATEMENT_SCRIPT_DETECTED" in diagnostic_codes
    assert "ANALYSIS_STATEMENT_SELECTED" in diagnostic_codes
    assert "INSERT_TARGET_EXTRACTED" in diagnostic_codes


def test_feature_tagging_is_exposed_in_diagnostics_and_capabilities():
    response = client.post(
        "/api/sql/analyze",
        json={
            "sql": """
select
  m['k'] as `\u4e2d\u6587\u522b\u540d`,
  count(distinct user_id) as uv,
  case when score > 0 then 1 else 0 end as is_pos,
  get_json_object(ext, '$.a') as a
from t
group by 1, 2
""",
            "dialect": "spark",
        },
    )
    data = response.json()

    assert data["status"] in {"success", "partial"}
    assert data["capabilities"]["dialect_feature_tagging"] is True
    assert data["capabilities"]["dialect_features"]["map_access"] == 1
    assert data["capabilities"]["dialect_features"]["json_func"] == 1
    assert data["capabilities"]["dialect_features"]["group_by_ordinal"] == 1
    assert data["capabilities"]["dialect_features"]["count_distinct"] == 1
    assert data["capabilities"]["dialect_features"]["case_when"] == 1
    assert "group_by_ordinal" in data["capabilities"]["dialect_feature_risks"]
    assert "chinese_backtick_alias" in data["capabilities"]["dialect_feature_risks"]
    assert "group_by_ordinal" in data["unsupported_features"]
    assert "chinese_backtick_alias" in data["unsupported_features"]
    assert data["confidence"]["lineage"] <= 0.72
    diagnostic_codes = {diagnostic["code"] for diagnostic in data["diagnostics_report"]["diagnostics"]}
    assert "MAP_ACCESS_DETECTED" in diagnostic_codes
    assert "JSON_EXTRACTION_FUNCTION_DETECTED" in diagnostic_codes
    assert "GROUP_BY_ORDINAL_DETECTED" in diagnostic_codes
    assert "QUOTED_CHINESE_ALIAS_DETECTED" in diagnostic_codes
    assert "COUNT_DISTINCT_DETECTED" in diagnostic_codes
    assert "CASE_WHEN_DETECTED" in diagnostic_codes

