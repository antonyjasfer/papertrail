import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.contracts.clock import IClock, ProductionClock
from app.core.state import AnalysisWorkflow, WorkflowState
from app.events.schemas import EventType, WorkflowEvent, compute_payload_hash
from app.orchestration.errors import (
    FutureEventError,
    IntegrityConflictError,
    LeaseAcquisitionError,
    StaleEventError,
    StateSynchronizationError,
)
from app.orchestration.models import ClaimStatus, WorkflowExecutionClaim
from app.orchestration.outbox import WorkflowOutboxEvent

logger = logging.getLogger("papertrail.mock.state_manager")


class InMemoryStateManager:
    """In-memory state manager for isolated unit testing and mock mode without cloud credentials.
    
    Implements IWorkflowStateManager protocol.
    """

    def __init__(self, clock: Optional[IClock] = None) -> None:
        self.clock = clock or ProductionClock()
        self._workflows: Dict[str, AnalysisWorkflow] = {}
        self._workflow_revisions: Dict[str, int] = {}
        self._processed_events: Dict[str, Dict[str, Any]] = {}
        self._claims: Dict[str, WorkflowExecutionClaim] = {}
        self._outbox: List[WorkflowOutboxEvent] = []
        self._engine_outputs: Dict[str, Dict[str, Any]] = {}

    def get_workflow(self, workflow_id: str) -> Optional[AnalysisWorkflow]:
        return self._workflows.get(workflow_id)

    def get_workflow_revision(self, workflow_id: str) -> int:
        return self._workflow_revisions.get(workflow_id, 1)

    def create_workflow(
        self, workflow_id: str, document_id: str
    ) -> Tuple[AnalysisWorkflow, WorkflowOutboxEvent]:
        workflow = AnalysisWorkflow(
            workflow_id=workflow_id,
            document_id=document_id,
            current_state=WorkflowState.UPLOADED,
            created_at=self.clock.now_utc(),
            updated_at=self.clock.now_utc(),
        )
        self._workflows[workflow_id] = workflow
        self._workflow_revisions[workflow_id] = 1

        payload = {"document_id": document_id}
        outbox_event = WorkflowOutboxEvent(
            workflow_id=workflow_id,
            document_id=document_id,
            event_id=f"evt-init-{workflow_id}",
            event_type=EventType.DOCUMENT_UPLOADED,
            workflow_revision=1,
            payload_hash=compute_payload_hash(payload),
            payload=payload,
            created_at=self.clock.now_utc(),
        )
        self._outbox.append(outbox_event)
        logger.info(
            "[InMemoryStateManager] Initialized workflow '%s' at state UPLOADED (Revision 1).",
            workflow_id,
        )
        return workflow, outbox_event

    def check_idempotency(
        self, event: WorkflowEvent
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        workflow_id = event.workflow_id
        current_revision = self.get_workflow_revision(workflow_id)
        logical_key = event.logical_event_key if hasattr(event, "logical_event_key") and event.logical_event_key else event.get_logical_event_key()

        if event.workflow_revision < current_revision:
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
        now = self.clock.now_utc()
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
            execution_id=f"exec-{uuid.uuid4().hex[:8]}",
            owner_id=owner_id,
            status=ClaimStatus.RUNNING,
            claimed_at=now,
            lease_expires_at=expires_at,
        )
        self._claims[logical_event_key] = claim
        logger.info(
            "[InMemoryStateManager] Worker '%s' acquired execution claim for '%s'.",
            owner_id,
            logical_event_key,
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
        stored_revision = self.get_workflow_revision(workflow_id)
        if expected_revision != stored_revision:
            raise StateSynchronizationError(workflow_id, expected_revision, stored_revision)

        workflow = self._workflows.get(workflow_id)
        if not workflow:
            raise RuntimeError(f"Workflow '{workflow_id}' not found.")

        previous_state = workflow.current_state
        workflow.transition_to(target_state, reason=reason)

        new_revision = stored_revision + 1
        self._workflow_revisions[workflow_id] = new_revision

        if output_reference is not None:
            self._engine_outputs[f"{workflow_id}:{new_revision}"] = output_reference

        # Mark active claim completed and write idempotency record using claim's logical_event_key
        for claim in self._claims.values():
            if claim.workflow_id == workflow_id and claim.status == ClaimStatus.RUNNING:
                claim.status = ClaimStatus.COMPLETED
                claim.output_reference = output_reference
                self._processed_events[claim.logical_event_key] = {
                    "event_id": getattr(claim, "event_id", f"evt-{workflow_id}-{stored_revision}"),
                    "logical_event_key": claim.logical_event_key,
                    "payload_hash": getattr(claim, "payload_hash", ""),
                    "workflow_id": workflow_id,
                    "workflow_revision": stored_revision,
                    "output_reference": output_reference,
                    "processed_at": self.clock.now_utc().isoformat(),
                }

        outbox_event: Optional[WorkflowOutboxEvent] = None
        if next_event_type is not None:
            payload = next_event_payload or {}
            outbox_event = WorkflowOutboxEvent(
                workflow_id=workflow_id,
                document_id=workflow.document_id,
                event_id=f"evt-{workflow_id}-rev{new_revision}",
                event_type=next_event_type,
                workflow_revision=new_revision,
                payload_hash=compute_payload_hash(payload),
                payload=payload,
                created_at=self.clock.now_utc(),
            )
            self._outbox.append(outbox_event)

        logger.info(
            "[InMemoryStateManager] Committed transition for '%s': %s -> %s (Rev %d -> %d).",
            workflow_id,
            previous_state.value,
            target_state.value,
            stored_revision,
            new_revision,
        )
        return workflow, outbox_event
