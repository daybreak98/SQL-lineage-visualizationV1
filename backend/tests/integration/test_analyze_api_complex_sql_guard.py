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

