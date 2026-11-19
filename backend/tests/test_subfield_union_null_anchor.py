from unittest.mock import patch

import sqlglot

from app.services.subfield import analyze_subfields


def test_projection_anchors_match_individual_union_null_occurrences():
    for prefix, left, right in [("", "NULL", "t.x"), ("", "t.x", "nUlL"),
                                ("-- macro: use Hive statement slices\n", "NULL", "null")]:
        start = prefix + "SELECT v.x FROM (SELECT "
        separator = " /* NULL AS x */ AS x FROM t UNION ALL SELECT "
        sql = start + left + separator + right + " AS x FROM t) v"
        result = analyze_subfields(sql, "hive")
        branches, = [m["union_branches"] for m in result["mappings"] if "union_branches" in m]
        for i, (expr, offset) in enumerate([(left,len(start)),(right,len(start+left+separator))]):
            if expr.lower() != "null":
                continue
            branch = branches[i]
            row, = [m for m in result["mappings"] if all(m[k] == v for k,v in branch["producer"].items())]
            assert row["kind"] == branch["branch_kind"] == "CONSTANT" and row["inputs"] == []
            pos = row["position"]
            assert pos == branch["position"] and (pos["start"], pos["end"]) == (offset, offset+4)
            assert sql[pos["start"]:pos["end"]] == expr
        assert any(u["code"]=="UNION_ALL_TYPE_COERCION_UNVERIFIED" for u in result["unknowns"])


def test_unpositioned_null_does_not_borrow_alias():
    sql = "SELECT v.x FROM (SELECT NULL AS x UNION ALL SELECT NULL AS x) v"
    with patch("app.services.subfield.parse_with_json_path_positions", side_effect=lambda s,d: sqlglot.parse(s, read=d)):
        result = analyze_subfields(sql, "spark")
    rows = [m for m in result["mappings"] if m["kind"] == "CONSTANT"]
    assert len(rows) == 2 and all(m["position"] is None and m["inputs"] == [] for m in rows)
    branches, = [m["union_branches"] for m in result["mappings"] if "union_branches" in m]
    assert all(b["position"] is None for b in branches)
