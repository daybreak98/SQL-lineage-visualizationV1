from app.complex_sql_guard.parser_adapter import SqlglotParserAdapter
from app.domain import diagnostics_model as diag_codes


def test_parser_adapter_parse_error():
    result = SqlglotParserAdapter().parse("select from", "spark", "broken_sql")

    assert result.status.value == "failed"
    assert result.error_message
    assert {diagnostic.code for diagnostic in result.diagnostics} == {diag_codes.SQLGLOT_PARSE_ERROR}

