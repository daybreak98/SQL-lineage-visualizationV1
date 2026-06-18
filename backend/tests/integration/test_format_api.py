from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_format_sql_keeps_all_statements_in_multi_statement_input():
    response = client.post(
        "/api/sql/format",
        json={
            "sql": "select 1 as a; select 2 as b",
            "dialect": "spark",
        },
    )
    data = response.json()

    assert data["status"] == "success"
    assert data["formatted_sql"]
    assert "1 as a" in data["formatted_sql"]
    assert "2 as b" in data["formatted_sql"]
    assert data["formatted_sql"].count("select\n") == 2
    assert "SELECT" not in data["formatted_sql"]


def test_format_sql_keeps_keywords_lowercase_without_touching_string_literals():
    response = client.post(
        "/api/sql/format",
        json={
            "sql": "select 'SELECT' as label, count(*) as cnt from t group by 1",
            "dialect": "spark",
        },
    )
    data = response.json()

    assert data["status"] == "success"
    assert "'SELECT'" in data["formatted_sql"]
    assert "select\n" in data["formatted_sql"]
    assert "\nfrom t" in data["formatted_sql"]
    assert "count(*) as cnt" in data["formatted_sql"]
