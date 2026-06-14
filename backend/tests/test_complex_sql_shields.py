from app.complex_sql_guard.shields import DirtySqlPreprocessor
from app.domain import diagnostics_model as diag_codes


def test_literal_shield_regex():
    sql = "select regexp_extract(url, '^[^?]+', 0) as path from t"
    bundle, diagnostics = DirtySqlPreprocessor().preprocess(sql)

    assert "__SQLG_REGEX_" in bundle.analysis_sql
    assert any(placeholder.kind == "regex_literal" for placeholder in bundle.placeholders)
    assert diag_codes.REGEX_LITERAL_SHIELD_APPLIED in {diagnostic.code for diagnostic in diagnostics}


def test_literal_shield_json_path():
    sql = "select get_json_object(data, '$.refundRecords[*].amount') as amount from t"
    bundle, diagnostics = DirtySqlPreprocessor().preprocess(sql)

    assert "__SQLG_JSON_" in bundle.analysis_sql
    assert any(placeholder.kind == "json_path_literal" for placeholder in bundle.placeholders)
    assert diag_codes.JSON_PATH_LITERAL_SHIELD_APPLIED in {diagnostic.code for diagnostic in diagnostics}


def test_template_shield_zdt():
    sql = 'select * from t where dt = ${zdt.addDay(-1).format("yyyyMMdd")}'
    bundle, diagnostics = DirtySqlPreprocessor().preprocess(sql)

    assert "__SQLG_TPL_" in bundle.analysis_sql
    assert any(placeholder.kind == "template" for placeholder in bundle.placeholders)
    assert diag_codes.TEMPLATE_SQL_DETECTED in {diagnostic.code for diagnostic in diagnostics}


def test_freemarker_block_shield():
    sql = "select * from t <#if test> where dt = '20260101' </#if>"
    bundle, diagnostics = DirtySqlPreprocessor().preprocess(sql)

    assert "__SQLG_FTL_" not in bundle.analysis_sql
    assert sum(1 for placeholder in bundle.placeholders if placeholder.kind == "freemarker_block") == 2
    assert diag_codes.FREEMARKER_BLOCK_DETECTED in {diagnostic.code for diagnostic in diagnostics}

