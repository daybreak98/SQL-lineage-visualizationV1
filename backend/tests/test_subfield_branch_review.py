from copy import deepcopy

from app.services.subfield import analyze_subfields
from app.services.subfield_branch_review import build_branch_review


THREE_ARGS = """
WITH base AS (SELECT t.j FROM src t),
     l AS (SELECT get_json_object(x.j, '$.a') AS a FROM base x),
     r AS (SELECT get_json_object(x.j, '$.b') AS b FROM base x)
SELECT COALESCE(l.a, l.a, r.b) AS protected FROM l CROSS JOIN r
"""


def test_three_arguments_keep_repeated_producer_reasons_and_controller_dispatch():
    from app.api.subfield_controller import SubfieldRequest, analyze_subfield_lineage

    facts = analyze_subfields(THREE_ARGS, "spark")
    root = next(m for m in facts["mappings"] if m["root"])
    assert root["port_model"] == "COALESCE_N" and root["argument_count"] == 3
    reads = root["port_reads"]
    assert [r["argument_slot"] for r in reads] == [1, 2, 3]
    assert reads[0]["producer"] == reads[1]["producer"]
    assert reads[0]["position"] != reads[1]["position"]
    protected = {k: root[k] for k in ("statement", "scope", "slot")}
    response = analyze_subfield_lineage(SubfieldRequest(
        sql=THREE_ARGS, protected_outputs=[protected],
        candidate_keys=[{"source": "src", "column": "j", "keys": ["a", "b"]}]))
    report = response["review"]["observed_branch_demands"]
    [entry] = report["by_protected_output"]
    assert entry["status"] == "OBSERVED" and entry["argument_count"] == 3
    assert report["rowset_verified"] is entry["rowset_verified"] is False
    [source] = entry["by_source"]
    assert [(p["path_tokens"], [r["argument_slot"] for r in p["reasons"]])
            for p in source["paths"]] == [
        ([{"kind": "key", "value": "a"}], [1, 2]),
        ([{"kind": "key", "value": "b"}], [3]),
    ]
    assert response["review"]["candidate_assessment"]["status"] == "UNKNOWN"
    assert not response["review"]["candidate_assessment"]["entries"]


def test_missing_last_argument_uses_ast_count_not_remaining_edge_count():
    facts = analyze_subfields(THREE_ARGS, "spark")
    root = next(m for m in facts["mappings"] if m["root"])
    assert root["argument_count"] == 3
    root["port_reads"] = root["port_reads"][:2]
    assert root["inputs"]  # Flat provenance must not repair the missing edge.
    [entry] = build_branch_review(facts, [root])["by_protected_output"]
    assert entry["status"] == "UNRESOLVED" and entry["argument_count"] == 3
    assert entry["rowset_verified"] is False
    assert any(g["reason"] == "MISSING_OR_AMBIGUOUS_ARGUMENT" and g["argument_slot"] == 3
               for g in entry["unresolved"])
    [source] = entry["by_source"]
    [path] = source["paths"]
    assert path["path_tokens"] == [{"kind": "key", "value": "a"}]
    assert [r["argument_slot"] for r in path["reasons"]] == [1, 2]


def test_coalesce_merges_both_demands_and_keeps_evidence_when_one_edge_is_missing():
    result = analyze_subfields("""
        WITH base AS (SELECT t.j FROM src t),
             l AS (SELECT get_json_object(x.j, '$.a') AS a FROM base x),
             r AS (SELECT get_json_object(x.j, '$.b') AS b FROM base x)
        SELECT COALESCE(l.a, r.b) AS protected FROM l CROSS JOIN r
    """, "spark")
    root = next(mapping for mapping in result["mappings"] if mapping["root"])
    protected = {key: root[key] for key in ("statement", "scope", "slot")}

    def report(facts):
        review = build_branch_review(facts, [protected])
        entry, = review["by_protected_output"]
        assert review["rowset_verified"] is entry["rowset_verified"] is False
        return entry

    def source_paths(review):
        source, = review["by_source"]
        assert (source["source"], source["column"]) == ("src", "j")
        return [(path["path_tokens"], [reason["argument_slot"] for reason in path["reasons"]])
                for path in source["paths"]]

    observed = report(result)
    assert observed["status"] == "OBSERVED"
    assert source_paths(observed) == [
        ([{"kind": "key", "value": "a"}], [1]),
        ([{"kind": "key", "value": "b"}], [2]),
    ]

    broken = deepcopy(result)
    left = next(mapping for mapping in broken["mappings"] if mapping["output"] == "a")
    assert left["inputs"]  # Flat provenance is still present.
    del left["port_reads"]
    unresolved = report(broken)
    assert unresolved["status"] == "UNRESOLVED"
    assert source_paths(unresolved) == [([{"kind": "key", "value": "b"}], [2])]
