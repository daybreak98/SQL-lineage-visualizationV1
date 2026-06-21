from __future__ import annotations

import asyncio
import ipaddress

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

MAX_REQUEST_BODY_BYTES = 2 * 1024 * 1024
MAX_SQL_CHARS = 64 * 1024
SQL_TIMEOUT_SECONDS = 30.0
MAX_CONCURRENT_SQL_REQUESTS = 1

_SQL_PATHS = {
    "/api/sql/analyze",
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
        super().__init__(app)
        self.max_request_body_bytes = max_request_body_bytes
        self.sql_timeout_seconds = sql_timeout_seconds
        self.max_concurrent_sql_requests = max_concurrent_sql_requests
        self._active_sql_requests = 0
        self._active_lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client_host = request.client.host if request.client else None
        if not is_loopback_client(client_host):
            return JSONResponse({"detail": "Local access only"}, status_code=403)

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_request_body_bytes:
                    return JSONResponse({"detail": "Request body too large"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)

        if request.url.path not in _SQL_PATHS:
            return await call_next(request)

        async with self._active_lock:
            if self._active_sql_requests >= self.max_concurrent_sql_requests:
                return JSONResponse({"detail": "SQL service is busy"}, status_code=429)
            self._active_sql_requests += 1

        try:
            return await asyncio.wait_for(
                call_next(request),
                timeout=self.sql_timeout_seconds,
            )
        except asyncio.TimeoutError:
            return JSONResponse({"detail": "SQL request timed out"}, status_code=504)
        finally:
            async with self._active_lock:
                self._active_sql_requests -= 1
