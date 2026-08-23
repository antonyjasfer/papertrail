from datetime import datetime, timezone
import pytest
from app.events.schemas import EventType, WorkflowEvent, compute_payload_hash
from app.events.publisher import MockPubSubPublisher
from app.events.subscriber import MockPubSubSubscriber


def test_payload_hash_computation():
    payload_a = {"document_id": "doc-123", "amount": 100}
    payload_b = {"amount": 100, "document_id": "doc-123"}
    hash_a = compute_payload_hash(payload_a)
    hash_b = compute_payload_hash(payload_b)
    assert hash_a == hash_b
    assert len(hash_a) == 64


def test_workflow_event_logical_key():
    dt = datetime.now(timezone.utc)
    event = WorkflowEvent(
        workflow_id="wf-001",
        document_id="doc-123",
        event_type=EventType.DOCUMENT_UPLOADED,
        current_state="UPLOADED",
        workflow_revision=1,
        payload={"document_id": "doc-123"},
        event_timestamp=dt,
        correlation_id="corr-1",
    )
    assert event.get_logical_event_key() == "wf-001:1:DOCUMENT_UPLOADED"
    assert event.payload_hash != ""


def test_mock_publisher_and_subscriber():
    publisher = MockPubSubPublisher()
    subscriber = MockPubSubSubscriber()

    received = []
    subscriber.listen(lambda evt: received.append(evt))

    event = WorkflowEvent(
        workflow_id="wf-001",
        document_id="doc-123",
        event_type=EventType.INGESTION_COMPLETED,
        current_state="INGESTING",
        workflow_revision=2,
        payload={},
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-1",
    )

    publisher.publish(event)
    assert len(publisher.published_events) == 1

    subscriber.simulate_event(event)
    assert len(received) == 1
    assert received[0].workflow_id == "wf-001"
