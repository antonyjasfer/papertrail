from datetime import datetime, timezone
from decimal import Decimal
import hashlib

from app.audit.constants import GENESIS_PREVIOUS_HASH
from app.audit.hashing import compute_event_hash, compute_hash, compute_payload_hash
from app.audit.models import AuditEvent, AuditEventType, AuditProvenance


def test_compute_hash_basic():
    data = b"papertrail-ai-test"
    expected = hashlib.sha256(data).hexdigest()
    assert compute_hash(data) == expected


def test_compute_payload_hash_field_order_independence():
    payload_1 = {"b": Decimal("100.00"), "a": "vendor_name"}
    payload_2 = {"a": "vendor_name", "b": Decimal("100.00")}
    assert compute_payload_hash(payload_1) == compute_payload_hash(payload_2)


def test_compute_event_hash_deterministic():
    ts = datetime(2026, 8, 18, 18, 46, 12, 123456, tzinfo=timezone.utc)
    event = AuditEvent(
        event_id="evt-001",
        document_id="doc-123",
        workflow_id="wf-456",
        event_type=AuditEventType.DOCUMENT_REGISTERED,
        event_timestamp=ts,
        schema_version="1.0.0",
        source_phase="Phase 5",
        payload_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        previous_event_hash=GENESIS_PREVIOUS_HASH,
        event_hash="",  # To be populated
        provenance=AuditProvenance(app_version="0.1.0"),
    )
    event_hash_1 = compute_event_hash(event)
    event_hash_2 = compute_event_hash(event)
    assert event_hash_1 == event_hash_2
    assert len(event_hash_1) == 64
