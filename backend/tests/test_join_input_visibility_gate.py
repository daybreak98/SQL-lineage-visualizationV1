from app.services.subfield import analyze_subfields

SQL = ("SELECT get_json_object(c.j,'$.ok') AS x FROM toy.t a JOIN toy.t b ON "
       "get_json_object(c.j,'$.impossible') = b.j JOIN toy.t c ON a.id=c.id")


def test_forward_on_reference_is_unverified_without_erasing_select():
    for dialect in ("spark", "hive"):
        data = analyze_subfields(SQL,dialect)
        selected, pred = [u for u in data["uses"] if u["kind"] == "EXTRACT"]
        assert selected["named_source_binding"]["relation_instance"]["declaration_position"]["start"] == 122
        assert pred["path"] == "$.impossible" and pred["binding_status"] == "JOIN_INPUT_VISIBILITY_UNVERIFIED"
        assert "named_source_binding" not in pred
        gap, = data["unknowns"]
        assert gap["code"] == pred["binding_status"] and gap["clause"] == "JOIN"
        assert SQL[gap["position"]["start"]:gap["position"]["end"]] == "j"
        assert data["coverage"]["analysis_status"] == "ANALYSIS_INCOMPLETE"


def test_current_and_previous_join_inputs_are_visible_by_instance():
    sql = ("SELECT 1 FROM toy.t a JOIN toy.t b ON get_json_object(a.j,'$.a')=get_json_object(b.j,'$.b') "
           "JOIN toy.t c ON get_json_object(b.j,'$.prior')=get_json_object(c.j,'$.right')")
    data = analyze_subfields(sql,"spark")
    reads = [u for u in data["uses"] if u["kind"] == "EXTRACT"]
    assert not data["unknowns"] and len(reads) == 4
    for u, alias in zip(reads, "abbc"):
        b = u["named_source_binding"]
        assert b["relation_instance"]["declaration_position"]["start"] == sql.index("toy.t "+alias)+6
        assert u["clause"] == "JOIN" and b["scope"] == "1:1"
