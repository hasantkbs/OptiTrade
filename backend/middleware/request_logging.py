"""
OptiTrade — Request Logging Middleware
========================================
Attaches a unique request_id to every request and logs:
  - incoming request (method, path, client IP)
  - outgoing response (status code, duration in ms)

The request_id is also returned in the X-Request-ID response header so
mobile clients can include it in bug reports.
"""
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("optitrade.request")

# Paths that are too noisy to log at INFO (logged at DEBUG instead)
_SILENT_PATHS = {"/health", "/", "/ml/status"}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())[:8]
        start = time.monotonic()

        # Make request_id available to downstream handlers via request.state
        request.state.request_id = request_id

        path    = request.url.path
        method  = request.method
        client  = request.client.host if request.client else "unknown"
        level   = logging.DEBUG if path in _SILENT_PATHS else logging.INFO

        logger.log(level, "→ %s %s", method, path, extra={
            "request_id": request_id,
            "method":     method,
            "path":       path,
            "client":     client,
        })

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.monotonic() - start) * 1000, 1)
            logger.error("✗ %s %s crashed in %.1fms", method, path, duration_ms, extra={
                "request_id": request_id,
                "method":     method,
                "path":       path,
                "duration_ms": duration_ms,
            }, exc_info=exc)
            raise

        duration_ms = round((time.monotonic() - start) * 1000, 1)
        status      = response.status_code

        log_level = (
            logging.ERROR   if status >= 500 else
            logging.WARNING if status >= 400 else
            level
        )
        logger.log(log_level, "← %s %s %d %.1fms", method, path, status, duration_ms, extra={
            "request_id":  request_id,
            "method":      method,
            "path":        path,
            "status_code": status,
            "duration_ms": duration_ms,
        })

        response.headers["X-Request-ID"] = request_id
        return response
