"""Hive macro literals bind per call without asserting UDF output semantics."""

from app.services.subfield import analyze_subfields


DEFINITION = (
    "CREATE TEMPORARY MACRO pick(doc STRING, path STRING) "
    "default.clean(get_json_object(doc, path));\n"
)


def test_two_string_macro_binds_each_literal_and_keeps_definition_call_evidence():
    sql = DEFINITION + "SELECT pick(t.j, '$.x') AS x, pick(t.j, '$.y') AS y FROM lab.t t"
    facts = analyze_subfields(sql, "hive")

    extracts = [u for u in facts["uses"] if u["kind"] == "EXTRACT"]
    assert len(extracts) == 2
    for key, read in zip(("x", "y"), extracts, strict=True):
        assert (read["source"], read["column"]) == ("lab.t", "j")
        assert read["path_tokens"] == [{"kind": "key", "value": key}]
        macro = read["macro"]
        assert macro["name"] == "pick"
        assert macro["definition"]["statement"] == 1
        definition_position = macro["definition"]["position"]
        assert sql[definition_position["start"]:definition_position["end"]].lower() == "get_json_object"
        assert macro["call"]["statement"] == 2
        call_position = macro["call"]["position"]
        assert sql[call_position["start"]:call_position["end"]].lower() == "pick"
        assert call_position["start"] == sql.index(f"pick(t.j, '$.{key}')")
        path_argument = macro["path_argument"]
        assert (path_argument["parameter_slot"], path_argument["statement"]) == (2, 2)
        path_position = path_argument["position"]
        assert sql[path_position["start"]:path_position["end"]] == f"'$.{key}'"

    assert {m["output"]: m["kind"] for m in facts["mappings"]} == {"x": "UNKNOWN", "y": "UNKNOWN"}
    unknowns = [u for u in facts["unknowns"] if u["code"] == "UNKNOWN_FUNCTION"]
    assert len(unknowns) == 2
    assert all(u["macro"]["name"] == "pick" for u in unknowns)
    assert all("CLEAN(" in u["expression"] for u in unknowns)


def test_dynamic_paths_and_declaration_boundaries_never_guess_builtin_extracts():
    dynamic = analyze_subfields(
        DEFINITION + "SELECT pick(t.j, t.p) AS out FROM lab.t t", "hive"
    )
    assert not any(u["kind"] == "EXTRACT" for u in dynamic["uses"])
    assert {u["column"] for u in dynamic["uses"] if u["source"] == "lab.t"} == {"j", "p"}
    assert dynamic["mappings"][0]["kind"] == "UNKNOWN"
    assert {i["column"] for i in dynamic["mappings"][0]["inputs"]} == {"j", "p"}
    assert dynamic["unknowns"]

    for prefix in (
        DEFINITION + DEFINITION,
        "CREATE TEMPORARY FUNCTION get_json_object AS 'example.CustomJson';\n" + DEFINITION,
    ):
        facts = analyze_subfields(prefix + "SELECT pick(t.j, '$.x') AS out FROM lab.t t", "hive")
        assert not any(u["kind"] == "EXTRACT" for u in facts["uses"])
        assert facts["mappings"][0]["kind"] == "UNKNOWN"
        assert facts["unknowns"]
