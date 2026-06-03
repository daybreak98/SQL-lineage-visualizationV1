from app.services.sql_parse_service import parse_sql


def test_simple_select_a():
    result = parse_sql("select a from t")
    assert result.success is True
    assert result.status == "success"
    assert len(result.output_fields) == 1
    assert result.output_fields[0].name == "a"


def test_select_a_as_aa():
    result = parse_sql("select a as aa from t")
    assert result.success is True
    assert result.output_fields[0].name == "aa"
    assert result.output_fields[0].expression == "a"


def test_count_star_as_cnt():
    result = parse_sql("select count(*) as cnt from t")
    assert result.success is True
    assert result.output_fields[0].name == "cnt"
    assert result.output_fields[0].expression == "COUNT(*)"


def test_multiple_output_fields():
    result = parse_sql("select a, b, c from t")
    assert result.success is True
    assert len(result.output_fields) == 3
    assert [f.name for f in result.output_fields] == ["a", "b", "c"]


def test_source_type_unknown_for_simple_column():
    result = parse_sql("select a from t")
    assert result.output_fields[0].source_type == "unknown"


def test_source_type_expression_for_function():
    result = parse_sql("select count(*) as cnt from t")
    assert result.output_fields[0].source_type == "expression"


def test_source_type_expression_for_aliased_column():
    result = parse_sql("select a as aa from t")
    assert result.output_fields[0].source_type == "expression"


def test_parse_error_returns_failed():
    result = parse_sql("select from")
    assert result.success is False
    assert result.status == "failed"
    assert len(result.output_fields) == 0


def test_parse_error_has_diagnostic():
    result = parse_sql("select from")
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].code == "SQL_PARSE_ERROR"
    assert result.diagnostics[0].level == "error"


def test_stage_status_on_success():
    result = parse_sql("select a from t")
    stages = result.stage_statuses
    assert stages[0]["stage"] == "sql_parse"
    assert stages[0]["status"] == "success"


def test_stage_status_on_failure():
    result = parse_sql("select from")
    stages = result.stage_statuses
    assert stages[0]["stage"] == "sql_parse"
    assert stages[0]["status"] == "failed"
    assert "SQL_PARSE_ERROR" in stages[0]["diagnostic_codes"]
