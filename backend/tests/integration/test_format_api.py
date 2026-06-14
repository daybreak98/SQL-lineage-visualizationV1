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
    assert "1 AS a" in data["formatted_sql"]
    assert "2 AS b" in data["formatted_sql"]
    assert data["formatted_sql"].count("SELECT\n") == 2
