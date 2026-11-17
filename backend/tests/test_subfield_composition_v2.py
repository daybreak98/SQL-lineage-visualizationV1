"""Composition uses structural slots, never flattened origin similarity."""
from app.services.subfield_composition import build_snapshot, compose_demands


def test_closed_cte_value_and_where_demand_are_both_preserved():
    snap = build_snapshot("WITH b AS (SELECT t.j FROM src t) SELECT "
        "get_json_object(b.j,'$.a') AS out FROM b WHERE get_json_object(b.j,'$.b') IS NOT NULL", "one")
    root = next(p for p in snap["ports"] if p["root"])
    result = compose_demands([snap], [], [{"port": root["port"], "demand": {"kind": "WHOLE_VALUE"}}])
    paths = {tuple(t["value"] for t in d.get("path_tokens", [])) for d in result["source_demands"]}
    assert ("a",) in paths and ("b",) in paths
    assert result["status"] == "REVIEW_ONLY" and result["rowset_verified"] is False


def test_union_slots_and_unknown_function_never_become_identity():
    snap = build_snapshot("SELECT get_json_object(t.j,'$.a') AS same FROM src t UNION ALL "
                          "SELECT mystery(get_json_object(t.j,'$.b')) AS same FROM src t", "two")
    root = next(p for p in snap["ports"] if p["root"])
    result = compose_demands([snap], [], [{"port": root["port"], "demand": {"kind": "WHOLE_VALUE"}}])
    assert len(result["source_demands"]) >= 2
    assert any(u["code"] == "UNKNOWN_FUNCTION_SEMANTICS" for u in result["unknowns"])
    assert {p["port"]["scope"] for p in snap["ports"] if p["output"] == "same"} >= {"1:1", "1:2"}


def test_full_output_contract_contains_whole_carrier():
    snap = build_snapshot("SELECT get_json_object(t.j,'$.a') AS a, t.j FROM src t", "all")
    roots = [p for p in snap["ports"] if p["root"]]
    small = compose_demands([snap], [], [{"port": roots[0]["port"], "demand": {"kind": "WHOLE_VALUE"}}])
    full = compose_demands([snap], [], [{"port": p["port"], "demand": {"kind": "WHOLE_VALUE"}} for p in roots])
    assert not any(d["kind"] == "WHOLE_VALUE" for d in small["source_demands"])
    assert any(d["kind"] == "WHOLE_VALUE" for d in full["source_demands"])


def test_explicit_link_cycle_and_multiple_writers_do_not_disappear():
    snap = build_snapshot("SELECT t.j FROM src t", "cycle")
    root = snap["ports"][0]["port"]
    source = snap["relations"][0]["source"]
    link = {"consumer_source": source, "producer_port": root,
            "binding_status": "EXPLICIT_VIRTUAL_SLOT", "evidence": {"reason": "test"},
            "partition": {"dt": "same"}}
    result = compose_demands([snap], [link], [{"port": root, "demand": {"kind": "WHOLE_VALUE"}}])
    assert any(u["code"] == "CYCLE_BOUNDARY" for u in result["unknowns"])
    result = compose_demands([snap], [link, dict(link)], [{"port": root, "demand": {"kind": "WHOLE_VALUE"}}])
    assert any(u["code"] == "MULTIPLE_WRITERS" for u in result["unknowns"])


def test_wrong_database_qualifier_is_not_bound_to_other_table():
    snap = build_snapshot("SELECT other_db.t.j AS j FROM this_db.t", "qualified")
    assert not any("source" in e and e["source"].get("column") == "j" for e in snap["relations"])
    assert any(u["code"] == "COLUMN_BINDING_UNVERIFIED" for u in snap["unknowns"])


def test_count_star_keeps_row_source_without_inventing_value_columns():
    snap = build_snapshot("SELECT COUNT(*) AS n FROM src t", "count")
    root = next(p for p in snap["ports"] if p["root"])
    assert root["constant"] is False
    result = compose_demands([snap], [], [{"port": root["port"], "demand": {"kind": "WHOLE_VALUE"}}])
    assert any(d["kind"] == "ROW_SET" and d["source"]["relation"] == "src" for d in result["source_demands"])
    assert not any(d["source"].get("column") for d in result["source_demands"])


def test_cast_is_not_a_path_identity_contract():
    snap = build_snapshot("SELECT CAST(t.j AS STRING) AS out FROM src t", "cast")
    root = next(p for p in snap["ports"] if p["root"])
    result = compose_demands([snap], [], [{"port": root["port"], "demand": {
        "kind": "VALUE_PATH", "path_tokens": [{"kind": "key", "value": "a"}]}}])
    value = next(d for d in result["source_demands"] if d["source"].get("column") == "j")
    assert value["kind"] == "UNKNOWN" and value["reason"] == "TRANSFORM_SEMANTICS_UNVERIFIED"


def test_lateral_declares_slots_with_unverified_semantics():
    snap = build_snapshot("SELECT u.k,u.v FROM src t LATERAL VIEW OUTER "
                          "explode(map('a',get_json_object(t.j,'$.x'))) u AS k,v", "lateral")
    assert any(u["code"] == "GENERATOR_SEMANTICS_UNVERIFIED" for u in snap["unknowns"])
    assert [(p["port"]["slot"], p["output"]) for p in snap["ports"] if "generator_id" in p] == [(1, "k"), (2, "v")]
    assert any(u["code"] == "GENERATOR_FUNCTION_BINDING_UNVERIFIED" for u in snap["unknowns"])


def test_window_keeps_partition_order_evidence_and_unknown_semantics():
    sql = "SELECT ROW_NUMBER() OVER (PARTITION BY t.j ORDER BY t.k) AS rn FROM src t"
    snap = build_snapshot(sql, "window", "spark")
    root = next(p for p in snap["ports"] if p["root"])
    result = compose_demands([snap], [], [{"port": root["port"], "demand": {"kind": "WHOLE_VALUE"}}])
    assert any(u["code"] == "WINDOW_SEMANTICS_UNVERIFIED" for u in result["unknowns"])
    assert result["observed_windows"]
    values = [d for d in result["source_demands"] if d["source"].get("column")]
    assert {d["source"]["column"] for d in values} == {"j", "k"}
    assert all(d["kind"] == "UNKNOWN" for d in values)
    for edge in snap["row_relations"]:
        if edge["clause"] == "WINDOW":
            pos = edge["evidence"]["position"]
            assert sql[pos["start"]:pos["end"]] in {"j", "k"}
    assert {e["source"]["column"] for e in snap["row_relations"] if e["clause"] == "WINDOW"} == {"j", "k"}


def test_qualify_preserves_condition_and_marks_rowset_unverified():
    sql = "SELECT t.j FROM src t QUALIFY t.j > 0"
    snap = build_snapshot(sql, "qualify", "spark")
    assert any(u["code"] == "ROWSET_EQUIVALENCE_UNVERIFIED" for u in snap["unknowns"])
    edge, = [e for e in snap["row_relations"] if e["clause"] == "QUALIFY"]
    pos = edge["evidence"]["position"]
    assert sql[pos["start"]:pos["end"]] == "j" and edge["role"] == "ROWSET"


def test_same_named_generator_slots_keep_their_own_inputs():
    sql = ("SELECT left_tuple.pg AS left_pg, right_tuple.pg AS right_pg FROM src t "
           "LATERAL VIEW json_tuple(t.left_doc, 'pg') left_tuple AS pg "
           "LATERAL VIEW json_tuple(t.right_doc, 'pg') right_tuple AS pg")
    snap = build_snapshot(sql, "tuple_slots")
    roots = [p["port"] for p in snap["ports"] if p["root"]]
    generators = []
    for root, expected in zip(roots, ("left_doc", "right_doc"), strict=True):
        result = compose_demands([snap], [], [{"port": root}])
        demand, = [d for d in result["source_demands"] if d["source"]["column"] is not None]
        assert demand["source"]["column"] == expected and demand["role"] == "STRUCTURE"
        edge, = [edge for edge in demand["witness"] if edge["clause"] == "GENERATOR_INPUT"]
        generators.append(edge["operations"][-1]["generator_id"])
        assert edge["consumer"]["slot"] == 1
        pos = edge["evidence"]["position"]
        assert sql[pos["start"]:pos["end"]] == expected
    assert len(set(generators)) == 2


def test_generator_key_after_decode_is_not_a_raw_json_path():
    sql = ("SELECT parsed.pg FROM src t LATERAL VIEW "
           "json_tuple(reflect('java.net.URLDecoder', 'decode', "
           "get_json_object(t.payload, '$.encoded'), 'UTF-8'), 'pg') parsed AS pg")
    snap = build_snapshot(sql, "opaque_tuple")
    root, = [p["port"] for p in snap["ports"] if p["root"]]
    result = compose_demands([snap], [], [{"port": root, "demand": {
        "kind": "VALUE_PATH", "path_tokens": [{"kind": "key", "value": "child"}]}}])
    demand, = [d for d in result["source_demands"] if d["source"]["column"] == "payload"]
    assert demand["kind"] == "UNKNOWN" and demand["role"] == "STRUCTURE"
    assert not demand.get("path_tokens")
    edge, = [edge for edge in demand["witness"] if edge["clause"] == "GENERATOR_INPUT"]
    assert any("java.net.URLDecoder" in op.get("expression", "") for op in edge["operations"])
    assert edge["operations"][-1]["output"]["key"] == "pg"


def test_with_insert_uses_primary_scope_and_cte_producer():
    sql = 'WITH b AS (SELECT t.j FROM src t) INSERT OVERWRITE TABLE out SELECT b.j FROM b'
    snap = build_snapshot(sql, 'with_insert')
    root, = snap['writes'][0]['root_ports']
    assert root['statement'] == 1 and root['scope'] == '1:2' and root['slot'] == 1
    result = compose_demands([snap], [], [{'port': root}])
    value, = [d for d in result['source_demands'] if d['source'].get('column') == 'j']
    assert value['source']['relation'] == 'src'
    assert value['witness'][0]['producer']['scope'] == '1:1'
    assert not any(d['source']['relation'] == 'b' for d in result['source_demands'])


def test_select_case_controls_value_without_becoming_where_or_a_source():
    sql = ("WITH b AS (SELECT t.flag, t.j, t.keep FROM src t) "
           "SELECT CASE WHEN b.flag = 1 THEN get_json_object(b.j,'$.x') "
           "WHEN b.flag = 2 THEN private_udf(get_json_object(b.j,'$.y')) "
           "ELSE NULL END AS picked FROM b WHERE b.keep = 1")
    snap = build_snapshot(sql, "ordered_case")
    root, = [p["port"] for p in snap["ports"] if p["root"]]
    result = compose_demands([snap], [], [{"port": root, "demand": {
        "kind": "VALUE_PATH", "path_tokens": [{"kind": "key", "value": "downstream"}]}}])
    demands = [d for d in result["source_demands"] if d["source"]["column"] is not None]
    controls = [d for d in demands if d["source"]["column"] == "flag"]
    assert len(controls) == 2 and all(d["role"] == "CONDITION" for d in controls)
    assert all(not d.get("path_tokens") for d in controls)
    assert [d["witness"][0]["evidence"]["case_parts"][0]["arm_slot"] for d in controls] == [1, 2]
    assert all(d["witness"][0]["producer"]["slot"] == 1 for d in controls)
    where, = [d for d in demands if d["role"] == "ROWSET"]
    assert where["source"]["column"] == "keep" and where["witness"][0]["clause"] == "WHERE"
    values = [d for d in demands if d["role"] == "VALUE"]
    assert [(d["source"]["column"], d["path_tokens"][0]["value"]) for d in values] == [("j", "x"), ("j", "y")]
    assert values[1]["kind"] == "UNKNOWN"
    case, = result["observed_cases"]
    assert [arm["kind"] for arm in case["arms"]] == ["WHEN", "WHEN", "ELSE"]
    assert case["arms"][-1]["value"]["expression"] == "NULL"
    assert not case["arms"][-1]["value"]["bindings"]


def test_regex_where_records_whole_input_and_explicit_capture_without_json_path():
    sql = ("SELECT t.id FROM src t WHERE "
           "regexp_extract(t.payload, 'request_batch:(.*)', 1) = '2'")
    snap = build_snapshot(sql, "regex_where")
    root, = [p["port"] for p in snap["ports"] if p["root"]]
    result = compose_demands([snap], [], [{"port": root}])
    demand, = [d for d in result["source_demands"] if d["source"]["column"] == "payload"]
    edge, = demand["witness"]
    op, = edge["operations"]
    assert edge["clause"] == "WHERE" and demand["role"] == "ROWSET"
    assert op["representation"] == "REGEX_WHOLE_INPUT_STRING"
    assert op["pattern_sql"] == "'request_batch:(.*)'" and op["capture_group"] == 1
    pos = op["function_position"]
    assert sql[pos["start"]:pos["end"]] == "regexp_extract"
    assert demand["kind"] == "UNKNOWN" and not demand.get("path_tokens")
    assert result["status"] == "REVIEW_ONLY" and not result["rowset_verified"]


def test_regex_with_opaque_input_keeps_boundary_and_dynamic_arguments_stay_unknown():
    sql = ("SELECT t.id FROM src t WHERE "
           "regexp_extract(private_decode(t.payload), 'request_batch:(.*)', 1) = '2' "
           "AND regexp_extract(t.other, t.pattern, t.group_id) = '2'")
    snap = build_snapshot(sql, "regex_opaque")
    root, = [p["port"] for p in snap["ports"] if p["root"]]
    result = compose_demands([snap], [], [{"port": root}])
    demands = {d["source"]["column"]: d for d in result["source_demands"]
               if d["role"] == "ROWSET" and d["source"]["column"] is not None}
    assert set(demands) == {"payload", "other", "pattern", "group_id"}
    for d in demands.values():
        assert d["kind"] == "UNKNOWN" and not d.get("path_tokens")
    ops = demands["payload"]["witness"][0]["operations"]
    assert ops[0]["kind"] == "OPAQUE_FUNCTION"
    assert ops[1]["representation"] == "REGEX_WHOLE_INPUT_STRING"
    for col in ("other", "pattern", "group_id"):
        assert not any("representation" in op for op in demands[col]["witness"][0]["operations"])


def test_regex_output_path_does_not_become_an_input_path():
    sql = ("SELECT get_json_object(regexp_extract(t.payload, '(.*)', 1), '$.output_key') "
           "AS parsed FROM src t")
    snap = build_snapshot(sql, "regex_output_path")
    root, = [p["port"] for p in snap["ports"] if p["root"]]
    result = compose_demands([snap], [], [{"port": root, "demand": {
        "kind": "VALUE_PATH", "path_tokens": [{"kind": "key", "value": "downstream"}]}}])
    demand, = [d for d in result["source_demands"] if d["source"]["column"] == "payload"]
    assert demand["kind"] == "UNKNOWN" and not demand.get("path_tokens")
    assert demand["downstream_demand"]["path_tokens"][0]["value"] == "downstream"
    assert demand["operation_chain"][-1]["path_tokens"][0]["value"] == "output_key"


def test_nested_case_in_guard_stops_output_path_at_guard_boundary():
    sql = ("SELECT CASE WHEN (CASE WHEN t.flag=1 THEN t.a ELSE t.b END)=1 "
           "THEN t.payload ELSE NULL END AS chosen FROM fact t")
    snap = build_snapshot(sql, "nested_guard")
    root, = [p["port"] for p in snap["ports"] if p["root"]]
    result = compose_demands([snap], [], [{"port": root, "demand": {
        "kind": "VALUE_PATH", "path_tokens": [{"kind": "key", "value": "downstream"}]}}])
    demand = {d["source"]["column"]: d for d in result["source_demands"] if d["source"]["column"]}
    for col in ("flag", "a", "b"):
        assert demand[col]["role"] == "CONDITION" and not demand[col].get("path_tokens")
        assert demand[col]["witness"][0]["clause"] == "SELECT"
    for col in ("a", "b"):
        assert demand[col]["witness"][0]["evidence"]["case_parts"][0]["part"] == "VALUE"
    assert demand["payload"]["role"] == "VALUE"
    assert demand["payload"]["path_tokens"][0]["value"] == "downstream"
    assert result["status"] == "REVIEW_ONLY" and not result["rowset_verified"]


def test_nested_case_in_then_keeps_value_path_and_its_own_guard():
    sql = ("SELECT CASE WHEN t.flag=1 THEN (CASE WHEN t.active=1 THEN t.a ELSE t.b END) "
           "ELSE t.payload END AS chosen FROM fact t")
    snap = build_snapshot(sql, "nested_then")
    root, = [p["port"] for p in snap["ports"] if p["root"]]
    result = compose_demands([snap], [], [{"port": root, "demand": {
        "kind": "VALUE_PATH", "path_tokens": [{"kind": "key", "value": "downstream"}]}}])
    demand = {d["source"]["column"]: d for d in result["source_demands"] if d["source"]["column"]}
    for col in ("flag", "active"):
        assert demand[col]["role"] == "CONDITION" and not demand[col].get("path_tokens")
    for col in ("a", "b", "payload"):
        assert demand[col]["role"] == "VALUE"
        assert demand[col]["path_tokens"][0]["value"] == "downstream"


def test_case_value_comparison_stops_output_path_for_nested_case_operands():
    sql = ("SELECT CASE WHEN t.flag=1 THEN (CASE WHEN t.active=1 THEN t.a ELSE t.b END)=1 "
           "ELSE 0 END AS chosen FROM fact t")
    snap = build_snapshot(sql, "case_value_comparison")
    root, = [p["port"] for p in snap["ports"] if p["root"]]
    path = [{"kind": "key", "value": "downstream"}]
    result = compose_demands([snap], [], [{"port": root, "demand": {
        "kind": "VALUE_PATH", "path_tokens": path}}])
    demands = {d["source"]["column"]: d for d in result["source_demands"] if d["source"]["column"]}
    for col in ("a", "b"):
        d = demands[col]
        assert d["role"] == "VALUE" and d["kind"] == "UNKNOWN"
        assert "path_tokens" not in d and "path_basis" not in d
        assert d["downstream_demand"]["path_tokens"] == path
        assert {"kind": "COMPARISON", "name": "EQ"} in d["operation_chain"]
    for col in ("flag", "active"):
        assert demands[col]["role"] == "CONDITION" and "path_tokens" not in demands[col]
    assert result["status"] == "REVIEW_ONLY" and not result["rowset_verified"]


def test_case_value_comparison_keeps_real_input_path_and_direct_else_path():
    sql = ("SELECT CASE WHEN t.flag=1 THEN get_json_object(t.doc,'$.before') >= 1 "
           "ELSE t.payload END AS chosen FROM fact t")
    snap = build_snapshot(sql, "case_comparison_extract")
    root, = [p["port"] for p in snap["ports"] if p["root"]]
    path = [{"kind": "key", "value": "downstream"}]
    result = compose_demands([snap], [], [{"port": root, "demand": {
        "kind": "VALUE_PATH", "path_tokens": path}}])
    demands = {d["source"]["column"]: d for d in result["source_demands"] if d["source"]["column"]}
    doc = demands["doc"]
    assert doc["role"] == "VALUE" and doc["kind"] == "UNKNOWN"
    assert doc["path_tokens"] == [{"kind": "key", "value": "before"}]
    assert doc["path_basis"] == "OBSERVED_INPUT_ONLY"
    extract, comparison, *_ = doc["operation_chain"]
    assert extract["kind"] == "EXTRACT"
    assert comparison == {"kind": "COMPARISON", "name": "GTE"}
    direct = demands["payload"]
    assert direct["role"] == "VALUE" and direct["path_tokens"] == path
