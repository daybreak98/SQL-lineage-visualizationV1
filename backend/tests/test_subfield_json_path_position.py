import sqlglot
from sqlglot import Dialect

from app.api.subfield_controller import SubfieldRequest, analyze_subfield_lineage
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


SQL_A = (
    "SELECT get_json_object(e.payload, '$.item_id') AS item_id,\n"
    "       get_json_object(e.payload, '$.shop_id') AS shop_id\n"
    "FROM demo.events e"
)


def _request(sql):
    return analyze_subfield_lineage(SubfieldRequest(
        sql=sql,
        protected_outputs=[{"statement": 1, "scope": "1:2", "slot": 1}],
        candidate_keys=[{"source": "demo.events", "column": "payload", "keys": ["item_id", "absent"]}],
    ))


def _position(start, end, line, column_end):
    return {"start": start, "end": end, "line": line, "column_end": column_end}


def test_static_extract_uses_expose_literal_spans_and_keep_review_semantics():
    result = _request(SQL_A)
    item, shop = result["uses"]
    for use, key, fn_span, path_span in (
        (item, "item_id", _position(7, 22, 1, 22), _position(34, 45, 1, 45)),
        (shop, "shop_id", _position(66, 81, 2, 22), _position(93, 104, 2, 45)),
    ):
        assert use["kind"] == "EXTRACT"
        assert use["path_tokens"] == [{"kind": "key", "value": key}]
        assert use["position"] == fn_span
        assert use["json_path_position"] == path_span
        assert SQL_A[path_span["start"]:path_span["end"]] == f"'$.{key}'"
    assert result["review"]["candidate_assessment"] == {
        "status": "UNKNOWN", "reason": "PROTECTED_PATH_UNVERIFIED", "entries": [],
    }


def test_static_extract_uses_keep_distinct_spans_for_repeated_literals_and_ignore_comments():
    sql = (
        "/* \U0001F600 '$.item_id' */\r\n"
        "WITH src AS (SELECT e.payload AS j FROM demo.events e)\r\n"
        "SELECT get_json_object(s.j, /* '$.item_id' */ '$.item_id') AS item_id,\r\n"
        "       get_json_object(s.j, '$.item_id') AS again FROM src s"
    )
    result = _request(sql)
    raw, item, again = result["uses"]
    assert raw["kind"] == "WHOLE_RAW" and "json_path_position" not in raw
    mappings = {m["output"]: m for m in result["mappings"]}
    for use, output, fn_span, path_span in (
        (item, "item_id", _position(84, 99, 3, 22), _position(123, 134, 3, 57)),
        (again, "again", _position(156, 171, 4, 22), _position(177, 188, 4, 39)),
    ):
        assert use["kind"] == "EXTRACT"
        assert use["position"] == fn_span
        assert use["json_path_position"] == path_span
        assert sql[path_span["start"]:path_span["end"]] == "'$.item_id'"
        [read] = mappings[output]["port_reads"]
        assert read["json_path_position"] == path_span
    assessments = result["review"]["candidate_assessment"]["entries"]
    assert [(entry["key"], entry["status"]) for entry in assessments] == [
        ("item_id", "OBSERVED"), ("absent", "NOT_OBSERVED_NEEDS_VALIDATION"),
    ]


def test_unverified_literal_position_keeps_function_span(monkeypatch):
    monkeypatch.setattr(sqlglot, "__version__", "unverified")
    item, shop = _request(SQL_A)["uses"]
    assert item["position"] == _position(7, 22, 1, 22)
    assert shop["position"] == _position(66, 81, 2, 22)
    for use in (item, shop):
        assert use["kind"] == "EXTRACT"
        assert "json_path_position" not in use
