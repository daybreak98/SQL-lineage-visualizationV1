from fastapi.testclient import TestClient

from app.main import app


def _analyze(sql, *, ports=None, dialect="spark"):
    payload = {"sql": sql, "dialect": dialect}
    if ports is not None:
        payload["protected_outputs"] = [
            {"statement": 1, "scope": scope, "slot": slot} for scope, slot in ports
        ]
    with TestClient(app) as client:
        response = client.post("/api/sql/subfield-lineage", json=payload)
    assert response.status_code == 200
    return response.json()


def test_comment_only_reports_no_analyzable_sql_without_changing_parse_flag():
    result = _analyze("-- SELECT get_json_object(p, '$.ignored')\n/* macro */",
                      dialect="hive")
    assert result["coverage"]["parsed"] is True
    assert result["coverage"]["analysis_status"] == "NO_ANALYZABLE_SQL"
    assert result["mappings"] == result["uses"] == result["unknowns"] == []

    separators = _analyze("/* comment */; -- trailing", ports=[("1:1", 1)])
    assert separators["coverage"]["analysis_status"] == "NO_ANALYZABLE_SQL"
    assert separators["review"]["path_demand_status"] == "NO_ANALYZABLE_SQL"
    assert separators["unknowns"] == []


def test_nested_extract_reports_unverified_path_and_preserves_read_evidence():
    sql = ("WITH raw AS (SELECT get_json_object(p,'$.mid') AS mid FROM src) "
           "SELECT get_json_object(r.mid,'$.x'){} FROM raw r")
    for alias in ("", " AS x"):
        result = _analyze(sql.format(alias), ports=[("1:2", 1)])
        [root] = [m for m in result["mappings"] if m["root"]]
        assert (root["statement"], root["scope"], root["slot"]) == (1, "1:2", 1)
        assert not result["review"]["unmatched_protected_outputs"]
        expected = "JSON_USE_OBSERVED" if alias else "ANALYSIS_INCOMPLETE"
        assert result["coverage"]["analysis_status"] == expected
        review = result["review"]
        assert review["path_demand_status"] == "ANALYSIS_INCOMPLETE"
        assert review["observed_path_demands"]["by_protected_output"] == []
        assert [use["path"] for use in result["uses"]] == ["$.mid", "$.mid::json.x"]
        assert result["unknowns"] == []


def test_bound_plain_projection_and_partial_binding_have_different_empty_results():
    plain = _analyze("SELECT s.p FROM src s", ports=[("1:1", 1)])
    assert plain["coverage"]["analysis_status"] == "NO_JSON_USE_IN_SCOPE"
    assert plain["review"]["path_demand_status"] == "NO_JSON_USE_IN_SCOPE"
    assert plain["review"]["findings"][0]["decision"] == "RETAIN_WHOLE"
    assert _analyze("SELECT 1", dialect="hive")["coverage"]["analysis_status"] == "NO_JSON_USE_IN_SCOPE"

    gap = _analyze("SELECT missing.p AS p FROM src s", ports=[("1:1", 1)])
    assert gap["coverage"]["analysis_status"] == "ANALYSIS_INCOMPLETE"
    assert gap["review"]["path_demand_status"] == "ANALYSIS_INCOMPLETE"
    assert [row["code"] for row in gap["unknowns"]] == ["UNBOUND_COLUMN"]

    opaque_json = _analyze("SELECT to_json(s.p) AS encoded FROM src s", ports=[("1:1", 1)])
    assert opaque_json["coverage"]["analysis_status"] == "ANALYSIS_INCOMPLETE"
    assert opaque_json["review"]["path_demand_status"] == "ANALYSIS_INCOMPLETE"
    assert opaque_json["unknowns"] == []


def test_unmatched_output_does_not_hide_another_outputs_verified_demand():
    sql = ("WITH b AS (SELECT t.j FROM src t) "
           "SELECT get_json_object(b.j, '$.a') AS a FROM b")
    assert _analyze(sql, ports=[("1:2", 1)])["review"]["path_demand_status"] == "OBSERVED"
    result = _analyze(sql, ports=[("1:2", 1), ("1:2", 2)])
    assert result["coverage"]["analysis_status"] == "JSON_USE_OBSERVED"
    assert result["review"]["path_demand_status"] == "ANALYSIS_INCOMPLETE"
    [entry] = result["review"]["observed_path_demands"]["by_protected_output"]
    assert entry["path_tokens"] == [{"kind": "key", "value": "a"}]
