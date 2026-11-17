from app.services.subfield import analyze_subfields


def test_fixed_map_preserves_each_value_use_without_source_key_enumeration():
    sql = """SELECT u.k,u.v FROM lab.events t LATERAL VIEW OUTER
explode(map('type',get_json_object(t.j,'$.kind'),'status',get_json_object(t.j,'$.kind'))) u AS k,v"""
    result = analyze_subfields(sql, "hive")
    [gen] = result["generators"]
    assert gen["input_semantics"] == "FIXED_MAP_CONSTRUCTION"
    assert [e["constructed_key"] for e in gen["entries"]] == ["type", "status"]
    assert all(e["inputs"][0]["path_tokens"] == [{"kind": "key", "value": "kind"}]
               for e in gen["entries"])
    assert gen["entries"][0]["position"] != gen["entries"][1]["position"]
    extracts = [u for u in result["uses"] if u["kind"] == "EXTRACT"]
    assert len(extracts) == 2
    roots = {m["output"]: m for m in result["mappings"] if m["root"]}
    assert roots["k"]["kind"] == "DERIVED" and roots["k"]["inputs"] == []
    assert roots["v"]["kind"] == "DERIVED" and roots["v"]["inputs"]
    assert any(u["code"] == "GENERATOR_FUNCTION_BINDING_UNVERIFIED" for u in result["unknowns"])
    assert not result["coverage"]["complete"]


def test_dynamic_map_key_does_not_claim_finite_constructed_key_set():
    sql = "SELECT u.k,u.v FROM lab.events t LATERAL VIEW explode(map(t.k,get_json_object(t.j,'$.kind'))) u AS k,v"
    result = analyze_subfields(sql, "hive")
    assert not any(g.get("input_semantics") == "FIXED_MAP_CONSTRUCTION" for g in result["generators"])
    assert result["unknowns"]
