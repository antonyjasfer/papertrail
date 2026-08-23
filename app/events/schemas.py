import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
import uuid
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Event types emitted during the workflow pipeline lifecycle."""

    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    INGESTION_COMPLETED = "INGESTION_COMPLETED"
    EXTRACTION_COMPLETED = "EXTRACTION_COMPLETED"
    ANALYSIS_TRIGGERED = "ANALYSIS_TRIGGERED"
    FORENSICS_COMPLETED = "FORENSICS_COMPLETED"
    COMPLIANCE_COMPLETED = "COMPLIANCE_COMPLETED"
    RISK_COMPLETED = "RISK_COMPLETED"
    AUDIT_COMPLETED = "AUDIT_COMPLETED"
    REPORT_COMPLETED = "REPORT_COMPLETED"
    WORKFLOW_FAILED = "WORKFLOW_FAILED"
    WORKFLOW_ESCALATED = "WORKFLOW_ESCALATED"
    REVIEW_REQUESTED = "REVIEW_REQUESTED"


def compute_payload_hash(payload: Dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash of a payload dictionary."""
    canonical_str = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


class WorkflowEvent(BaseModel):
    """Canonical event envelope transported across Pub/Sub stages.
    
    Note: `workflow_revision` is the authoritative state ordering mechanism.
    `event_timestamp` is strictly an explicit metadata timestamp.
    """

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    document_id: str
    event_type: EventType
    current_state: str
    target_state: Optional[str] = None
    workflow_revision: int  # Authoritative monotonic state revision counter
    payload_hash: str = ""   # SHA-256 digest of payload
    payload: Dict[str, Any] = Field(default_factory=dict)
    event_timestamp: datetime  # Explicit caller-supplied metadata timestamp
    correlation_id: str
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    attempt_number: int = 1

    def model_post_init(self, __context: Any) -> None:
        """Compute payload_hash automatically if not populated."""
        if not self.payload_hash and self.payload is not None:
            self.payload_hash = compute_payload_hash(self.payload)

    def get_logical_event_key(self) -> str:
        """Return the unique logical key for idempotency deduplication."""
        return f"{self.workflow_id}:{self.workflow_revision}:{self.event_type.value}"
