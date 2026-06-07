from app.complex_sql_guard import analyze_complex_sql
from app.domain import diagnostics_model as diag_codes


def test_analyzer_partial_result():
    sql = """
    with a as (select id from t1),
    broken as (select from),
    c as (select id from t2)
    select a.id
    from a
    join c on a.id = c.id
    """

    result = analyze_complex_sql(sql, "spark")
    diagnostic_codes = {diagnostic.code for diagnostic in result.diagnostics}

    assert result.status.value == "partial"
    assert diag_codes.SEGMENT_PARSE_FALLBACK in diagnostic_codes
    assert diag_codes.PARTIAL_PARSE_RESULT in diagnostic_codes
    assert result.capabilities["segment_parse"] is True
    assert any(segment.segment_type == "cte_item" and segment.parse_status.value == "success" for segment in result.segments)


def test_preflight_error_downgrades_successful_parse_to_partial():
    result = analyze_complex_sql(
        "select a from t",
        "spark",
        options={"max_sql_chars": 5},
    )
    diagnostic_codes = {diagnostic.code for diagnostic in result.diagnostics}

    assert result.status.value == "partial"
    assert diag_codes.ANALYSIS_TIMEOUT in diagnostic_codes
    assert diag_codes.LOW_CONFIDENCE_LINEAGE in diagnostic_codes
    assert result.confidence["parse"] <= 0.6
    assert result.confidence["lineage"] <= 0.35

