"""PaperTrail AI — Operational Error Taxonomy and Classification System.

Provides standard error categories, structured error models, and classification helpers
for production monitoring, alerting, structured logging, and root-cause analysis.
"""

from enum import Enum
from typing import Any, Dict, Optional


class ErrorCategory(str, Enum):
    """Standardized operational error categories for PaperTrail AI."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    TRANSIENT_DEPENDENCY_ERROR = "TRANSIENT_DEPENDENCY_ERROR"
    PERMANENT_PROCESSING_ERROR = "PERMANENT_PROCESSING_ERROR"
    STATE_TRANSITION_ERROR = "STATE_TRANSITION_ERROR"
    CLAIM_CONFLICT = "CLAIM_CONFLICT"
    IDEMPOTENCY_DUPLICATE = "IDEMPOTENCY_DUPLICATE"
    SERVICE_BUS_ERROR = "SERVICE_BUS_ERROR"
    COSMOS_ERROR = "COSMOS_ERROR"
    BLOB_STORAGE_ERROR = "BLOB_STORAGE_ERROR"
    REPORT_GENERATION_ERROR = "REPORT_GENERATION_ERROR"
    AUDIT_ERROR = "AUDIT_ERROR"
    WORKER_RUNTIME_ERROR = "WORKER_RUNTIME_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class OperationalError(Exception):
    """Structured base exception with operational category and context."""

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN_ERROR,
        retryable: bool = False,
        workflow_id: Optional[str] = None,
        document_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.category = category
        self.retryable = retryable
        self.workflow_id = workflow_id
        self.document_id = document_id
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_message": self.message,
            "error_category": self.category.value,
            "retryable": self.retryable,
            "workflow_id": self.workflow_id,
            "document_id": self.document_id,
            "details": self.details,
        }


def classify_error(exc: BaseException) -> ErrorCategory:
    """Deterministically map any exception to its standard operational error category."""
    if isinstance(exc, OperationalError):
        return exc.category

    exc_name = type(exc).__name__
    exc_msg = str(exc).lower()

    if "validation" in exc_name.lower() or "valueerror" in exc_name.lower():
        return ErrorCategory.VALIDATION_ERROR
    if "leaseacquisition" in exc_name.lower() or "claim" in exc_msg:
        return ErrorCategory.CLAIM_CONFLICT
    if "integrityconflict" in exc_name.lower() or "staleevent" in exc_name.lower() or "futureevent" in exc_name.lower():
        return ErrorCategory.IDEMPOTENCY_DUPLICATE
    if "statesynchronization" in exc_name.lower() or "transition" in exc_msg:
        return ErrorCategory.STATE_TRANSITION_ERROR
    if "cosmos" in exc_name.lower() or "cosmos" in exc_msg:
        return ErrorCategory.COSMOS_ERROR
    if "servicebus" in exc_name.lower() or "service_bus" in exc_msg:
        return ErrorCategory.SERVICE_BUS_ERROR
    if "blob" in exc_name.lower() or "storage" in exc_msg or "blob" in exc_msg:
        return ErrorCategory.BLOB_STORAGE_ERROR
    if "report" in exc_name.lower() or "report" in exc_msg:
        return ErrorCategory.REPORT_GENERATION_ERROR
    if "audit" in exc_name.lower() or "hash" in exc_msg:
        return ErrorCategory.AUDIT_ERROR
    if "timeout" in exc_msg or "connection" in exc_msg or "unavailable" in exc_msg or "rate" in exc_msg:
        return ErrorCategory.TRANSIENT_DEPENDENCY_ERROR

    return ErrorCategory.UNKNOWN_ERROR
