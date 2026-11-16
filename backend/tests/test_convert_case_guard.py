import pytest

from app.api.format_controller import convert_sql
from app.models import ConvertSqlRequest


@pytest.mark.parametrize("sql, expected", [
    ("select 'SELECT' as label from t", "select\n  'SELECT' as label\nfrom t"),
    ("select 'SAFE' as `SELECT` from t /* SELECT */",
     "select\n  'SAFE' as `SELECT`\nfrom t /* SELECT */"),
])
def test_pretty_conversion_only_changes_code_word_case(sql, expected):
    result = convert_sql(ConvertSqlRequest(
        sql=sql, source_dialect="spark", target_dialect="hive", pretty=True,
    ))
    assert result.status == "success"
    assert result.converted_sql == expected


@pytest.mark.parametrize("parameter", ["COUNT", "customer_id"])
def test_pretty_conversion_preserves_named_parameter_identity(parameter):
    import sqlglot
    from sqlglot import exp

    result = convert_sql(ConvertSqlRequest(
        sql=f"SELECT :{parameter} AS value",
        source_dialect="spark", target_dialect="hive", pretty=True,
    ))
    assert result.status == "success"
    assert result.converted_sql == f"select\n  :{parameter} as value"
    converted = sqlglot.parse_one(result.converted_sql, read="hive")
    assert [node.name for node in converted.find_all(exp.Placeholder)] == [parameter]
