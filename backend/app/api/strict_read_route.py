"""Append optional evidence to an already serialized, independently cacheable base."""
import asyncio
from time import monotonic

from fastapi import Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, Response

from app.api import strict_read_trial as trial
from app.api import single_cte_cold
from app.api.strict_identity_cache import identity_followup
from app.api.subfield_fact_cache import FactCacheRoute


def append_block(base, block):
    # The router returns only JSON objects. Preserve the exact original bytes
    # and raw headers (including duplicate headers); recompute Content-Length.
    raw = base.body
    if not isinstance(raw, bytes) or not raw.startswith(b"{") or not raw.endswith(b"}"):
        return base
    data = raw[:-1] + (b"," if len(raw) > 2 else b"") + b'"strict_read_evidence":' + JSONResponse(block).body + b"}"
    response = Response(data, status_code=base.status_code, background=base.background)
    response.raw_headers += [(k,v) for k,v in base.raw_headers if k.lower() != b"content-length"]
    return response


async def request_evidence(payload, deadline):
    from app.api.strict_read_deadline import ADDON_SECONDS, RESPONSE_RESERVE_SECONDS, run_bounded
    # Include waiting for a thread token in the wall clock budget. The same
    # absolute cutoff is passed to the independent subprocess supervisor.
    now = monotonic()
    stop = min(now + ADDON_SECONDS, deadline - RESPONSE_RESERVE_SECONDS) if deadline is not None else now + ADDON_SECONDS
    if stop <= now:
        return "BUDGET_EXCEEDED", None
    try:
        return await asyncio.wait_for(
            run_in_threadpool(run_bounded, payload, request_deadline=stop + RESPONSE_RESERVE_SECONDS),
            timeout=stop - now,
        )
    except asyncio.TimeoutError:
        return "BUDGET_EXCEEDED", None


class StrictReadRoute(FactCacheRoute):
    def get_route_handler(self):
        ordinary = super().get_route_handler()

        async def route(request: Request):
            started = monotonic()
            base = await ordinary(request)
            if base.status_code == 200 and getattr(request.state, "strict_identity_pending", None):
                request.state.sql_ready_fallback = base
                release = getattr(request.state, "release_normal_sql_slot", None)
                if release is not None:
                    release()
                try:
                    response = await identity_followup(request, base, started)
                except Exception:
                    response = base
                finally:
                    request.state.strict_identity_pending = None
                return single_cte_cold.append_if_fits(request, base, response)
            pending = getattr(request.state, "strict_read_pending", None)
            if not pending or base.status_code != 200:
                return single_cte_cold.append_if_fits(request, base, base)
            selected, mixed = pending
            # Install the completed core body before doing *any* optional work.
            # No change to 504 behavior for an incomplete/slow normal analysis.
            request.state.sql_ready_fallback = base
            release = getattr(request.state, "release_normal_sql_slot", None)
            if release is not None:
                release()  # The remaining work belongs only to the proof lease.
            try:
                payload, refusal = trial.prepare(selected, mixed)
                if refusal:
                    return append_block(base, refusal)
                timeout = append_block(base, trial.refusal(selected.sql, selected.dialect, "BUDGET_EXCEEDED"))
                request.state.sql_ready_fallback = timeout
                reason, result = await request_evidence(payload, getattr(request.state, "sql_deadline", None))
                if reason == "BUDGET_EXCEEDED":
                    return timeout
                if reason or not result:
                    return append_block(base, trial.refusal(selected.sql, selected.dialect, "OBSERVER_UNAVAILABLE"))
                return append_block(base, result)
            except Exception:
                return append_block(base, trial.refusal(selected.sql, selected.dialect, "OBSERVER_UNAVAILABLE"))
        return route
