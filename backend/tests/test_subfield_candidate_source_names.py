from app.api.subfield_controller import SubfieldRequest, analyze_subfield_lineage


NAMED_C = ("WITH c AS (SELECT t.event_payload AS p FROM {} t)\n"
           "SELECT get_json_object(c.p,'$.media_id') AS extracted FROM c;")


def _review(sql, source="lab.media_events", *, dialect="spark", scope="1:2"):
    return analyze_subfield_lineage(SubfieldRequest(
        sql=sql, dialect=dialect,
        protected_outputs=[{"statement": 1, "scope": scope, "slot": 1}],
        candidate_keys=[{"source": source, "column": "event_payload", "keys": ["media_id"]}],
    ))


def test_case_difference_explains_unverified_spark_carrier_for_both_identifier_forms():
    for lower, upper in (("lab.media_events", "LAB.MEDIA_EVENTS"),
                         ("`lab`.`media_events`", "`LAB`.`MEDIA_EVENTS`")):
        for relation, observed_source, expected in (
            (lower, "lab.media_events", ("OBSERVED", "OVERLAPS_OBSERVED_PATH")),
            (upper, "LAB.MEDIA_EVENTS", ("UNKNOWN", "SOURCE_NAME_CASE_MISMATCH_UNVERIFIED")),
        ):
            result = _review(NAMED_C.format(relation))
            assert result["unknowns"] == []
            assert [row["source"] for row in result["uses"]] == [observed_source, observed_source]
            review = result["review"]
            [demand] = review["observed_path_demands"]["by_protected_output"]
            assert demand["source"] == observed_source
            [entry] = review["candidate_assessment"]["entries"]
            assert entry["source"] == "lab.media_events"
            assert (entry["status"], entry["reason"]) == expected


def test_case_collisions_do_not_confirm_a_candidate_source():
    sql = ("WITH lo AS (SELECT t.event_payload AS p FROM lab.media_events t), "
           "hi AS (SELECT t.event_payload AS p FROM LAB.MEDIA_EVENTS t) "
           "SELECT get_json_object(lo.p,'$.media_id') AS extracted FROM lo")
    result = _review(sql, "Lab.Media_Events", scope="1:3")
    assert not result["unknowns"]
    assert {row["source"] for row in result["uses"]} == {"lab.media_events", "LAB.MEDIA_EVENTS"}
    [entry] = result["review"]["candidate_assessment"]["entries"]
    assert (entry["status"], entry["reason"]) == ("UNKNOWN", "SOURCE_NAME_CASE_AMBIGUOUS")
    [exact] = _review(sql, scope="1:3")["review"]["candidate_assessment"]["entries"]
    assert (exact["status"], exact["reason"]) == ("OBSERVED", "OVERLAPS_OBSERVED_PATH")


def test_hive_keeps_existing_candidate_review_boundary():
    result = _review(NAMED_C.format("LAB.MEDIA_EVENTS"), dialect="hive")
    assert result["review"]["candidate_assessment"] == {
        "status": "UNKNOWN", "entries": [], "reason": "REQUIRES_SINGLE_SPARK_STATEMENT",
    }
