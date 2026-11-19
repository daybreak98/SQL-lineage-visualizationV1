from copy import deepcopy
from unittest.mock import patch

from app.api.subfield_controller import SubfieldRequest, analyze_subfield_lineage
from app.services.subfield import Analysis

SQL = ("SELECT get_json_object(a.payload,'$.k') AS result FROM demo.events a "
       "LEFT JOIN demo.events b ON b.id=a.id INNER JOIN demo.events c ON b.parent=c.id")
PORT = dict(statement=1, scope="1:1", slot=1)


def run(sql):
    return analyze_subfield_lineage(SubfieldRequest(sql=sql, dialect="spark", protected_outputs=[PORT],
        candidate_keys=[dict(source="demo.events", column="payload", keys=["k"])]))


def test_repeated_table_opposite_operand_order_and_consumer_identity():
    result = run(SQL)
    joins = result["review"]["observed_control_uses"]
    assert [(u["consumer"]["ordinal"], u["relation_instance"]["alias"], u["relation_instance"]["join_side"])
            for u in joins] == [(1,"b","RIGHT"), (1,"a","LEFT"), (2,"b","LEFT"), (2,"c","RIGHT")]
    for use, expected in zip(joins, ["b.id=a.id"]*2 + ["b.parent=c.id"]*2):
        assert use["source"] == "demo.events" and use["role"] == "RELATIONAL"
        c = use["consumer"]
        assert c["scope"] == use["scope"] == PORT["scope"] and c["statement"] == 1 and "slot" not in c
        assert c["join_type"] == ("LEFT" if c["ordinal"] == 1 else "INNER")
        assert not c["rowset_verified"] and not c["pruning_authorized"]
        for pos, token in [(c["predicate_span"],expected), (use["position"],use["column"]),
                           (use["relation_instance"]["alias_position"],use["relation_instance"]["alias"])]:
            assert SQL[pos["start"]:pos["end"]] == token
    assert joins[0]["relation_instance"]["alias_position"] != joins[1]["relation_instance"]["alias_position"]
    with patch.object(Analysis, "bind_join_sites", return_value=None):
        previous = run(SQL)
    # Both lists expose the same occurrences; JSON round-trip simulates detached wire data.
    import json
    cleaned = json.loads(json.dumps(result))
    for use in cleaned["uses"] + cleaned["review"]["observed_control_uses"]:
        if "consumer" in use:
            for key in ("consumer","scope","relation_instance","qualifier_position"):
                del use[key]
    assert cleaned == previous


def test_ambiguous_or_forward_reference_does_not_create_a_control_witness():
    for predicate in ("id=a.id", "c.id=a.id", "a.id=a.parent"):
        result = run(SQL.replace("b.id=a.id", predicate))
        assert not any(u.get("consumer", {}).get("ordinal") == 1 for u in result["uses"])
        assert result["review"]["candidate_assessment"]["status"] == "UNKNOWN"
    assert run(SQL.replace("b.id=a.id","id=a.id"))["unknowns"]
