from app.api.subfield_controller import SubfieldRequest, analyze_subfield_lineage


PAIR = "SELECT l.payload AS j FROM lab.l l UNION ALL SELECT r.body AS j FROM lab.r r"


def request(sql, dialect):
    return analyze_subfield_lineage(SubfieldRequest(
        sql=sql, dialect=dialect, protected_outputs=[port("1:4")],
        candidate_keys=[{"source": "lab.l", "column": "payload", "keys": ["k", "other"]}],
    ))


def port(scope):
    return {"statement": 1, "scope": scope, "slot": 1}


def token(sql, position):
    return sql[position["start"]:position["end"]]


def test_spark_and_hive_locate_two_consumptions_of_the_same_virtual_union_slot():
    sql = (f"SELECT get_json_object(u.j,'$.k') AS hit FROM ({PAIR}) u "
           "WHERE get_json_object(u.j,'$.k') = 'yes'")
    for dialect in ("spark", "hive"):
        result = request(sql, dialect)
        projection, condition = result["union_output_reads"]
        assert (projection["consumer"], projection["role"], projection["clause"]) == (
            port("1:4"), "VALUE", "SELECT",
        )
        assert (condition["consumer"], condition["role"], condition["clause"]) == (
            None, "CONDITION", "WHERE",
        )
        assert projection["scope"] == condition["scope"] == "1:4"
        for read in (projection, condition):
            assert read["producer"] == port("1:3")
            assert read["value_semantics"] == "UNVERIFIED"
            assert read["path_tokens"] == [{"kind": "key", "value": "k"}]
            assert token(sql, read["position"]) == "j"
            assert token(sql, read["call_position"]) == "get_json_object"
            assert token(sql, read["json_path_position"]) == "'$.k'"
            assert "source" not in read
        assert projection["position"]["start"] < condition["position"]["start"]
        [joined] = [m for m in result["mappings"] if m.get("union_branches")]
        assert [edge["producer"] for edge in joined["union_branches"]] == [port("1:1"), port("1:2")]
        assert [(item["source"], item["column"]) for item in joined["inputs"]] == [
            ("lab.l", "payload"), ("lab.r", "body"),
        ]
        assert not any(u["kind"] == "EXTRACT" for u in result["uses"])
        assert result["review"]["observed_path_demands"]["by_protected_output"] == []
        assert result["review"]["candidate_assessment"]["status"] == "UNKNOWN"


def test_explicit_null_is_still_a_union_member_without_a_physical_read():
    pair = PAIR.replace("SELECT r.body AS j FROM lab.r r", "SELECT NULL AS j")
    result = request(f"SELECT get_json_object(u.j,'$.k') AS hit FROM ({pair}) u", "spark")
    [read] = result["union_output_reads"]
    assert read["producer"] == port("1:3")
    assert read["rowset_verified"] is False
    [joined] = [m for m in result["mappings"] if m.get("union_branches")]
    assert [e["branch_kind"] for e in joined["union_branches"]] == ["WHOLE_RAW", "CONSTANT"]
    assert [e["producer"] for e in joined["union_branches"]] == [port("1:1"), port("1:2")]
    assert [u["source"] for u in result["uses"]] == ["lab.l"]


def test_cast_mismatched_width_or_unbound_side_does_not_get_a_logical_read():
    for argument, arms in (
        ("CAST(u.j AS STRING)", PAIR),
        ("u.j", PAIR.replace("r.body AS j", "r.body AS j, r.body AS extra")),
        ("u.j", PAIR.replace("r.body AS j", "missing.body AS j")),
        ("u.j", PAIR.replace("r.body AS j", "r.body AS other")),
    ):
        result = request(f"SELECT get_json_object({argument},'$.k') AS hit FROM ({arms}) u", "hive")
        assert not result.get("union_output_reads")
        assert result["unknowns"] and result["review"]["path_demand_status"] == "ANALYSIS_INCOMPLETE"


def test_three_union_members_preserve_slots_without_claiming_physical_paths():
    arms = PAIR + " UNION ALL SELECT n.raw AS j FROM lab.n n"
    sql = (f"SELECT get_json_object(u.j,'$.k') AS hit FROM ({arms}) u "
           "WHERE get_json_object(u.j,'$.k') = 'yes'")
    for dialect in ("spark", "hive"):
        result = analyze_subfield_lineage(SubfieldRequest(
            sql=sql, dialect=dialect, protected_outputs=[port("1:6")],
            candidate_keys=[{"source": "lab.l", "column": "payload", "keys": ["k"]}],
        ))
        value, condition = result["union_output_reads"]
        assert (value["consumer"], value["role"]) == (port("1:6"), "VALUE")
        assert (condition["consumer"], condition["role"]) == (None, "CONDITION")
        assert value["position"]["start"] < condition["position"]["start"]
        for read in (value, condition):
            assert read["producer"] == port("1:5")
            assert token(sql, read["json_path_position"]) == "'$.k'"
            assert read["path_tokens"] == [{"kind": "key", "value": "k"}]
            assert read["value_semantics"] == "UNVERIFIED"
            assert "source" not in read
        [union] = [m for m in result["mappings"] if m["scope"] == "1:5"]
        assert [edge["producer"] for edge in union["union_branches"]] == [
            port("1:1"), port("1:2"), port("1:4"),
        ]
        assert [token(sql, edge["position"]) for edge in union["union_branches"]] == ["j"] * 3
        assert [(row["source"], row["column"]) for row in union["inputs"]] == [
            ("lab.l", "payload"), ("lab.r", "body"), ("lab.n", "raw"),
        ]
        assert not any(row["kind"] == "EXTRACT" for row in result["uses"])
        assert result["review"]["path_demand_status"] == "ANALYSIS_INCOMPLETE"
        assert result["review"]["candidate_assessment"]["entries"] == []


def test_three_members_with_distinct_or_conflicting_names_keep_the_read_unknown():
    for operator, alias in (("UNION", "j"), ("UNION ALL", "other")):
        arms = PAIR + f" {operator} SELECT n.raw AS {alias} FROM lab.n n"
        result = request(f"SELECT get_json_object(u.j,'$.k') AS hit FROM ({arms}) u", "hive")
        assert not result.get("union_output_reads")
        assert {"UNKNOWN_JSON_INPUT"} <= {row["code"] for row in result["unknowns"]}
        assert not any(row["kind"] == "EXTRACT" for row in result["uses"])


def test_parentheses_keep_only_virtual_union_reads_and_real_branch_reads():
    for last_alias in ("j", "other"):
        sql = (
            "SELECT get_json_object(u.j,'$.outer_key') AS selected, "
            "get_json_object((u.j),'$.wrapped') AS wrapped "
            "FROM (SELECT l.doc AS j, get_json_object(l.meta,'$.local_key') AS side FROM toy.left_rows l "
            "UNION ALL SELECT r.doc AS j, 'R' AS side FROM toy.right_rows r "
            f"UNION ALL SELECT n.doc AS {last_alias}, 'N' AS side FROM toy.third_rows n) u "
            "WHERE get_json_object(u.j,'$.guard') = 'yes'"
        )
        result = analyze_subfield_lineage(SubfieldRequest(
            sql=sql, dialect="spark", protected_outputs=[port("1:6")],
            candidate_keys=[{"source": "toy.left_rows", "column": "doc",
                             "keys": ["outer_key", "missing"]}],
        ))
        assert [(u["source"], u["column"], u["path"]) for u in result["uses"]
                if u["kind"] == "EXTRACT"] == [("toy.left_rows", "meta", "$.local_key")]
        reads = result.get("union_output_reads", [])
        if last_alias == "j":
            assert [token(sql, read["json_path_position"]) for read in reads] == [
                "'$.outer_key'", "'$.wrapped'", "'$.guard'",
            ]
            assert [read["consumer"]["slot"] if read["consumer"] else None for read in reads] == [1, 2, None]
            assert all(read["producer"] == port("1:5") for read in reads)
        else:
            assert reads == []
        review = result["review"]
        assert review["path_demand_status"] == "ANALYSIS_INCOMPLETE"
        assert review["candidate_assessment"]["status"] == "UNKNOWN"
        assert review["candidate_assessment"]["entries"] == []


def test_unqualified_case_guard_uses_the_unique_named_binder_and_its_own_site():
    arms = ("SELECT doc AS packet FROM lab.l l UNION ALL "
            "SELECT body AS packet FROM lab.r r UNION ALL SELECT raw AS packet FROM lab.n n")
    predicate = "get_json_object(packet,'$.class') IN ('a','b')"
    sql = f"SELECT CASE WHEN {predicate} THEN 1 ELSE 0 END AS hit FROM ({arms}) stream"
    for dialect in ("spark", "hive"):
        result = analyze_subfield_lineage(SubfieldRequest(
            sql=sql, dialect=dialect, protected_outputs=[port("1:6")],
        ))
        [read] = result["union_output_reads"]
        assert (read["producer"], read["scope"], read["consumer"]) == (port("1:5"), "1:6", None)
        assert (read["clause"], read["role"], read["qualification"]) == ("SELECT", "CONDITION", "UNQUALIFIED")
        assert read["relation_alias"] == "stream"
        assert read["select_case"] == {"projection": port("1:6"), "parts": [{"part": "GUARD", "arm_slot": 1}]}
        assert token(sql, read["position"]) == "packet"
        assert token(sql, read["call_position"]) == "get_json_object"
        assert token(sql, read["json_path_position"]) == "'$.class'"
        assert read["value_semantics"] == "UNVERIFIED" and read["rowset_verified"] is False
        assert [u["kind"] for u in result["uses"]] == ["WHOLE_RAW"] * 3
        assert result["review"]["observed_path_demands"]["by_protected_output"] == []


def test_unqualified_case_does_not_guess_shadowing_or_treat_standalone_if_as_case():
    arms = PAIR + " UNION ALL SELECT raw AS j FROM lab.n n"
    predicate = "get_json_object(j,'$.class') IN ('a','b')"
    guarded = f"CASE WHEN {predicate} THEN 1 ELSE 0 END AS hit"
    cases = (
        (f"SELECT {guarded} FROM ({arms}) stream CROSS JOIN lab.shadow s", "AMBIGUOUS_COLUMN"),
        (f"SELECT 0 AS j, {guarded} FROM ({arms}) stream", "UNKNOWN_JSON_INPUT"),
        (f"SELECT IF({predicate},1,0) AS hit FROM ({arms}) stream", "UNKNOWN_JSON_INPUT"),
    )
    for sql, reason in cases:
        result = request(sql, "spark")
        assert not result.get("union_output_reads")
        assert any(u["code"] == reason for u in result["unknowns"])
        assert not any(u["kind"] == "EXTRACT" for u in result["uses"])


SCOPED_ARMS = ("SELECT l.payload AS packet, get_json_object(l.meta,'$.local') AS side FROM lab.l l "
               "UNION ALL SELECT r.body AS packet, 'R' AS side FROM lab.r r "
               "UNION ALL SELECT n.raw AS packet, 'N' AS side FROM lab.n n")
LABEL_SCHEMA = {"lab.labels": {"columns": ["id", "label"], "complete": True,
                               "version": "v1", "evidence": "synthetic"}}


def _joined_guard(dialect, from_sql, column="packet", ctes="", schemas=None):
    sql = (f"WITH stream AS ({SCOPED_ARMS}){ctes} "
           f"SELECT CASE WHEN 'hit' <> COALESCE(get_json_object({column},'$.status'),'empty') "
           f"OR 1=0 THEN 1 ELSE 0 END AS hit FROM {from_sql}")
    scope = "1:7" if ctes else "1:6"
    result = analyze_subfield_lineage(SubfieldRequest(
        sql=sql, dialect=dialect, source_schemas=schemas, protected_outputs=[port(scope)],
        candidate_keys=[{"source": "lab.l", "column": "payload", "keys": ["status", "missing"]}],
    ))
    assert [(r["source"], r["column"], r["path"]) for r in result["uses"]
            if r["kind"] == "EXTRACT"] == [("lab.l", "meta", "$.local")]
    assert result["review"]["path_demand_status"] == "ANALYSIS_INCOMPLETE"
    assert result["review"]["candidate_assessment"]["entries"] == []
    return sql, result


def test_joined_case_guard_requires_real_scope_or_schema_disambiguation():
    for dialect in ("spark", "hive"):
        _, ambiguous = _joined_guard(dialect, "stream CROSS JOIN lab.labels ref")
        assert not ambiguous.get("union_output_reads")
        assert any(u["code"] == "AMBIGUOUS_COLUMN" for u in ambiguous["unknowns"])
        for source, ctes, schemas in (
            ("stream CROSS JOIN lab.labels ref", "", LABEL_SCHEMA),
            ("stream LEFT JOIN labels ref ON ref.label = 'known'",
             ", labels AS (SELECT s.label FROM lab.labels s)", None),
        ):
            sql, result = _joined_guard(dialect, source, ctes=ctes, schemas=schemas)
            [read] = result["union_output_reads"]
            assert read["producer"] == port("1:5") and read["consumer"] is None
            assert read["select_case"]["projection"] == port("1:7" if ctes else "1:6")
            assert read["role"] == "CONDITION" and read["relation_alias"] == "stream"
            assert token(sql, read["position"]) == "packet"
            assert token(sql, read["json_path_position"]) == "'$.status'"
            assert not read["rowset_verified"] and read["value_semantics"] == "UNVERIFIED"


def test_joined_case_guard_traces_one_plain_cte_projection_by_original_occurrence():
    for projection in ("stream.packet", "CAST(stream.packet AS STRING)"):
        sql, result = _joined_guard(
            "hive", "relay CROSS JOIN lab.labels ref", column="envelope",
            ctes=f", relay AS (SELECT {projection} AS envelope FROM stream)", schemas=LABEL_SCHEMA,
        )
        reads = result.get("union_output_reads", [])
        if projection == "stream.packet":
            [read] = reads
            assert read["producer"] == port("1:5") and read["relation_alias"] == "relay"
            assert token(sql, read["position"]) == "envelope"
            [step] = read["via"]
            assert step["consumer"] == port("1:6") and step["producer"] == port("1:5")
            assert token(sql, step["position"]) == "packet"
            assert step["position"]["end"] < read["position"]["start"]
        else:
            assert reads == []


def test_joined_case_guard_does_not_infer_using_or_an_open_sibling_output():
    for source, ctes in (
        ("stream JOIN lab.labels ref USING (packet)", ""),
        ("stream CROSS JOIN labels ref", ", labels AS (SELECT * FROM lab.labels s)"),
    ):
        _, result = _joined_guard("spark", source, ctes=ctes,
                                  schemas=LABEL_SCHEMA if not ctes else None)
        assert not result.get("union_output_reads")
