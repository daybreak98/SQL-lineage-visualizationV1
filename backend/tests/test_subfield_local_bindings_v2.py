"""Local occurrence evidence preserves uncertainty and positional UNION inputs."""
import pytest

from app.services.subfield_local import analyze_local_bindings


def test_database_qualifier_mismatch_has_no_physical_binding():
    result = analyze_local_bindings("SELECT other_db.t.j FROM this_db.t")

    assert result["column_bindings"] == []
    assert any(u["code"] == "UNBOUND_COLUMN" for u in result["facts"]["unknowns"])
    assert not any(m["inputs"] for m in result["facts"]["mappings"])


@pytest.mark.parametrize(("expression", "operation"), [
    ("CAST(t.j AS STRING)", {"Cast", "TryCast"}),
    ("COUNT(t.j)", {"Count"}),
])
def test_function_arguments_keep_physical_binding_without_verified_semantics(expression, operation):
    result = analyze_local_bindings(f"SELECT {expression} AS out FROM src t")

    bindings = [b for b in result["column_bindings"]
                if b["binding"].get("kind") == "NAMED_SOURCE"]
    assert bindings
    assert all(b["binding"] == {"kind": "NAMED_SOURCE", "source": "src", "column": "j"}
               for b in bindings)
    assert all(b["consumer"]["slot"] == 1 for b in bindings)
    assert all(any(op["kind"] in operation and op["semantics"] == "UNVERIFIED"
                   for op in b["operations"]) for b in bindings)


def test_count_star_records_rows_without_inventing_a_named_column():
    result = analyze_local_bindings("SELECT COUNT(*) AS n FROM src t")

    assert result["row_dependencies"]
    assert all(r["kind"] == "ROWS" and r["semantics"] == "UNVERIFIED"
               and r["clause"] == "SELECT" for r in result["row_dependencies"])
    assert all(r["consumer"]["slot"] == 1 for r in result["row_dependencies"])
    assert not any(b["binding"].get("kind") == "NAMED_SOURCE"
                   for b in result["column_bindings"])


def seven_arm_union(last_arm="SELECT NULL AS j"):
    return " UNION ALL ".join([
        *(f"SELECT t.j AS j FROM src_{i} t" for i in range(6)), last_arm,
    ])


@pytest.mark.parametrize('left,ambiguous', [('u.k', False), ('k', True)])
def test_two_arm_union_join_port_is_independent_of_value_certainty(left, ambiguous):
    sql = ("SELECT 1 FROM (SELECT cast(t.x AS BIGINT) AS k FROM lab.t t "
           "UNION ALL SELECT null AS other) u JOIN (SELECT s.y AS k FROM lab.s s) d "
           f"ON {left} = d.k")
    local = analyze_local_bindings(sql, 'hive')
    joins = [b for b in local['column_bindings'] if b['clause'] == 'JOIN']
    if ambiguous:
        assert [b['expression'] for b in joins] == ['d.k']
        assert any(d['code'] == 'AMBIGUOUS_COLUMN' and d.get('clause') == 'JOIN'
                   for d in local['facts']['unknowns'])
        return
    [use] = [b for b in joins if b['expression'] == left]
    p = use['binding']['producer']
    [m] = [m for m in local['facts']['mappings'] if all(m[k] == v for k, v in p.items())]
    assert use['consumer'] is None and m['slot'] == 1 and m['kind'] == 'UNKNOWN'
    assert [b['branch_kind'] for b in m['union_branches']] == ['DERIVED', 'CONSTANT']
    assert any(d['code'] == 'UNION_ALL_TYPE_COERCION_UNVERIFIED' for d in local['facts']['unknowns'])


def test_multi_arm_union_keeps_members_but_does_not_project_condition_path_to_sources():
    result = analyze_local_bindings(
        "SELECT CASE WHEN get_json_object(u.j, '$.x') = 'yes' "
        f"THEN 1 ELSE 0 END AS out FROM ({seven_arm_union()}) u")
    facts = result["facts"]

    observed = [u for u in facts["uses"]
                if u["clause"] == "SELECT" and u["role"] == "CONDITION"
                and u["path_tokens"] == [{"kind": "key", "value": "x"}]]
    assert observed == []
    [unknown] = [u for u in facts["unknowns"] if u["code"] == "UNKNOWN_JSON_INPUT"]
    assert {i["source"] for i in unknown["inputs"]} == {f"src_{i}" for i in range(6)}
    assert all(i["path_tokens"] == [] for i in unknown["inputs"])
    unions = [m for m in facts["mappings"] if len(m.get("union_branches", [])) == 7]
    assert unions
    assert all([b["branch_slot"] for b in m["union_branches"]] == list(range(1, 8))
               for m in unions)
    assert all(m["union_branches"][-1]["branch_kind"] == "CONSTANT" for m in unions)
    assert any(u["code"] == "UNION_ALL_TYPE_COERCION_UNVERIFIED" for u in facts["unknowns"])


def test_union_width_mismatch_does_not_claim_known_outer_json_path():
    result = analyze_local_bindings(
        "SELECT get_json_object(u.j, '$.x') AS out FROM ("
        f"{seven_arm_union('SELECT NULL AS j, NULL AS extra')}) u")
    facts = result["facts"]

    assert any(u["code"] in {"UNBOUND_COLUMN", "UNKNOWN_JSON_INPUT"}
               for u in facts["unknowns"])
    assert not any(u["clause"] == "SELECT" and u.get("path_tokens") == [
        {"kind": "key", "value": "x"}] for u in facts["uses"])
    assert not any(len(m.get("union_branches", [])) == 7 for m in facts["mappings"])
