"""Statement-level WITH and uncertain generator outputs retain local evidence."""

from app.services.subfield import analyze_subfields


def test_with_insert_keeps_cte_paths_and_distinct_fixed_map_occurrences():
    sql = """
CREATE TABLE lab.t (j STRING);
CREATE TABLE lab.out (x STRING);
WITH b AS (
    SELECT u.k, u.v, get_json_object(t.j, '$.x') AS x
    FROM lab.t t
    LATERAL VIEW OUTER explode(map(
        'a', get_json_object(t.j, '$.kind'),
        'b', get_json_object(t.j, '$.kind'))) u AS k, v
)
INSERT OVERWRITE TABLE lab.out SELECT b.x FROM b;
"""
    result = analyze_subfields(sql, "hive")

    [root] = [mapping for mapping in result["mappings"] if mapping["root"]]
    assert (root["statement"], root["target"], root["output"], root["kind"]) == (
        3, "lab.out", "x", "EXTRACT")
    assert [(item["source"], item["column"], item["path"]) for item in root["inputs"]] == [
        ("lab.t", "j", "$.x")]
    assert sql[root["position"]["start"]:root["position"]["end"]] == "x"

    [generator] = result["generators"]
    assert generator["input_semantics"] == "FIXED_MAP_CONSTRUCTION"
    assert generator["mode"] == "OUTER"
    assert [entry["constructed_key"] for entry in generator["entries"]] == ["a", "b"]
    assert all(entry["inputs"] == generator["entries"][0]["inputs"]
               for entry in generator["entries"])
    assert generator["entries"][0]["inputs"][0]["path"] == "$.kind"
    assert generator["entries"][0]["position"] != generator["entries"][1]["position"]
    extracts = [use for use in result["uses"]
                if use["clause"] == "LATERAL" and use["path"] == "$.kind"]
    assert len(extracts) == 2
    assert extracts[0]["position"] != extracts[1]["position"]
    assert all(use["statement"] == 3 for use in result["uses"])
    inputs = [item for mapping in result["mappings"] for item in mapping["inputs"]]
    assert {item["source"] for item in inputs} == {"lab.t"}
    assert not any(item["column"] == "*" for item in inputs)
    codes = {unknown["code"] for unknown in result["unknowns"]}
    assert {"UNSUPPORTED_STATEMENT", "GENERATOR_FUNCTION_BINDING_UNVERIFIED",
            "CROSS_STATEMENT_BINDING_UNVERIFIED"} <= codes
    assert not result["coverage"]["complete"]


def test_unknown_map_outputs_do_not_hide_group_path_or_alias_uncertainty():
    sql = """
SELECT nvl(x, 'UNKNOWN') AS x, v
FROM (
    SELECT get_json_object(t.j, '$.x') AS x, u.k, u.v
    FROM lab.t t
    LATERAL VIEW OUTER explode(opaque_map(t.j)) u AS k, v
) b
GROUP BY x, v
"""
    result = analyze_subfields(sql, "hive")

    [generator] = result["generators"]
    assert generator["input_semantics"] == "UNKNOWN"
    assert [output["column"] for output in generator["outputs"]] == ["k", "v"]
    assert len({output["id"] for output in generator["outputs"]}) == 2
    generated = [mapping for mapping in result["mappings"]
                 if mapping["scope"] == generator["scope"]]
    assert [(mapping["output"], mapping["kind"]) for mapping in generated] == [
        ("k", "UNKNOWN"), ("v", "UNKNOWN")]
    group_reads = [use for use in result["uses"]
                   if use["clause"] == "GROUP_BY" and use["path"] == "$.x"]
    assert group_reads
    assert all((use["source"], use["column"], use["role"]) == (
        "lab.t", "j", "RELATIONAL") for use in group_reads)
    assert all(use["binding_status"] == "INPUT_OR_OUTPUT_ALIAS_UNVERIFIED"
               for use in group_reads)
    assert any(unknown["code"] == "POSSIBLE_OUTPUT_ALIAS"
               and unknown["clause"] == "GROUP_BY" and unknown["expression"] == "x"
               for unknown in result["unknowns"])
    assert any(unknown["code"] == "UNKNOWN_EXPLODE_INPUT_SEMANTICS"
               for unknown in result["unknowns"])
    inputs = [item for mapping in result["mappings"] for item in mapping["inputs"]]
    assert {item["source"] for item in inputs} == {"lab.t"}
    assert not any(item["column"] == "*" for item in inputs)
    assert not result["coverage"]["complete"]
