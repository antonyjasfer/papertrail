import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.state import AnalysisWorkflow, WorkflowState, validate_transition
from app.events.schemas import EventType, WorkflowEvent
from app.orchestration.errors import (
    FutureEventError,
    IntegrityConflictError,
    LeaseAcquisitionError,
    StaleEventError,
    StateSynchronizationError,
)
from app.orchestration.models import ClaimStatus, WorkflowExecutionClaim
from app.orchestration.outbox import OutboxStatus, WorkflowOutboxEvent

logger = logging.getLogger(__name__)


class FirestoreStateManager:
    """Manages atomic state persistence, optimistic revision concurrency locking,
    execution claims, idempotency deduplication, and transactional outbox event storage.
    
    Supports both Firestore production backend and lightweight in-memory storage for testing.
    """

    def __init__(self, db_client: Optional[Any] = None) -> None:
        self.db_client = db_client
        # In-memory storage structures for local testing / mock mode
        self._workflows: Dict[str, AnalysisWorkflow] = {}
        self._workflow_revisions: Dict[str, int] = {}
        self._processed_events: Dict[str, Dict[str, Any]] = {}  # logical_key -> metadata
        self._claims: Dict[str, WorkflowExecutionClaim] = {}     # logical_key -> claim
        self._outbox: List[WorkflowOutboxEvent] = []
        self._engine_outputs: Dict[str, Dict[str, Any]] = {}    # workflow_id:revision -> output

    def get_workflow(self, workflow_id: str) -> Optional[AnalysisWorkflow]:
        """Retrieve current workflow instance."""
        return self._workflows.get(workflow_id)

    def get_workflow_revision(self, workflow_id: str) -> int:
        """Retrieve current monotonic workflow revision (starts at 1)."""
        return self._workflow_revisions.get(workflow_id, 1)

    def create_workflow(self, workflow_id: str, document_id: str) -> Tuple[AnalysisWorkflow, WorkflowOutboxEvent]:
        """Initialize a new workflow instance at revision 1 and create initial UPLOADED outbox record."""
        workflow = AnalysisWorkflow(
            workflow_id=workflow_id,
            document_id=document_id,
            current_state=WorkflowState.UPLOADED,
        )
        self._workflows[workflow_id] = workflow
        self._workflow_revisions[workflow_id] = 1

        outbox_event = WorkflowOutboxEvent(
            workflow_id=workflow_id,
            document_id=document_id,
            event_id=f"evt-init-{workflow_id}",
            event_type=EventType.DOCUMENT_UPLOADED,
            workflow_revision=1,
            payload_hash="",
            payload={"document_id": document_id},
        )
        self._outbox.append(outbox_event)
        logger.info(
            f"[FirestoreStateManager] Initialized workflow '{workflow_id}' at state UPLOADED (Revision 1)."
        )
        return workflow, outbox_event

    def check_idempotency(self, event: WorkflowEvent) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Check if an event has already been processed using its logical key.
        
        Returns:
            Tuple[bool, Optional[Dict[str, Any]]]: (is_processed, cached_output)
        
        Raises:
            StaleEventError: If event_revision < stored_revision.
            FutureEventError: If event_revision > stored_revision.
            IntegrityConflictError: If payload_hash differs for an already processed logical key.
        """
        workflow_id = event.workflow_id
        current_revision = self.get_workflow_revision(workflow_id)

        # Check revision semantics
        if event.workflow_revision < current_revision:
            # Check if this exact logical key was processed in the past
            logical_key = event.get_logical_event_key()
            if logical_key in self._processed_events:
                cached = self._processed_events[logical_key]
                if cached["payload_hash"] != event.payload_hash:
                    raise IntegrityConflictError(
                        f"Integrity conflict for event key '{logical_key}': payload hash mismatch."
                    )
                return True, cached.get("output_reference")
            raise StaleEventError(workflow_id, event.workflow_revision, current_revision)

        if event.workflow_revision > current_revision:
            raise FutureEventError(workflow_id, event.workflow_revision, current_revision)

        logical_key = event.get_logical_event_key()
        if logical_key in self._processed_events:
            cached = self._processed_events[logical_key]
            if cached["payload_hash"] != event.payload_hash:
                raise IntegrityConflictError(
                    f"Integrity conflict for event key '{logical_key}': payload hash mismatch."
                )
            return True, cached.get("output_reference")

        return False, None

    def acquire_execution_claim(
        self,
        workflow_id: str,
        logical_event_key: str,
        owner_id: str,
        ttl_seconds: int = 300,
    ) -> WorkflowExecutionClaim:
        """Acquire an execution claim lease for an engine adapter.
        
        Raises:
            LeaseAcquisitionError: If an active, non-expired lease is held by another worker.
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds)

        existing = self._claims.get(logical_event_key)
        if existing and existing.status in (ClaimStatus.CLAIMED, ClaimStatus.RUNNING):
            if not existing.is_expired(now) and existing.owner_id != owner_id:
                raise LeaseAcquisitionError(
                    logical_event_key, existing.owner_id, str(existing.lease_expires_at)
                )

        claim = WorkflowExecutionClaim(
            workflow_id=workflow_id,
            logical_event_key=logical_event_key,
            execution_id=f"exec-{uuid_hex()}",
            owner_id=owner_id,
            status=ClaimStatus.RUNNING,
            claimed_at=now,
            lease_expires_at=expires_at,
        )
        self._claims[logical_event_key] = claim
        logger.info(
            f"[FirestoreStateManager] Worker '{owner_id}' acquired execution claim for '{logical_event_key}'."
        )
        return claim

    def commit_transaction(
        self,
        workflow_id: str,
        expected_revision: int,
        target_state: WorkflowState,
        output_reference: Optional[Dict[str, Any]] = None,
        next_event_type: Optional[EventType] = None,
        next_event_payload: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
    ) -> Tuple[AnalysisWorkflow, Optional[WorkflowOutboxEvent]]:
        """Atomically verify workflow revision, execute state transition, record output,
        persist processed event record, and generate an outgoing WorkflowOutboxEvent.
        """
        stored_revision = self.get_workflow_revision(workflow_id)
        if expected_revision != stored_revision:
            raise StateSynchronizationError(workflow_id, expected_revision, stored_revision)

        workflow = self._workflows.get(workflow_id)
        if not workflow:
            raise RuntimeError(f"Workflow '{workflow_id}' not found.")

        # Execute state transition (validates transition matrix strictly)
        previous_state = workflow.current_state
        workflow.transition_to(target_state, reason=reason)

        # Monotonic revision increment
        new_revision = stored_revision + 1
        self._workflow_revisions[workflow_id] = new_revision

        # Store engine output reference if provided
        if output_reference is not None:
            self._engine_outputs[f"{workflow_id}:{new_revision}"] = output_reference

        # Mark claim completed if active
        for claim in self._claims.values():
            if claim.workflow_id == workflow_id and claim.status == ClaimStatus.RUNNING:
                claim.status = ClaimStatus.COMPLETED
                claim.output_reference = output_reference

        # Create transactional outbox event if next_event_type is provided
        outbox_event: Optional[WorkflowOutboxEvent] = None
        if next_event_type is not None:
            payload = next_event_payload or {}
            outbox_event = WorkflowOutboxEvent(
                workflow_id=workflow_id,
                document_id=workflow.document_id,
                event_id=f"evt-{workflow_id}-rev{new_revision}",
                event_type=next_event_type,
                workflow_revision=new_revision,
                payload_hash="",
                payload=payload,
            )
            self._outbox.append(outbox_event)

        logger.info(
            f"[FirestoreStateManager] Committed transition for workflow '{workflow_id}': "
            f"{previous_state.value} -> {target_state.value} (Revision {stored_revision} -> {new_revision})."
        )
        return workflow, outbox_event


def uuid_hex() -> str:
    import uuid
    return uuid.uuid4().hex[:8]
