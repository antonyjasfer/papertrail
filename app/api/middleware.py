"""PaperTrail AI — Production API Observability Middleware.

Provides request timing, automatic correlation ID generation/propagation,
structured request logging, metric recording, and safe error handling for all HTTP traffic.
"""

import logging
import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.errors import classify_error
from app.core.logging import CorrelationContext, log_event
from app.core.metrics import record_api_request

logger = logging.getLogger("papertrail.api")


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """FastAPI Middleware for request tracing, metrics, and structured logging."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()

        # Extract or generate correlation and request IDs
        correlation_id = (
            request.headers.get("X-Correlation-ID")
            or request.headers.get("X-Request-ID")
            or f"corr-{uuid.uuid4().hex[:12]}"
        )
        request_id = f"req-{uuid.uuid4().hex[:8]}"

        # Bind to contextvars
        with CorrelationContext(correlation_id=correlation_id, request_id=request_id):
            log_event(
                logger=logger,
                level=logging.INFO,
                message=f"Incoming HTTP request {request.method} {request.url.path}",
                component="api",
                operation="http_request_received",
                http_method=request.method,
                http_path=request.url.path,
                correlation_id=correlation_id,
                request_id=request_id,
            )

            try:
                response = await call_next(request)
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                duration_sec = duration_ms / 1000.0

                # Record metrics
                record_api_request(
                    endpoint=request.url.path,
                    method=request.method,
                    status_code=response.status_code,
                    duration_seconds=duration_sec,
                )

                # Inject correlation headers on response
                response.headers["X-Correlation-ID"] = correlation_id
                response.headers["X-Request-ID"] = request_id

                log_event(
                    logger=logger,
                    level=logging.INFO if response.status_code < 400 else logging.WARNING,
                    message=f"HTTP response {response.status_code} for {request.method} {request.url.path} in {duration_ms:.2f}ms",
                    component="api",
                    operation="http_request_completed",
                    http_method=request.method,
                    http_path=request.url.path,
                    http_status=response.status_code,
                    duration_ms=duration_ms,
                    outcome="SUCCESS" if response.status_code < 400 else "CLIENT_OR_SERVER_ERROR",
                    correlation_id=correlation_id,
                    request_id=request_id,
                )
                return response

            except Exception as exc:
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                duration_sec = duration_ms / 1000.0
                err_cat = classify_error(exc)

                # Record error metric
                record_api_request(
                    endpoint=request.url.path,
                    method=request.method,
                    status_code=500,
                    duration_seconds=duration_sec,
                )

                log_event(
                    logger=logger,
                    level=logging.ERROR,
                    message=f"Unhandled exception during {request.method} {request.url.path}: {exc}",
                    component="api",
                    operation="http_request_failed",
                    http_method=request.method,
                    http_path=request.url.path,
                    http_status=500,
                    duration_ms=duration_ms,
                    outcome="FAILED",
                    error_category=err_cat.value,
                    error_details=str(exc),
                    correlation_id=correlation_id,
                    request_id=request_id,
                )
                raise exc
