import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.subfield_controller import router

PREFIX = "WITH c AS (SELECT t.payload AS p FROM toy.events t) "
SELECT = "SELECT get_json_object(c.p, '$.a') AS known, get_json_object(c.p, '$.b')"
ROOT = {"statement": 1, "scope": "1:2", "slot": 1}


@pytest.mark.parametrize("alias,missing,reason", [
    ("", "UNKNOWN", "PROJECTION_SCOPE_NOT_CLOSED"),
    (" AS second", "NOT_OBSERVED_NEEDS_VALIDATION", "KEY_EXISTENCE_AND_EFFECT_UNVERIFIED"),
])
def test_positive_read_and_absence_have_separate_closure_requirements(alias, missing, reason):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    sql = PREFIX + SELECT + alias + " FROM c"
    with TestClient(app) as client:
        response = client.post("/api/sql/subfield-lineage", json={"sql": sql, "dialect": "spark",
            "protected_outputs": [ROOT], "candidate_keys": [{"source":"toy.events","column":"payload","keys":["a","missing"]}]})
    assert response.status_code == 200
    facts = response.json()
    review = facts["review"]
    a = review["candidate_assessment"]
    print(alias or "unnamed", a)
    assert [(e["key"],e["status"],e["reason"]) for e in a["entries"]] == [
        ("a","OBSERVED","OVERLAPS_OBSERVED_PATH"), ("missing",missing,reason)]
    assert a["status"] == missing
    if not alias:
        assert a["reason"] == reason
    entry, = review["observed_path_demands"]["by_protected_output"]
    assert entry["protected_output"] == ROOT and entry["path_tokens"] == [{"kind":"key","value":"a"}]
    assert entry["port_reads"] and entry["source"] == "toy.events"
    use, = [u for u in facts["uses"] if u["path"] == "$.a" and u["kind"] == "EXTRACT"]
    pos = use["position"]
    assert sql[pos["start"]:pos["end"]] == "get_json_object" and review["status"] == "REVIEW_ONLY"
