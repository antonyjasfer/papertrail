import hashlib
from typing import Any

from app.audit.canonical import canonicalize, canonicalize_datetime
from app.audit.models import AuditEvent


def compute_hash(data: bytes) -> str:
    """Compute SHA-256 lower-case hex digest over raw bytes."""
    return hashlib.sha256(data).hexdigest()


def compute_payload_hash(payload: Any) -> str:
    """Compute SHA-256 lower-case hex digest over canonicalized payload representation."""
    canonical_bytes = canonicalize(payload)
    return compute_hash(canonical_bytes)


def compute_event_hash(event: AuditEvent) -> str:
    """Compute SHA-256 event digest over canonical event fields.
    
    Ordered input structure:
    - schema_version
    - event_id
    - document_id
    - workflow_id
    - event_type
    - event_timestamp (microsecond-precise UTC ISO-8601 string)
    - source_phase
    - payload_hash
    - previous_event_hash
    """
    hash_input = {
        "event_id": event.event_id,
        "document_id": event.document_id,
        "workflow_id": event.workflow_id,
        "event_type": event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
        "event_timestamp": canonicalize_datetime(event.event_timestamp),
        "schema_version": event.schema_version,
        "source_phase": event.source_phase,
        "payload_hash": event.payload_hash,
        "previous_event_hash": event.previous_event_hash,
    }
    canonical_bytes = canonicalize(hash_input)
    return compute_hash(canonical_bytes)
