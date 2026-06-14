from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_convert_sql_returns_converted_payload():
    response = client.post(
        "/api/sql/convert",
        json={
            "sql": "select `user_id` from t",
            "source_dialect": "hive",
            "target_dialect": "spark",
            "pretty": True,
        },
    )
    data = response.json()

    assert data["status"] == "success"
    assert data["source_dialect"] == "hive"
    assert data["target_dialect"] == "spark"
    assert data["converted_sql"]
    assert isinstance(data["elapsed_ms"], int)
    assert data["diagnostics"] == []


def test_convert_sql_formats_without_uppercasing_keywords():
    sql = "select user_id, count(distinct order_no) as order_cnt from dwd_order_di group by user_id"
    response = client.post(
        "/api/sql/convert",
        json={
            "sql": sql,
            "source_dialect": "spark",
            "target_dialect": "hive",
            "pretty": True,
        },
    )
    data = response.json()

    assert data["status"] == "success"
    assert data["converted_sql"].startswith("select\n")
    assert "count(distinct order_no) as order_cnt" in data["converted_sql"]
    assert "\nfrom dwd_order_di" in data["converted_sql"]
    assert "\ngroup by\n" in data["converted_sql"]
    assert "SELECT" not in data["converted_sql"]


def test_convert_sql_preserves_keyword_case_around_substantive_rewrite():
    response = client.post(
        "/api/sql/convert",
        json={
            "sql": "select from_unixtime(ts, 'yyyy-MM-dd') as dt from t",
            "source_dialect": "hive",
            "target_dialect": "starrocks",
            "pretty": True,
        },
    )
    data = response.json()

    assert data["status"] == "success"
    assert data["converted_sql"].startswith("select\n")
    assert " as dt" in data["converted_sql"]
    assert "\nfrom t" in data["converted_sql"]
    assert "%Y-%m-%d" in data["converted_sql"]


def test_convert_sql_accepts_sr_alias():
    response = client.post(
        "/api/sql/convert",
        json={
            "sql": "select 1",
            "source_dialect": "sr",
            "target_dialect": "hive",
            "pretty": True,
        },
    )
    data = response.json()

    assert data["status"] == "success"
    assert data["source_dialect"] == "starrocks"
    assert data["target_dialect"] == "hive"


def test_convert_sql_rejects_unsupported_dialect_without_silent_fallback():
    response = client.post(
        "/api/sql/convert",
        json={
            "sql": "select 1",
            "source_dialect": "mysql",
            "target_dialect": "hive",
            "pretty": True,
        },
    )
    data = response.json()

    assert data["status"] == "failed"
    assert data["source_dialect"] == "mysql"
    assert data["target_dialect"] == "hive"
    assert data["converted_sql"] is None
    assert [diagnostic["code"] for diagnostic in data["diagnostics"]] == ["UNSUPPORTED_DIALECT"]


def test_convert_sql_marks_risky_passthrough_functions_partial():
    response = client.post(
        "/api/sql/convert",
        json={
            "sql": "select bitmap_count(to_bitmap(user_id)) as uv from dwd_order_di",
            "source_dialect": "starrocks",
            "target_dialect": "hive",
            "pretty": True,
        },
    )
    data = response.json()

    assert data["status"] == "partial"
    assert data["converted_sql"]
    assert "FUNCTION_PASSTHROUGH" in {diagnostic["code"] for diagnostic in data["diagnostics"]}


def test_convert_sql_reports_risky_source_function_line_number():
    response = client.post(
        "/api/sql/convert",
        json={
            "sql": "\n".join(
                [
                    "select",
                    "  user_id,",
                    "  bitmap_count(to_bitmap(user_id)) as uv",
                    "from dwd_order_di",
                ]
            ),
            "source_dialect": "starrocks",
            "target_dialect": "hive",
            "pretty": True,
        },
    )
    data = response.json()

    risky = [diagnostic for diagnostic in data["diagnostics"] if diagnostic["code"] == "FUNCTION_CONVERSION_UNCERTAIN"]
    assert data["status"] == "partial"
    assert risky
    assert risky[0]["location"]["line"] == 3
    assert risky[0]["extra"]["function"] == "bitmap_count"


def test_convert_sql_keeps_all_statements_in_multi_statement_input():
    response = client.post(
        "/api/sql/convert",
        json={
            "sql": "select 1 as a; select 2 as b",
            "source_dialect": "spark",
            "target_dialect": "hive",
            "pretty": True,
        },
    )
    data = response.json()

    assert data["status"] == "success"
    assert data["converted_sql"]
    assert "select\n  1 as a" in data["converted_sql"]
    assert "select\n  2 as b" in data["converted_sql"]
    assert data["converted_sql"].count("select\n") == 2
