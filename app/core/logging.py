"""PaperTrail AI — Production Structured Logging and Correlation Layer.

Provides machine-readable JSON logging, automatic correlation context propagation,
and sensitive data redaction filters to prevent credential or PII leaks in production logs.
"""

import contextvars
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Context variable for request / workflow correlation
_correlation_ctx: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar(
    "correlation_ctx", default={}
)

# Patterns for sensitive credential redaction
SENSITIVE_PATTERNS = [
    re.compile(r"(bearer\s+)[a-zA-Z0-9_\-\.]{20,}", re.IGNORECASE),
    re.compile(r"(sig=)[a-zA-Z0-9%_\-\.]{20,}", re.IGNORECASE),
    re.compile(r"(AccountKey=)[a-zA-Z0-9+/=]{20,}", re.IGNORECASE),
    re.compile(r"(SharedAccessKey=)[a-zA-Z0-9+/=]{20,}", re.IGNORECASE),
    re.compile(r"(password[\"']?\s*[:=]\s*[\"']?)[^\"'\s]+", re.IGNORECASE),
    re.compile(r"(client_secret[\"']?\s*[:=]\s*[\"']?)[^\"'\s]+", re.IGNORECASE),
    re.compile(r"(api[_-]?key[\"']?\s*[:=]\s*[\"']?)[a-zA-Z0-9_\-]{16,}", re.IGNORECASE),
]

SENSITIVE_KEYS = {
    "password",
    "secret",
    "token",
    "access_token",
    "api_key",
    "apikey",
    "client_secret",
    "account_key",
    "shared_access_key",
    "connection_string",
    "azure_cosmos_key",
    "azure_storage_connection_string",
    "azure_servicebus_connection_string",
    "gemini_api_key",
}


def sanitize_value(val: Any) -> Any:
    """Sanitize string values against known secret patterns."""
    if isinstance(val, str):
        sanitized = val
        for pat in SENSITIVE_PATTERNS:
            sanitized = pat.sub(r"\1[REDACTED]", sanitized)
        return sanitized
    elif isinstance(val, dict):
        return {
            k: ("[REDACTED]" if k.lower() in SENSITIVE_KEYS else sanitize_value(v))
            for k, v in val.items()
        }
    elif isinstance(val, list):
        return [sanitize_value(elem) for elem in val]
    return val


class CorrelationContext:
    """Context manager for setting correlation attributes (workflow_id, document_id, etc.)."""

    def __init__(self, **kwargs: Any) -> None:
        self.new_ctx = {k: v for k, v in kwargs.items() if v is not None}
        self.token: Optional[contextvars.Token] = None

    def __enter__(self) -> "CorrelationContext":
        current = _correlation_ctx.get().copy()
        current.update(self.new_ctx)
        self.token = _correlation_ctx.set(current)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.token is not None:
            _correlation_ctx.reset(self.token)


def get_current_correlation() -> Dict[str, Any]:
    """Retrieve current ambient correlation context."""
    return _correlation_ctx.get().copy()


def set_correlation_context(**kwargs: Any) -> None:
    """Update ambient correlation context."""
    current = _correlation_ctx.get().copy()
    for k, v in kwargs.items():
        if v is not None:
            current[k] = v
    _correlation_ctx.set(current)


class StructuredJsonFormatter(logging.Formatter):
    """Production JSON log formatter emitting machine-readable structured events."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp_str = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        
        # Base log fields
        log_entry: Dict[str, Any] = {
            "timestamp": timestamp_str,
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Merge correlation context
        ctx = _correlation_ctx.get()
        if ctx:
            log_entry.update(ctx)

        # Merge extra attributes from LogRecord
        if hasattr(record, "structured_data") and isinstance(record.structured_data, dict):
            log_entry.update(record.structured_data)

        for key in (
            "component",
            "operation",
            "workflow_id",
            "document_id",
            "adapter",
            "event_type",
            "current_state",
            "target_state",
            "workflow_revision",
            "claim_id",
            "idempotency_key",
            "retry_count",
            "duration_ms",
            "outcome",
            "error_category",
            "error_details",
            "http_method",
            "http_path",
            "http_status",
            "correlation_id",
            "request_id",
        ):
            if hasattr(record, key) and getattr(record, key) is not None:
                log_entry[key] = getattr(record, key)

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Redact any sensitive content
        sanitized_entry = sanitize_value(log_entry)
        return json.dumps(sanitized_entry, default=str)


def setup_structured_logging(level: str = "INFO") -> None:
    """Configure root logger with StructuredJsonFormatter."""
    root_logger = logging.getLogger()
    log_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers
    has_structured = False
    for handler in list(root_logger.handlers):
        if isinstance(handler.formatter, StructuredJsonFormatter):
            has_structured = True
        else:
            root_logger.removeHandler(handler)

    if not has_structured:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredJsonFormatter())
        root_logger.addHandler(handler)


def log_event(
    logger: logging.Logger,
    level: int,
    message: str,
    component: str,
    operation: str,
    workflow_id: Optional[str] = None,
    document_id: Optional[str] = None,
    outcome: str = "SUCCESS",
    duration_ms: Optional[float] = None,
    error_category: Optional[str] = None,
    error_details: Optional[str] = None,
    **extra_fields: Any,
) -> None:
    """Helper to emit standard machine-readable structured log entries."""
    extra: Dict[str, Any] = {
        "component": component,
        "operation": operation,
        "outcome": outcome,
    }
    if workflow_id:
        extra["workflow_id"] = workflow_id
    if document_id:
        extra["document_id"] = document_id
    if duration_ms is not None:
        extra["duration_ms"] = round(duration_ms, 2)
    if error_category:
        extra["error_category"] = error_category
    if error_details:
        extra["error_details"] = error_details

    extra.update(extra_fields)
    logger.log(level, message, extra={"structured_data": extra})
