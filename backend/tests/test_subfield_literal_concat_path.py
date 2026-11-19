from app.api.subfield_controller import SubfieldRequest, analyze_subfield_lineage


def _analyze(sql, *, dialect="spark", scope="1:2"):
    return analyze_subfield_lineage(SubfieldRequest(
        sql=sql, dialect=dialect,
        protected_outputs=[{"statement": 1, "scope": scope, "slot": 1}],
    ))


def test_literal_spark_concat_matches_json_key_evidence_in_create_view():
    template = ("CREATE VIEW v AS WITH c AS (SELECT s.j FROM src s) "
                "SELECT get_json_object(c.j,{}) AS hit FROM c")
    literal = _analyze(template.format("'$.k'"))
    sql = template.format("CONCAT('$.','k')")
    folded = _analyze(sql)
    assert folded["unknowns"] == literal["unknowns"] == []
    [left] = [row for row in literal["uses"] if row["kind"] == "EXTRACT"]
    [right] = [row for row in folded["uses"] if row["kind"] == "EXTRACT"]
    for field in ("kind", "source", "column", "path", "path_tokens", "position"):
        assert left[field] == right[field]
    assert sql[right["position"]["start"]:right["position"]["end"]] == "get_json_object"
    assert "json_path_position" not in right

    [root] = [row for row in folded["mappings"] if row["root"]]
    [read] = root["port_reads"]
    assert "json_path_position" not in read
    for result in (literal, folded):
        assert result["review"]["path_demand_status"] == "OBSERVED"
        [demand] = result["review"]["observed_path_demands"]["by_protected_output"]
        assert (demand["source"], demand["column"], demand["path_tokens"]) == (
            "src", "j", [{"kind": "key", "value": "k"}],
        )


def test_runtime_concat_and_opaque_calls_remain_unknown_without_losing_other_facts():
    result = _analyze(
        "SELECT get_json_object(s.j,concat('$.',s.key)) AS dynamic_key, "
        "get_json_object(s.j,concat('$.',:key)) AS param_key, "
        "get_json_object(s.j,path_udf('$.','k')) AS opaque_key, "
        "get_json_object(s.j,concat('$.','k[*]')) AS wildcard, "
        "get_json_object(s.j,'$.known') AS known FROM src s", scope="1:1",
    )
    assert [row["code"] for row in result["unknowns"]] == [
        "UNSUPPORTED_JSON_PATH", "UNSUPPORTED_JSON_PATH", "UNSUPPORTED_JSON_PATH",
        "UNKNOWN_FUNCTION", "UNSUPPORTED_JSON_PATH",
    ]
    assert [row["kind"] for row in result["mappings"]] == ["UNKNOWN"] * 4 + ["EXTRACT"]
    assert any(row["column"] == "key" and row["kind"] == "WHOLE_RAW" for row in result["uses"])
    assert [row["path"] for row in result["uses"] if row["kind"] == "EXTRACT"] == ["$.known"]
    assert result["review"]["path_demand_status"] == "ANALYSIS_INCOMPLETE"


def test_literal_concat_is_not_assumed_for_other_dialects_or_function_registration():
    sql = "SELECT get_json_object(s.j,concat('$.','k')) AS hit FROM src s"
    for result in (
        _analyze(sql, dialect="hive", scope="1:1"),
        _analyze("CREATE TEMPORARY FUNCTION concat AS 'example.Custom'; " + sql, scope="2:1"),
    ):
        assert any(row["code"] == "UNSUPPORTED_JSON_PATH" for row in result["unknowns"])
        assert not any(row["kind"] == "EXTRACT" for row in result["uses"])
