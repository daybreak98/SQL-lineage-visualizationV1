from app.complex_sql_guard.feature_tagger import detect_dialect_features


def test_detects_multiple_dialect_features():
    sql = """
select
  m['k'] as `\u4e2d\u6587\u522b\u540d`,
  count(distinct user_id) as uv,
  case when score > 0 then 1 else 0 end as is_pos,
  get_json_object(ext, '$.a') as a
from t
group by 1, 2
"""

    result = detect_dialect_features(sql)

    assert result.features["map_access"] == 1
    assert result.features["json_func"] == 1
    assert result.features["group_by_ordinal"] == 1
    assert result.features["chinese_backtick_alias"] == 1
    assert result.features["count_distinct"] == 1
    assert result.features["case_when"] == 1

    diagnostic_codes = {diagnostic.code for diagnostic in result.diagnostics}
    assert "MAP_ACCESS_DETECTED" in diagnostic_codes
    assert "JSON_EXTRACTION_FUNCTION_DETECTED" in diagnostic_codes
    assert "GROUP_BY_ORDINAL_DETECTED" in diagnostic_codes
    assert "QUOTED_CHINESE_ALIAS_DETECTED" in diagnostic_codes
    assert "COUNT_DISTINCT_DETECTED" in diagnostic_codes
    assert "CASE_WHEN_DETECTED" in diagnostic_codes
    assert result.risk_features == ["chinese_backtick_alias", "group_by_ordinal"]
    assert result.confidence_cap == 0.72
