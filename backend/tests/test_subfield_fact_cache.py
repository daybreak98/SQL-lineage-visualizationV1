"""Small real-route checks; no corpus replay or latency benchmark."""
from fastapi.testclient import TestClient

from app.main import app
from app.services import subfield
from app.services.subfield_review import build_review


SQL = ("WITH b AS (SELECT t.j FROM src t) SELECT "
       "get_json_object(b.j,'$.a') AS a, get_json_object(b.j,'$.b') AS b FROM b")


def test_same_sql_two_roots_equal_uncached_and_skip_parsing(monkeypatch):
    # Break caught: recomputing facts, reusing a review, or omitting schema/dialect.
    monkeypatch.setenv("SUBFIELD_FACT_CACHE", "1")
    baseline = subfield.analyze_subfields(SQL, "spark", {})
    roots = [m for m in baseline["mappings"] if m.get("root")]
    ports = [{k: m[k] for k in ("statement", "scope", "slot")} for m in roots]
    assert len(ports) == 2
    candidates = [[{"source": "src", "column": "j", "keys": [name, "unseen"]}]
                  for name in ("a", "b")]
    expected = [dict(baseline, review=build_review(baseline, [port], candidates[i]))
                for i, port in enumerate(ports)]
    parsed = []
    analyze = subfield.analyze_subfields

    def counted(*args, **kwargs):
        parsed.append(1)
        return analyze(*args, **kwargs)

    monkeypatch.setattr(subfield, "analyze_subfields", counted)
    with TestClient(app) as client:
        payload = {"sql": SQL, "dialect": "spark"}
        initial = client.post("/api/sql/subfield-lineage", json=payload)
        assert initial.status_code == 200 and initial.json() == baseline
        for index, port in enumerate(ports):
            response = client.post("/api/sql/subfield-lineage", json=dict(
                payload, protected_outputs=[port], candidate_keys=candidates[index]))
            assert response.status_code == 200 and response.json() == expected[index]
        assert len(parsed) == 1, "two root reviews must reuse facts, never each other's review"
        changed = dict(payload, dialect="hive", source_schemas={"src": {
            "columns": ["j"], "complete": True, "version": "v2", "evidence": "test declaration",
        }}, protected_outputs=[ports[0]])
        response = client.post("/api/sql/subfield-lineage", json=changed)
        assert response.status_code == 200
        assert response.json()["coverage"]["dialect"] == "hive"
        assert len(parsed) == 2, "schema/dialect changed: miss, cold review must run original analysis"


def test_parsed_unknowns_are_reused_without_changing_any_review_field(monkeypatch):
    sql, dialect = "SELECT private_fn(t.payload) AS id FROM demo.events t", "hive"
    baseline = subfield.analyze_subfields(sql, dialect, {})
    assert baseline["coverage"]["parsed"] is True
    assert not baseline["coverage"]["partial"] and baseline["unknowns"]
    root = next(m for m in baseline["mappings"] if m.get("root"))
    ports = [{k: root[k] for k in ("statement", "scope", "slot")}]
    expected = dict(baseline, review=build_review(baseline, ports))
    calls = []
    analyze = subfield.analyze_subfields

    def counted(*args, **kwargs):
        calls.append(1)
        return analyze(*args, **kwargs)

    monkeypatch.setattr(subfield, "analyze_subfields", counted)
    monkeypatch.setenv("SUBFIELD_FACT_CACHE", "1")
    with TestClient(app) as client:
        payload = {"sql": sql, "dialect": dialect}
        initial = client.post("/api/sql/subfield-lineage", json=payload)
        assert initial.status_code == 200 and initial.json() == baseline
        response = client.post("/api/sql/subfield-lineage", json=dict(payload, protected_outputs=ports))
        assert response.status_code == 200 and response.json() == expected
        assert response.json()["unknowns"] == baseline["unknowns"]
        assert len(calls) == 1, "parsed unknowns are immutable facts, not a parse failure"


def test_key_changes_for_each_semantic_input_and_keeps_defaults():
    from starlette.requests import Request
    from app.api.subfield_controller import SubfieldRequest
    from app.api.subfield_fact_cache import fact_key
    request = Request({"type": "http"})
    request.state.subfield_fact_cache = {"generation": 0}
    fn = subfield.analyze_subfields
    schemas = {"src": {"columns": ["j", "k"], "complete": True, "version": "v1", "evidence": "e"}}
    base = fact_key(request, SQL, "spark", schemas, fn)
    assert base != fact_key(request, SQL + " ", "spark", schemas, fn)
    assert base != fact_key(request, SQL, "hive", schemas, fn)
    for field, value in (("columns", ["k", "j"]), ("complete", False),
                         ("version", "v2"), ("evidence", "other")):
        changed = {"src": {**schemas["src"], field: value}}
        assert base != fact_key(request, SQL, "spark", changed, fn)
    assert base != fact_key(request, SQL, "spark", {"SRC": schemas["src"]}, fn)
    implicit = SubfieldRequest(sql=SQL, source_schemas={"src": {"columns": ["j"]}})
    explicit = SubfieldRequest(sql=SQL, dialect="spark", source_schemas={"src": {
        "columns": ["j"], "complete": False, "version": "", "evidence": ""}})
    assert implicit.model_dump() == explicit.model_dump()


def test_snapshot_bounds_expiry_generation_and_private_decode(monkeypatch):
    from app.api import subfield_fact_cache as cache
    clock = [0]
    store = cache.FactSnapshots(max_entries=2, max_bytes=48, max_entry_bytes=24, ttl=3, clock=lambda: clock[0])
    monkeypatch.setattr(cache, "snapshots", store)
    keys = [(subfield.analyze_subfields, "v", bytes([i])) for i in range(4)]
    for key in keys[:3]:
        store.put(key, b'{"uses":[]}', store.generation)
    assert store.get(keys[0]) is None and store.get(keys[1]) is not None
    fresh = cache.read_facts(keys[1])
    fresh["uses"].append("private")
    assert cache.read_facts(keys[1]) == {"uses": []}
    store.put(keys[3], b"x" * 25, store.generation)
    assert store.get(keys[3]) is None
    old_generation = store.generation
    store.clear()
    store.put(keys[0], b"{}", old_generation)
    assert store.get(keys[0]) is None
    store.put(keys[0], b"{}", store.generation)
    clock[0] = 3
    assert store.get(keys[0]) is None
    store.put(keys[0], b"bad-json", store.generation)
    assert cache.read_facts(keys[0]) is None
    bytes_limited = cache.FactSnapshots(max_entries=10, max_bytes=20, max_entry_bytes=20)
    bytes_limited.put(keys[0], b"x" * 9, 0)
    bytes_limited.put(keys[1], b"y" * 9, 0)
    assert bytes_limited.get(keys[0]) is None and bytes_limited.get(keys[1]) == b"y" * 9


def test_failure_oversize_and_disabled_paths_do_not_publish(monkeypatch):
    from starlette.requests import Request
    from app.api import subfield_fact_cache as cache
    request = Request({"type": "http"})
    state = {"pending": None, "generation": 0}
    request.state.subfield_fact_cache = state
    key = cache.fact_key(request, "SELECT 1", "spark", {}, subfield.analyze_subfields)
    for result in ({"coverage": {"parsed": False}},
                   {"coverage": {"parsed": True, "partial": True}},
                   {"coverage": {"parsed": True}, "review": {}},
                   {"coverage": {"parsed": True}, "uses": [object()]},
                   {"coverage": {"parsed": True}, "uses": ["x" * (128 * 1024)]}):
        cache.propose_facts(request, key, result)
        assert state["pending"] is None
    assert cache.fact_key(request, "x" * (16 * 1024), "spark", {}, subfield.analyze_subfields) is None
    monkeypatch.delenv("SUBFIELD_FACT_CACHE", raising=False)
    assert cache.enabled(request) is False


def test_only_current_anonymous_loopback_guard_can_enable(monkeypatch):
    from fastapi import FastAPI
    from starlette.requests import Request
    from app.api import subfield_fact_cache as cache
    from app.middleware.local_delivery import LocalDeliveryGuardMiddleware
    monkeypatch.setenv("SUBFIELD_FACT_CACHE", "1")
    scope = {"type": "http", "app": app, "client": ("127.0.0.1", 12345), "headers": []}
    assert cache.enabled(Request(scope)) is True
    for header in (b"authorization", b"cookie", b"x-api-key"):
        assert cache.enabled(Request({**scope, "headers": [(header, b"private")]})) is False
    for field in ("user", "session"):
        assert cache.enabled(Request({**scope, field: None})) is False
    assert cache.enabled(Request({**scope, "client": ("203.0.113.1", 12345)})) is False
    alternate = FastAPI()
    alternate.add_middleware(LocalDeliveryGuardMiddleware, sql_timeout_seconds=0.01)
    assert cache.enabled(Request({**scope, "app": alternate})) is False


def test_route_only_publishes_fast_success_and_never_cancelled_or_error(monkeypatch):
    import asyncio
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from app.api import subfield_fact_cache as cache
    from fastapi.routing import APIRoute
    store = cache.FactSnapshots()
    monkeypatch.setattr(cache, "snapshots", store)
    monkeypatch.setattr(cache, "enabled", lambda request: True)
    elapsed = [0]
    monkeypatch.setattr(cache, "monotonic", lambda: elapsed[0])
    key = (subfield.analyze_subfields, "v", b"descriptor")
    outcome = ["fast"]

    async def original(request):
        request.state.subfield_fact_cache["pending"] = (key, b"{}")
        if outcome[0] == "cancel":
            raise asyncio.CancelledError
        if outcome[0] == "error":
            raise ValueError("analysis failed")
        if outcome[0] == "slow":
            elapsed[0] += 1
        return JSONResponse({}, status_code=500 if outcome[0] == "500" else 200)

    monkeypatch.setattr(APIRoute, "get_route_handler", lambda self: original)
    route = cache.FactCacheRoute.__new__(cache.FactCacheRoute).get_route_handler()
    for kind in ("fast", "slow", "cancel", "error", "500"):
        store.clear()
        outcome[0] = kind
        request = Request({"type": "http"})
        try:
            asyncio.run(route(request))
        except (asyncio.CancelledError, ValueError):
            assert kind in {"cancel", "error"}
        assert (store.get(key) is not None) == (kind == "fast")
        assert request.state.subfield_fact_cache is None
