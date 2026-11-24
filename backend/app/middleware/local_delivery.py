from __future__ import annotations

import asyncio
import ipaddress
from threading import Lock
from time import monotonic

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse, Response
from starlette.types import Receive, Scope, Send

MAX_REQUEST_BODY_BYTES = 2 * 1024 * 1024
MAX_SQL_CHARS = 64 * 1024
SQL_TIMEOUT_SECONDS = 30.0
MAX_CONCURRENT_SQL_REQUESTS = 1

_SQL_PATHS = {
    "/api/sql/analyze",
    "/api/sql/subfield-lineage",
    "/api/sql/convert",
    "/api/sql/format",
}


def is_loopback_client(host: str | None) -> bool:
    if host == "testclient":
        return True
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class LocalDeliveryGuardMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        max_request_body_bytes: int = MAX_REQUEST_BODY_BYTES,
        sql_timeout_seconds: float = SQL_TIMEOUT_SECONDS,
        max_concurrent_sql_requests: int = MAX_CONCURRENT_SQL_REQUESTS,
    ) -> None:
        self._downstream = app
        super().__init__(self._with_bounded_sql_body)
        self.max_request_body_bytes = max_request_body_bytes
        self.sql_timeout_seconds = sql_timeout_seconds
        self.max_concurrent_sql_requests = max_concurrent_sql_requests
        self._active_sql_requests = 0
        self._active_lock = Lock()

    async def _with_bounded_sql_body(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http' or scope['method'] != 'POST' or HTTPConnection(scope).url.path not in _SQL_PATHS:
            await self._downstream(scope, receive, send)
            return

        # Count incoming bytes before FastAPI decodes JSON. Do not retain the over-limit chunk.
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                # BaseHTTPMiddleware expects a response even if the peer is gone.
                await Response(status_code=400)(scope, receive, send)
                return
            chunk = message.get('body', b'')
            if len(body) + len(chunk) > self.max_request_body_bytes:
                response = JSONResponse({"detail": "Request body too large"}, status_code=413)
                await response(scope, receive, send)
                return
            body.extend(chunk)
            if not message.get('more_body', False):
                break

        # Pass one complete body event to the JSON parser, then resume the ASGI receive channel.
        pending = bytes(body)
        del body

        async def replay() -> dict:
            nonlocal pending
            if pending is None:
                return await receive()
            message = {'type': 'http.request', 'body': pending, 'more_body': False}
            pending = None
            return message

        await self._downstream(scope, replay, send)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client_host = request.client.host if request.client else None
        if not is_loopback_client(client_host):
            return JSONResponse({"detail": "Local access only"}, status_code=403)

        if request.url.path != "/api/metadata/upload-db":
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > self.max_request_body_bytes:
                        return JSONResponse({"detail": "Request body too large"}, status_code=413)
                except ValueError:
                    return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)

        if request.url.path not in _SQL_PATHS:
            return await call_next(request)

        with self._active_lock:
            if self._active_sql_requests >= self.max_concurrent_sql_requests:
                return JSONResponse({"detail": "SQL service is busy"}, status_code=429)
            self._active_sql_requests += 1

        owns_slot = True

        def release_normal_sql_slot():
            # Both the post-serialization handoff and every unwind path use
            # this request's lease, not a bare decrement of the shared count.
            # No await/cancellation point between testing and giving it back.
            nonlocal owns_slot
            with self._active_lock:
                if owns_slot:
                    self._active_sql_requests -= 1
                    owns_slot = False

        try:
            request.state.release_normal_sql_slot = release_normal_sql_slot
            request.state.sql_deadline = monotonic() + self.sql_timeout_seconds
            return await asyncio.wait_for(
                call_next(request),
                timeout=self.sql_timeout_seconds,
            )
        except asyncio.TimeoutError:
            # Only the opt-in route can install this Response, and only after
            # the ordinary endpoint has returned its serialized 200 JSON body.
            ready = getattr(request.state, "sql_ready_fallback", None)
            if isinstance(ready, Response):
                return ready
            return JSONResponse({"detail": "SQL request timed out"}, status_code=504)
        finally:
            release_normal_sql_slot()
