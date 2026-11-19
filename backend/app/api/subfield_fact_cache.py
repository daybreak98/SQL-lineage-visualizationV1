"""Opt-in, single-local-user fact snapshots. No ASTs, reviews or disk writes.

SUBFIELD_FACT_CACHE=1 enables this for the existing 30-second local guard.
Unset/0 bypasses and clears it on the next request. Restart on rule/config changes.
This is not a multi-user cache. Payload bounds are not a process RSS bound.
"""
from collections import OrderedDict
import json
import os
from threading import Lock
from time import monotonic

from fastapi import Request
from fastapi.routing import APIRoute
import sqlglot

from app.middleware.local_delivery import LocalDeliveryGuardMiddleware, SQL_TIMEOUT_SECONDS, is_loopback_client


class FactSnapshots:
    def __init__(self, *, max_entries=2, max_bytes=256 * 1024,
                 max_entry_bytes=128 * 1024, ttl=30, clock=monotonic):
        self.entries = OrderedDict()
        self.max_entries, self.max_bytes = max_entries, max_bytes
        self.max_entry_bytes, self.ttl, self.clock = max_entry_bytes, ttl, clock
        self.lock = Lock()
        self.generation = 0

    def clear(self):
        with self.lock:
            self.entries.clear()
            self.generation += 1

    def _expire(self):
        now = self.clock()
        for key, (expires, _) in list(self.entries.items()):
            if expires <= now:
                del self.entries[key]

    def get(self, key):
        with self.lock:
            self._expire()
            entry = self.entries.get(key)
            return entry[1] if entry else None

    def put(self, key, value, generation):
        # Key contains the process-local analyzer identity, parser version and
        # exact descriptor bytes. Count the variable key text as retained data.
        size = len(key[1].encode("utf-8")) + len(key[2]) + len(value)
        if size > self.max_entry_bytes or size > self.max_bytes:
            return
        with self.lock:
            if generation != self.generation:
                return
            self._expire()
            self.entries.pop(key, None)
            self.entries[key] = (self.clock() + self.ttl, value)
            while (len(self.entries) > self.max_entries or
                   sum(len(k[1].encode("utf-8")) + len(k[2]) + len(v[1])
                       for k, v in self.entries.items()) > self.max_bytes):
                self.entries.popitem(last=False)


snapshots = FactSnapshots()
MAX_DESCRIPTOR_BYTES = 16 * 1024
MAX_FILL_SECONDS = 0.25


def enabled(request):
    if os.environ.get("SUBFIELD_FACT_CACHE") != "1":
        snapshots.clear()
        return False
    # There is no authenticated user/tenant model in the current workbench.
    # Never enable this cache for authenticated requests or a changed guard.
    guards = [m for m in request.app.user_middleware if m.cls is LocalDeliveryGuardMiddleware]
    return (is_loopback_client(request.client.host if request.client else None)
            and not any(h in request.headers for h in ("authorization", "cookie", "x-api-key"))
            and "user" not in request.scope and "session" not in request.scope
            and SQL_TIMEOUT_SECONDS == 30.0 and len(guards) == 1
            and guards[0].kwargs.get("sql_timeout_seconds", SQL_TIMEOUT_SECONDS) == 30.0)


class FactCacheRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def route(request: Request):
            started = monotonic()
            state = None
            try:
                if enabled(request):
                    state = {"pending": None, "generation": snapshots.generation}
                    request.state.subfield_fact_cache = state
            except Exception:
                pass  # Optional cache must not change the API error contract.
            try:
                response = await original(request)
                # The sync worker can only propose bytes. It cannot publish
                # after cancellation/timeout; slow paths never populate.
                if state and state["pending"] and response.status_code == 200:
                    try:
                        if monotonic() - started <= MAX_FILL_SECONDS and enabled(request):
                            key, value = state["pending"]
                            snapshots.put(key, value, state["generation"])
                    except Exception:
                        pass
                return response
            finally:
                if state is not None:
                    state["pending"] = None
                request.state.subfield_fact_cache = None

        return route


def fact_key(request, sql, dialect, schemas, analyzer):
    if request is None or not getattr(request.state, "subfield_fact_cache", None):
        return None
    try:
        # No sorting/folding/SQL normalization; JSON lists and dict order stay.
        raw = json.dumps(["facts-v2:two-step-v1", sql, dialect, schemas], ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
        return (analyzer, sqlglot.__version__, raw) if len(raw) <= MAX_DESCRIPTOR_BYTES else None
    except Exception:
        return None


def read_facts(key):
    try:
        raw = snapshots.get(key) if key is not None else None
        return json.loads(raw) if raw is not None else None
    except Exception:
        return None


def propose_facts(request, key, result):
    if key is None:
        return
    try:
        state = getattr(request.state, "subfield_fact_cache", None)
        coverage = result.get("coverage", {})
        # Semantic unknowns are static evidence too; keep them exactly. Only
        # failed/partial parsing is excluded, never upgrade review conclusions.
        if (state is None or "review" in result or coverage.get("parsed") is not True
                or coverage.get("partial")):
            return
        raw = json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(raw) + len(key[2]) + len(key[1].encode("utf-8")) <= snapshots.max_entry_bytes:
            state["pending"] = (key, raw)
    except Exception:
        pass
