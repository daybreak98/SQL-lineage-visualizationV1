from hashlib import sha256
from unittest.mock import patch

from app.services.subfield import Analysis, analyze_subfields


def token(sql, pos):
    return sql[pos["start"]:pos["end"]]


def test_same_table_distinct_instances_and_nested_alias_shadowing():
    sql = ("SELECT get_json_object(a.j,'$.items[0]') AS x, get_json_object(b.j,'$.items[0]') AS y "
           "FROM toy.t a JOIN toy.t b ON a.id=b.id WHERE EXISTS "
           "(SELECT 1 FROM toy.t a WHERE get_json_object(a.j,'$.items[0]')='yes')")
    data = analyze_subfields(sql, "hive")
    rows = [u for u in data["uses"] if u["kind"] == "EXTRACT"]
    assert len(rows) == 3 and data["coverage"]["sql_sha256"] == sha256(sql.encode()).hexdigest()
    expected = {(sql.index("toy.t a")+6,"1:2","a"), (sql.index("toy.t b")+6,"1:2","b"),
                (sql.rindex("toy.t a")+6,"1:1","a")}
    found = set()
    for use in rows:
        b = use["named_source_binding"]; inst = b["relation_instance"]
        p = inst["declaration_position"]
        found.add((p["start"],b["scope"],token(sql,p)))
        assert b["scope"] == inst["declaration_scope"] and inst["statement"] == use["statement"] == 1
        assert token(sql,b["qualifier_position"]) == inst["name"] == token(sql,p)
        assert [token(sql,x) for x in inst["table_part_positions"]] == ["toy","t"]
        assert token(sql,b["column_position"]) == use["column"] == "j" and use["source"] == "toy.t"
        assert token(sql,use["position"]) == "get_json_object"
        assert use["path_tokens"] == [{"kind":"key","value":"items"},{"kind":"index","value":0}]
    assert found == expected
    with patch.object(Analysis, "named_json_read_binding", return_value=None):
        old = analyze_subfields(sql, "hive")
    for use in rows:
        del use["named_source_binding"]
    assert data == old


def test_ambiguous_use_and_virtual_passthrough_do_not_inherit_a_table_instance():
    sql = ("WITH c AS (SELECT t.j AS carried FROM toy.t t) "
           "SELECT get_json_object(j,'$.k') AS ambiguous, get_json_object(c.carried,'$.k') AS virtual, "
           "get_json_object(a.j,'$.k') AS direct FROM toy.t a JOIN toy.t b ON a.id=b.id CROSS JOIN c")
    data = analyze_subfields(sql, "spark")
    assert any(u["code"] == "AMBIGUOUS_COLUMN" for u in data["unknowns"])
    by_pos = {u["position"]["start"]:u for u in data["uses"] if u["kind"] == "EXTRACT"}
    assert sql.index("get_json_object(j") not in by_pos
    assert "named_source_binding" not in by_pos[sql.index("get_json_object(c.")]
    assert by_pos[sql.index("get_json_object(a.")]["named_source_binding"]["relation_instance"]["name"] == "a"
