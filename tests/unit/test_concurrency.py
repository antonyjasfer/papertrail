from datetime import datetime, timedelta, timezone
import pytest

from app.core.state import WorkflowState
from app.events.schemas import EventType, WorkflowEvent
from app.orchestration.errors import (
    FutureEventError,
    IntegrityConflictError,
    LeaseAcquisitionError,
    StaleEventError,
    StateSynchronizationError,
)
from app.orchestration.state_manager import FirestoreStateManager


def test_monotonic_revision_optimistic_locking():
    manager = FirestoreStateManager()
    workflow, outbox = manager.create_workflow("wf-sync", "doc-sync")
    assert manager.get_workflow_revision("wf-sync") == 1

    # Attempt transition with wrong revision
    with pytest.raises(StateSynchronizationError):
        manager.commit_transaction(
            workflow_id="wf-sync",
            expected_revision=99,
            target_state=WorkflowState.INGESTING,
        )

    # Correct revision commit succeeds
    updated, new_outbox = manager.commit_transaction(
        workflow_id="wf-sync",
        expected_revision=1,
        target_state=WorkflowState.INGESTING,
        next_event_type=EventType.INGESTION_COMPLETED,
    )
    assert updated.current_state == WorkflowState.INGESTING
    assert manager.get_workflow_revision("wf-sync") == 2


def test_stale_and_future_event_rejection():
    manager = FirestoreStateManager()
    manager.create_workflow("wf-rev", "doc-rev")
    # Current revision is 1

    # Future event (rev 5) raises FutureEventError
    future_event = WorkflowEvent(
        workflow_id="wf-rev",
        document_id="doc-rev",
        event_type=EventType.FORENSICS_COMPLETED,
        current_state="EXTRACTED",
        workflow_revision=5,
        payload={},
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-rev",
    )
    with pytest.raises(FutureEventError):
        manager.check_idempotency(future_event)

    # Advance revision to 2
    manager.commit_transaction("wf-rev", 1, WorkflowState.INGESTING)
    assert manager.get_workflow_revision("wf-rev") == 2

    # Stale event (rev 1) raises StaleEventError
    stale_event = WorkflowEvent(
        workflow_id="wf-rev",
        document_id="doc-rev",
        event_type=EventType.DOCUMENT_UPLOADED,
        current_state="UPLOADED",
        workflow_revision=1,
        payload={},
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-rev",
    )
    with pytest.raises(StaleEventError):
        manager.check_idempotency(stale_event)


def test_execution_claim_contention_and_lease_expiration():
    manager = FirestoreStateManager()

    # Worker A acquires lease
    claim_a = manager.acquire_execution_claim(
        workflow_id="wf-claim",
        logical_event_key="wf-claim:1:INGESTION_COMPLETED",
        owner_id="worker-a",
        ttl_seconds=300,
    )
    assert claim_a.owner_id == "worker-a"

    # Worker B attempting to acquire same active lease fails
    with pytest.raises(LeaseAcquisitionError):
        manager.acquire_execution_claim(
            workflow_id="wf-claim",
            logical_event_key="wf-claim:1:INGESTION_COMPLETED",
            owner_id="worker-b",
            ttl_seconds=300,
        )

    # Simulate lease expiration
    claim_a.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)

    # Worker B can now acquire expired lease
    claim_b = manager.acquire_execution_claim(
        workflow_id="wf-claim",
        logical_event_key="wf-claim:1:INGESTION_COMPLETED",
        owner_id="worker-b",
        ttl_seconds=300,
    )
    assert claim_b.owner_id == "worker-b"
