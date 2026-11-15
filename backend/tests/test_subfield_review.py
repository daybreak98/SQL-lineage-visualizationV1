from app.services.subfield import analyze_subfields
from app.services import subfield_review


def test_review_retains_explicit_object_package_and_flags_unconfirmed_requests():
    sql = """
    SELECT s.object_json AS object_package, jt.color AS color
    FROM demo_messages s
    LATERAL VIEW json_tuple(s.extra_json, 'color', 'language') jt AS color, language
    WHERE get_json_object(s.context_json, '$.kind') = 'sample'
      AND private_predicate(s.context_json)
    """
    result = analyze_subfields(sql, "spark", source_schemas={
        "demo_messages": {"columns": ["object_json", "extra_json", "context_json"],
                          "complete": True, "version": "demo-v1", "evidence": "synthetic schema"}
    })
    root = next(m for m in result["mappings"] if m["root"] and m["output"] == "object_package")
    port = {field: root[field] for field in ("statement", "scope", "slot")}
    review = subfield_review.build_review(result, [port])
    retain, proof = review["findings"]
    assert retain["decision"] == "RETAIN_WHOLE"
    assert retain["protected_output"] == port
    assert [(p["source"], p["column"], p["path"]) for p in retain["evidence"]["inputs"]] == [
        ("demo_messages", "object_json", "$")
    ]
    assert proof["decision"] == "NEEDS_PROOF"
    assert proof["basis"] == "TUPLE_SYNTAX_REQUEST"
    assert proof["evidence"]["path"] == "$.language"
    assert proof["evidence"]["active"] is not True
    assert "protected_output" not in proof  # No proven link to the chosen output.
    assert any(u["role"] == "CONDITION" and u["path"] == "$.kind"
               for u in review["observed_control_uses"])
    assert review["unknowns"] == result["unknowns"]
    assert result["unknowns"]


def test_review_does_not_retain_a_cte_carrier_for_protected_extraction():
    result = analyze_subfields("""
        WITH carried AS (SELECT s.payload AS raw FROM src s)
        SELECT get_json_object(c.raw, '$.id') AS id FROM carried c
    """, "spark")
    carrier = next(m for m in result["mappings"] if m["output"] == "raw")
    assert not carrier["root"] and carrier["kind"] == "WHOLE_RAW"
    root = next(m for m in result["mappings"] if m["root"] and m["output"] == "id")
    assert root["kind"] == "EXTRACT"
    port = {field: root[field] for field in ("statement", "scope", "slot")}
    nonroot_port = {field: carrier[field] for field in ("statement", "scope", "slot")}
    review = subfield_review.build_review(result, [port, nonroot_port])
    assert review["findings"] == []
    assert review["unmatched_protected_outputs"] == [nonroot_port]
    unspecified = subfield_review.build_review(result, [])
    assert unspecified["status"] == "PROTECTED_OUTPUTS_UNSPECIFIED"
    assert unspecified["findings"] == []


def test_observed_demands_keep_selected_roots_and_actual_cte_ports():
    result = analyze_subfields("""
        WITH base AS (SELECT s.payload AS raw, s.payload AS twin FROM src s),
             carried AS (SELECT b.raw AS carry FROM base b)
        SELECT get_json_object(c.carry, '$.a') AS a,
               get_json_object(c.carry, '$.b') AS b FROM carried c
    """, "spark")
    mappings = {m["output"]: m for m in result["mappings"]}
    ports = {
        m["output"]: {field: m[field] for field in ("statement", "scope", "slot")}
        for m in mappings.values()
    }
    # A known origin in the flattened inputs does not prove a terminal binding.
    terminal = mappings["raw"].pop("terminal_binding", None)
    missing = subfield_review.build_review(result, [ports["a"]])["observed_path_demands"]
    assert missing["by_protected_output"] == missing["by_source"] == []
    assert terminal == "SQL_NAMED_RELATION_COLUMN"
    mappings["raw"]["terminal_binding"] = terminal

    both = subfield_review.build_review(result, [ports["a"], ports["b"]])["observed_path_demands"]
    assert [entry["protected_output"] for entry in both["by_protected_output"]] == [
        ports["a"], ports["b"]
    ]
    assert [(entry["source"], entry["column"]) for entry in both["by_source"]] == [
        ("src", "payload")
    ]
    assert [entry["path_tokens"] for entry in both["by_source"][0]["paths"]] == [
        [{"kind": "key", "value": "a"}], [{"kind": "key", "value": "b"}]
    ]
    for entry in both["by_protected_output"]:
        assert [edge["producer"] for edge in entry["port_reads"]] == [
            ports["carry"], ports["raw"]
        ]
        assert [edge["kind"] for edge in entry["port_reads"]] == ["EXTRACT", "PASSTHROUGH"]
        assert all(edge["position"] for edge in entry["port_reads"])
    one = subfield_review.build_review(result, [ports["a"]])["observed_path_demands"]
    assert one["by_protected_output"] == both["by_protected_output"][:1]
    assert one["by_source"][0]["paths"] == both["by_source"][0]["paths"][:1]

    # Break only the middle edge, leaving the root edge and flattened origin intact.
    assert mappings["carry"]["inputs"] and mappings["a"]["port_reads"]
    del mappings["carry"]["port_reads"]
    missing = subfield_review.build_review(result, [ports["a"]])["observed_path_demands"]
    assert missing["by_protected_output"] == missing["by_source"] == []


def test_candidate_review_requires_closed_selected_paths_and_blocks_whole_or_control():
    sql = """
        WITH base AS (SELECT s.payload AS raw FROM src s),
             carried AS (SELECT b.raw AS carry FROM base b)
        SELECT get_json_object(c.carry, '$.a.x') AS a, c.carry AS j FROM carried c
    """
    candidates = [{"source": "src", "column": "payload", "keys": ["b", "a", "A"]}]

    def assess(suffix="", selected=("a",), distinct=False):
        query = sql.replace("SELECT get_json_object", "SELECT DISTINCT get_json_object") if distinct else sql
        result = analyze_subfields(query + suffix, "spark")
        roots = {m["output"]: m for m in result["mappings"] if m["root"]}
        ports = [{field: roots[name][field] for field in ("statement", "scope", "slot")}
                 for name in selected]
        assert not result["unknowns"]
        return subfield_review.build_review(
            result, ports, candidate_keys=candidates,
        )["candidate_assessment"]

    assessment = assess()
    assert {entry["key"]: entry["status"] for entry in assessment["entries"]} == {
        "b": "NOT_OBSERVED_NEEDS_VALIDATION",
        "a": "OBSERVED",
        "A": "NOT_OBSERVED_NEEDS_VALIDATION",
    }
    for blocked, reason in (
        (assess(selected=("a", "j")), "PROTECTED_WHOLE_CARRIER"),
        (assess(" WHERE c.carry RLIKE 'token'"), "CONTROL_OR_STRUCTURAL_USE"),
        (assess(distinct=True), "PROJECTION_ONLY_NOT_VERIFIED"),
    ):
        assert blocked["status"] == "UNKNOWN"
        assert blocked["reason"] == reason and not blocked["entries"]
