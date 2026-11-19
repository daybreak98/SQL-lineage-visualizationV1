from copy import deepcopy
from hashlib import sha256

from app.api.subfield_controller import SubfieldRequest, analyze_subfield_lineage
from app.services.subfield_review import build_review

ROOT = {"statement": 1, "scope": "1:1", "slot": 1}
FILTER = "t.day='2026-11-20'"
SQL = "SELECT get_json_object(t.payload,'$.a') FROM demo.events t WHERE " + FILTER
KEYS = [{"source": "demo.events", "column": "payload", "keys": ["a", "absent"]}]


def review(sql=SQL, keys=KEYS):
    return analyze_subfield_lineage(SubfieldRequest(sql=sql, dialect="spark", protected_outputs=[ROOT],
                                                    candidate_keys=keys))


def test_scalar_filter_attests_only_the_requested_read():
    result = review()
    old = result["review"]
    evidence = old["observed_candidate_read"]
    assert old["candidate_assessment"]["status"] == "UNKNOWN" and old["candidate_assessment"]["entries"] == []
    assert old["path_demand_status"] == "ANALYSIS_INCOMPLETE" and old["status"] == "REVIEW_ONLY"
    assert evidence["analysis"]["sql_sha256"] == sha256(SQL.encode()).hexdigest()
    v, c = evidence["value"], evidence["control"]
    assert v["port"] == ROOT and v["path_tokens"] == [{"kind": "key", "value": "a"}]
    assert (v["source"], v["column"], c["source"], c["column"]) == ("demo.events","payload","demo.events","day")
    assert v["relation_alias_position"] == c["relation_alias_position"]
    assert not evidence["rowset_verified"] and not evidence["pruning_authorized"]
    for span, token in [(v["position"], "get_json_object"), (v["column_position"], "payload"),
                        (c["position"], "day"), (c["predicate_span"], FILTER), (c["relation_alias_position"], "t")]:
        assert SQL[span["start"]:span["end"]] == token
    assert old["observed_control_uses"][0]["position"] == c["position"] and "slot" not in c
    assert "observed_candidate_read" not in review(keys=[dict(KEYS[0], keys=["absent"])])["review"]
    nested = review(SQL.replace("'$.a'", "'$.a.scene'"))["review"]["observed_candidate_read"]
    assert [t["value"] for t in nested["value"]["path_tokens"]] == ["a", "scene"]
    for field in ("uses", "unknowns"):
        changed = deepcopy(result)
        if field == "uses": changed[field].pop()
        else: changed[field].append({"code": "UNBOUND_COLUMN"})
        checked = build_review(changed, [ROOT], KEYS)
        assert "observed_candidate_read" not in checked and checked["unknowns"] == changed["unknowns"]


def test_control_on_sibling_json_key_and_join_remain_out_of_scope():
    for sql, clause in [
        (SQL.replace(FILTER, "get_json_object(t.payload,'$.b')='yes'"), "WHERE"),
        (SQL.replace(" WHERE "+FILTER, " LEFT JOIN demo.tags s ON get_json_object(s.payload,'$.b')='yes'"), "JOIN")
    ]:
        result = review(sql.replace(" FROM demo.events", " AS a FROM demo.events"))
        r = result["review"]
        assert "observed_candidate_read" not in r and r["candidate_assessment"]["status"] == "UNKNOWN"
        assert any(u["role"] == "VALUE" and u["path"] == "$.a" for u in result["uses"])
        assert any(u["path"] == "$.b" and u["clause"] == clause for u in r["observed_control_uses"]), r["observed_control_uses"]
