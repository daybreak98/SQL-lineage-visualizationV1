from sqlglot import Dialect

from app.services.subfield import analyze_subfields
from app.services.subfield_branch_review import build_branch_review


def test_json_path_spans_keep_carrier_positions_and_reach_branch_review():
    sql = (
        "WITH base AS (SELECT t.j FROM src t), "
        "l AS (SELECT get_json_object(x.j,'$.a') AS a FROM base x), "
        "r AS (SELECT get_json_object(x.j,'$.b') AS b FROM base x) "
        "SELECT COALESCE(l.a,r.b) AS protected FROM l CROSS JOIN r"
    )
    facts = analyze_subfields(sql, "spark")
    mappings = {m["output"]: m for m in facts["mappings"]}
    expected = {"a": (69, 71, 76), "b": (128, 130, 135)}
    extract_reads = {}
    for branch, (carrier_start, start, end) in expected.items():
        [read] = mappings[branch]["port_reads"]
        assert read["kind"] == "EXTRACT"
        assert read["position"] == {
            "start": carrier_start, "end": carrier_start + 1,
            "line": 1, "column_end": carrier_start + 1,
        }
        assert sql[carrier_start:carrier_start + 1] == "j"
        assert read["json_path_position"] == {
            "start": start, "end": end, "line": 1, "column_end": end,
        }
        assert sql[start:end] == f"'$.{branch}'"
        extract_reads[branch] = read

    review = build_branch_review(facts, [mappings["protected"]])
    [entry] = review["by_protected_output"]
    assert entry["status"] == "OBSERVED" and entry["rowset_verified"] is False
    [source] = entry["by_source"]
    for slot, (branch, path) in enumerate(zip(("a", "b"), source["paths"], strict=True), 1):
        [reason] = path["reasons"]
        assert reason["argument_slot"] == slot
        assert path["path_tokens"] == [{"kind": "key", "value": branch}]
        [step] = [step for step in reason["port_reads"] if step["kind"] == "EXTRACT"]
        assert step["json_path_position"] == extract_reads[branch]["json_path_position"]
        assert step["position"] == extract_reads[branch]["position"]


def test_repeated_unicode_literals_use_original_codepoint_spans_and_one_tokenization(monkeypatch):
    column = "`j\u5217`"
    decoded_key = "\u952e\U0001f600.x"
    literal = f'''"$['{decoded_key}']"'''
    sql = (
        f"WITH base AS (SELECT t.{column}, {literal} AS marker FROM src t),\r\n"
        f" l AS (SELECT get_json_object(x.{column}, {literal}) AS a FROM base x),\r\n"
        f" r AS (SELECT get_json_object(x.{column}, {literal}) AS b, "
        f"get_json_object(x.{column}, x.marker) AS dynamic_path FROM base x)\r\n"
        "SELECT COALESCE(l.a,r.b) AS protected FROM l CROSS JOIN r"
    )
    tokenize = Dialect.tokenize
    source_tokenizations = 0

    def counted_tokenize(self, text, **kwargs):
        nonlocal source_tokenizations
        if text == sql:
            source_tokenizations += 1
        return tokenize(self, text, **kwargs)

    monkeypatch.setattr(Dialect, "tokenize", counted_tokenize)
    facts = analyze_subfields(sql, "hive")
    mappings = {m["output"]: m for m in facts["mappings"]}
    for branch, cte, line in (("a", " l AS (", 2), ("b", " r AS (", 3)):
        [read] = mappings[branch]["port_reads"]
        start = sql.index(literal, sql.index(cte))
        position = read["json_path_position"]
        assert position["start"] != len(sql[:position["start"]].encode("utf-16-le")) // 2
        assert position["start"] != len(sql[:position["start"]].encode("utf-8"))
        assert (position["start"], position["end"], position["line"]) == (start, start + len(literal), line)
        assert sql[position["start"]:position["end"]] == literal
        assert read["path_tokens"] == [{"kind": "key", "value": decoded_key}]
        carrier = read["position"]
        assert sql[carrier["start"]:carrier["end"]] == column

    assert not mappings["dynamic_path"].get("port_reads")
    assert source_tokenizations == 1
