"""Synthetic HTTP checks; no catalog, engine or production SQL involved."""
from copy import deepcopy
from hashlib import sha256

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.subfield_controller import router
from app.middleware.local_delivery import LocalDeliveryGuardMiddleware


@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(LocalDeliveryGuardMiddleware)
    app.include_router(router, prefix="/api")
    with TestClient(app) as client:
        yield client


def chain():
    sql_a = "SELECT s.j AS j FROM raw_src s"
    sql_b = "SELECT get_json_object(t.j, '$.a') AS a FROM stage t"
    def identity(name, sql):
        return dict(snapshot=name, sql_sha256=sha256(sql.encode()).hexdigest(),
                    statement=1, scope="1:1")
    producer = dict(**identity("a", sql_a), slot=1)
    consumer = dict(**identity("b", sql_b), relation="stage", column="j",
                    binding="SQL_NAMED_RELATION_COLUMN")
    return dict(mode="compose", snapshots=[
        dict(snapshot_id="a", sql=sql_a, dialect="hive"),
        dict(snapshot_id="b", sql=sql_b, dialect="hive")],
        links=[dict(consumer_source=consumer, producer_port=producer,
                    binding_status="EXPLICIT_VIRTUAL_SLOT", partition={},
                    evidence={"reason": "synthetic caller contract"})],
        protected_outputs=[dict(port=dict(**identity("b", sql_b), slot=1))])


def test_explicit_chain_returns_local_evidence_and_unverified_caller_contract(client):
    payload = chain()
    response = client.post("/api/sql/subfield-lineage", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "REVIEW_ONLY" and result["rowset_verified"] is False
    assert result["caller_contracts"] == payload["links"]
    assert len(result["local_snapshots"]) == 2
    assert any(d["source"]["relation"] == "raw_src" and
               d.get("path_tokens") == [{"kind": "key", "value": "a"}]
               for d in result["source_demands"])
    assert result["coverage_boundary"]["pruning_authorized"] is False
    assert result["coverage_boundary"]["caller_bindings_verified"] is False


@pytest.mark.parametrize("conflict", [False, True])
def test_missing_or_conflicting_link_stays_at_unresolved_boundary(client, conflict):
    payload = chain()
    payload["links"] = payload["links"] * 2 if conflict else []
    response = client.post("/api/sql/subfield-lineage", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "REVIEW_ONLY" and result["rowset_verified"] is False
    if conflict:
        assert any(u["code"] == "MULTIPLE_WRITERS" for u in result["unknowns"])
        assert any(u["code"] == "MULTIPLE_WRITERS" for u in result["unresolved_boundaries"])
    else:
        assert any(b["source"]["relation"] == "stage"
                   for b in result["unresolved_boundaries"])
    assert not any(d["source"]["relation"] == "raw_src" and d.get("path_tokens")
                   for d in result["source_demands"])


@pytest.mark.parametrize("bad", ["duplicate", "budget", "evidence", "partition", "hash"])
def test_invalid_identity_and_budget_rejected(client, bad):
    payload = deepcopy(chain())
    if bad == "duplicate":
        payload["snapshots"][1]["snapshot_id"] = "a"
    elif bad == "budget":
        payload["snapshots"][0]["sql"] = " " * 65536
    elif bad == "evidence":
        payload["links"][0]["evidence"] = {}
    elif bad == "partition":
        del payload["links"][0]["partition"]
    else:
        payload["links"][0]["producer_port"]["sql_sha256"] = "bad"
    assert client.post("/api/sql/subfield-lineage", json=payload).status_code == 422


def test_existing_single_sql_response_is_compatible(client):
    response = client.post("/api/sql/subfield-lineage", json={
        "sql": "SELECT get_json_object(s.j, '$.a') AS a FROM raw_src s", "dialect": "hive"})
    assert response.status_code == 200
    assert "mappings" in response.json()
    assert "local_snapshots" not in response.json()


def test_stale_link_is_rejected_and_missing_protected_port_is_unresolved(client):
    payload = chain()
    payload["links"][0]["consumer_source"]["sql_sha256"] = "0" * 64
    response = client.post("/api/sql/subfield-lineage", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_COMPOSITION_CONTRACT"
    payload = chain()
    payload["protected_outputs"][0]["port"]["slot"] = 99
    response = client.post("/api/sql/subfield-lineage", json=payload)
    assert response.status_code == 200
    assert any(u["code"] == "PROTECTED_OR_PRODUCER_PORT_MISSING"
               for u in response.json()["unresolved_boundaries"])


def test_caller_verified_label_never_verifies_binding(client):
    payload = chain()
    payload["links"][0]["binding_status"] = "VERIFIED_SCHEMA_SLOT"
    response = client.post("/api/sql/subfield-lineage", json=payload)
    assert response.status_code == 200
    assert response.json()["coverage_boundary"]["caller_bindings_verified"] is False
    assert response.json()["rowset_verified"] is False


def test_composition_reuses_existing_sql_concurrency_guard():
    app = FastAPI()
    app.add_middleware(LocalDeliveryGuardMiddleware, max_concurrent_sql_requests=0)
    app.include_router(router, prefix="/api")
    with TestClient(app) as client:
        assert client.post("/api/sql/subfield-lineage", json=chain()).status_code == 429



def composition_path_request(sql, path):
    port = dict(snapshot="x", sql_sha256=sha256(sql.encode()).hexdigest(),
                statement=1, scope="1:1", slot=1)
    return dict(mode="compose", snapshots=[dict(snapshot_id="x", sql=sql, dialect="spark")],
                links=[], protected_outputs=[dict(port=port, demand=dict(kind="VALUE_PATH", path_tokens=path))])


@pytest.mark.parametrize("kind,value", [("key", 3), ("index", "0"), ("index", True),
                                         ("index", 1.0), ("index", -1)])
def test_composition_rejects_invalid_path_tokens(client, kind, value):
    payload = composition_path_request("SELECT s.a FROM src s", [dict(kind=kind, value=value)])
    assert client.post("/api/sql/subfield-lineage", json=payload).status_code == 422


def test_composition_path_stops_at_arithmetic_but_keeps_operand_extraction(client):
    path = [dict(kind="key", value="downstream"), dict(kind="index", value=0)]
    sql = "SELECT s.a + get_json_object(s.doc, '$.before') AS result FROM src s"
    response = client.post("/api/sql/subfield-lineage", json=composition_path_request(sql, path))
    assert response.status_code == 200
    demands = {d["source"]["column"]: d for d in response.json()["source_demands"] if d["source"]["column"]}
    raw, extracted = demands["a"], demands["doc"]
    assert raw["kind"] == "UNKNOWN" and "path_tokens" not in raw
    assert raw["downstream_demand"]["path_tokens"] == path
    assert raw["operation_chain"] == [{"kind": "ARITHMETIC", "name": "ADD"}]
    assert extracted["kind"] == "UNKNOWN"
    assert extracted["path_tokens"] == [dict(kind="key", value="before")]
    assert extracted["path_basis"] == "OBSERVED_INPUT_ONLY"
