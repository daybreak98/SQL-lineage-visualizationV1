"""Local-only compact identity addon. Facts, proof and completion publish atomically."""
import asyncio
from hashlib import sha256
import os
from threading import BoundedSemaphore
from time import monotonic

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from app.api import subfield_fact_cache as ordinary
from app.api.strict_read_deadline import ADDON_SECONDS, RESPONSE_RESERVE_SECONDS
from app.services.p25_strict.strict_sidecar import Capture, Descriptor, Sidecar
from experiments.strict_use_wire_v2 import BLOCK, FIELD, MAX_BYTES, REF_KIND, expand, wire
import sqlglot

FLAG = "SUBFIELD_STRICT_USE_DEV"
RESOLVER = "0e0a38ab0a1536000a8ebcfeaf18dfd971aedd62"
RULES = "binding-shadow-inner-2"
WIRE = "compact-v2"
BUDGET = "capture-v1:max-hops-8:wire-32768"
store = ordinary.FactSnapshots()
_slot = BoundedSemaphore(1)


def enabled():
    return os.environ.get(FLAG) == "1"


def describe(request, schemas):
    return Descriptor(request.sql, request.dialect,
                      "explicit" if "dialect" in request.model_fields_set else "default",
                      schemas, sqlglot.__version__, RESOLVER, RULES, WIRE, BUDGET,
                      "local-strict-inner", {"schema_field": "source_schemas" in request.model_fields_set,
                                             "schema_nonnull": request.source_schemas is not None})


def patch(packed):
    return {"block": packed[BLOCK], "refs": [
        [i, row[FIELD]] for i, row in enumerate(packed["uses"])
        if (row.get(FIELD) or {}).get("kind") == REF_KIND]}


def apply(facts, item):
    if BLOCK in facts:
        raise ValueError("response already has identity evidence")
    rows = list(facts["uses"])
    seen = set()
    for i, binding in item["refs"]:
        if (type(i) is not int or not 0 <= i < len(rows) or i in seen or FIELD in rows[i]
                or binding.get("kind") != REF_KIND):
            raise ValueError("invalid identity reference")
        seen.add(i)
        rows[i] = {**rows[i], FIELD: binding}
    return {**facts, "uses": rows, BLOCK: item["block"]}


def verify(d, facts, proof):
    # Structural validation for a private, same-run, completed record only;
    # never treat an externally supplied decoder payload as authoritative.
    item, = proof
    coverage = facts["coverage"]
    if (not coverage.get("parsed") or coverage.get("partial") or not item["refs"]
            or item["block"].get("status") != "ATTACHED"):
        return False
    snapshot = {"sql_sha256": sha256(d.sql.encode("utf-8")).hexdigest(), "dialect": d.dialect,
                "schema_sha256": sha256(wire(d.schema, sort=True)).hexdigest(),
                "sqlglot": d.parser_version, "rules": d.rules_version}
    packed = apply(facts, item)
    if len(wire(packed)) - len(wire(facts)) > MAX_BYTES:
        return False
    expand(packed, snapshot)
    return True


cache = Sidecar(store, verifier=verify, verified_once=True)


def lookup(http_request, req, schemas):
    # FactCacheRoute established the anonymous-local/guard eligibility.
    if not getattr(http_request.state, "subfield_fact_cache", None):
        if os.environ.get("SUBFIELD_FACT_CACHE") != "1":
            store.clear()
        return None, None, None
    try:
        generation = store.generation
        d = describe(req, schemas)
        d.key()  # oversized descriptors bypass caching, not the addon
        return d, generation, cache.lookup(d, allowed=True)
    except Exception:
        return None, None, None


def render(base, job):
    """Run only after ordinary response serialization and normal lease return."""
    facts, pack, hit, descriptor, generation, payload = job
    if hit is None:
        packed = pack()
        if packed is None:
            return base, None
        item = patch(packed)
    else:
        item, = hit.proof
    response = JSONResponse(apply(payload, item), status_code=base.status_code,
                            background=base.background)
    if len(response.body) - len(base.body) > MAX_BYTES:
        return base, None
    response.raw_headers = [(k, v) for k, v in response.raw_headers if k == b"content-length"]
    response.raw_headers.extend((k, v) for k, v in base.raw_headers if k.lower() != b"content-length")
    pending = None
    if hit is None and descriptor is not None and item["block"]["status"] == "ATTACHED":
        try:
            pending = cache.prepare(descriptor, Capture(descriptor.key(), facts, [item], "COMPLETE"),
                                    allowed=True, generation=generation)
        except Exception:
            pass  # a cache failure must not suppress a valid attachment
    return response, pending


async def identity_followup(request, base, started):
    if not enabled():
        return base
    deadline = getattr(request.state, "sql_deadline", None)
    now = monotonic()
    limit = min(ADDON_SECONDS, deadline - now - RESPONSE_RESERVE_SECONDS) if deadline else ADDON_SECONDS
    if limit <= 0 or not _slot.acquire(blocking=False):
        return base

    job = request.state.strict_identity_pending

    def work():
        try:
            return render(base, job)
        except Exception:
            return base, None
        finally:
            # A timed-out thread still owns the private slot until it exits.
            _slot.release()

    task = asyncio.create_task(run_in_threadpool(work))
    try:
        response, pending = await asyncio.wait_for(asyncio.shield(task), timeout=limit)
    except asyncio.TimeoutError:
        return base
    if not enabled():
        return base
    # Do not publish from a worker or a cancelled / late response.
    if pending is not None and monotonic() - started <= ordinary.MAX_FILL_SECONDS:
        try:
            if ordinary.enabled(request):
                cache.publish(pending, completed=True)
        except Exception:
            pass
    return response
