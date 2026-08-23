from datetime import datetime, timezone
import pytest
from app.events.publisher import MockPubSubPublisher
from app.events.schemas import EventType
from app.orchestration.outbox import OutboxPublisherWorker, OutboxStatus, WorkflowOutboxEvent


def test_outbox_event_conversion():
    outbox = WorkflowOutboxEvent(
        workflow_id="wf-100",
        document_id="doc-100",
        event_id="evt-100",
        event_type=EventType.FORENSICS_COMPLETED,
        workflow_revision=5,
        payload_hash="hash-123",
        payload={"result": "ok"},
    )
    event = outbox.to_workflow_event(correlation_id="corr-100")
    assert event.event_id == "evt-100"
    assert event.workflow_revision == 5
    assert event.correlation_id == "corr-100"


def test_outbox_publisher_worker_dispatch():
    publisher = MockPubSubPublisher()
    worker = OutboxPublisherWorker(publisher=publisher)

    outbox = WorkflowOutboxEvent(
        workflow_id="wf-101",
        document_id="doc-101",
        event_id="evt-101",
        event_type=EventType.COMPLIANCE_COMPLETED,
        workflow_revision=6,
        payload_hash="hash-456",
        payload={},
    )
    worker.add_outbox_event(outbox)
    assert outbox.status == OutboxStatus.PENDING

    count = worker.process_pending()
    assert count == 1
    assert outbox.status == OutboxStatus.PUBLISHED
    assert len(publisher.published_events) == 1
