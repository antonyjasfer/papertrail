import logging
from typing import Any, Dict, Optional, Tuple

from app.core.config import settings
from app.core.state import AnalysisWorkflow, WorkflowState, validate_transition
from app.events.publisher import BasePublisher, MockPubSubPublisher
from app.events.schemas import EventType, WorkflowEvent
from app.orchestration.adapters.audit_adapter import AuditAdapter
from app.orchestration.adapters.base import BaseEngineAdapter, FailureClassification
from app.orchestration.adapters.compliance_adapter import ComplianceAdapter
from app.orchestration.adapters.doc_intel_adapter import DocIntelAdapter
from app.orchestration.adapters.forensic_adapter import ForensicAdapter
from app.orchestration.adapters.report_adapter import ReportAdapter
from app.orchestration.adapters.risk_adapter import RiskAdapter
from app.orchestration.errors import (
    FutureEventError,
    IntegrityConflictError,
    LeaseAcquisitionError,
    StaleEventError,
    StateSynchronizationError,
    UnauthorizedReviewerError,
)
from app.core.contracts.state_manager import IWorkflowStateManager
from app.infrastructure.factory import get_event_publisher, get_state_manager
from app.orchestration.models import HumanReviewPayload
from app.orchestration.outbox import OutboxPublisherWorker, WorkflowOutboxEvent

logger = logging.getLogger(__name__)


# Mapping of operational state to target operational state & next event type
STAGE_TRANSITION_MAP: Dict[WorkflowState, Tuple[WorkflowState, EventType]] = {
    WorkflowState.UPLOADED: (WorkflowState.INGESTING, EventType.INGESTION_COMPLETED),
    WorkflowState.INGESTING: (WorkflowState.EXTRACTING, EventType.EXTRACTION_COMPLETED),
    WorkflowState.EXTRACTING: (WorkflowState.EXTRACTED, EventType.ANALYSIS_TRIGGERED),
    WorkflowState.EXTRACTED: (WorkflowState.FORENSIC_ANALYSIS, EventType.FORENSICS_COMPLETED),
    WorkflowState.FORENSIC_ANALYSIS: (WorkflowState.COMPLIANCE_ANALYSIS, EventType.COMPLIANCE_COMPLETED),
    WorkflowState.COMPLIANCE_ANALYSIS: (WorkflowState.RISK_ASSESSED, EventType.RISK_COMPLETED),
    WorkflowState.RISK_ASSESSED: (WorkflowState.AUDIT_SEALED, EventType.AUDIT_COMPLETED),
    WorkflowState.AUDIT_SEALED: (WorkflowState.REPORT_GENERATED, EventType.REPORT_COMPLETED),
    WorkflowState.REPORT_GENERATED: (WorkflowState.COMPLETED, EventType.REPORT_COMPLETED),
}


class WorkflowOrchestrator:
    """Central Workflow Orchestrator for PaperTrail AI.
    
    Coordinates document analysis lifecycle across deterministic phase engines (Phases 7-12).
    Maintains sole state transition authority using IWorkflowStateManager and atomic transactions.
    """

    def __init__(
        self,
        state_manager: Optional[IWorkflowStateManager] = None,
        publisher: Optional[BasePublisher] = None,
        max_retries: int = 3,
        owner_id: str = "orchestrator-worker-1",
    ) -> None:
        self.state_manager = state_manager or get_state_manager()
        self.publisher = publisher or get_event_publisher()
        self.outbox_worker = OutboxPublisherWorker(self.publisher, max_retries=max_retries)
        self.max_retries = max_retries
        self.owner_id = owner_id

        # Register engine adapters
        self.adapters: Dict[WorkflowState, BaseEngineAdapter] = {
            WorkflowState.INGESTING: DocIntelAdapter(),
            WorkflowState.EXTRACTING: DocIntelAdapter(),
            WorkflowState.FORENSIC_ANALYSIS: ForensicAdapter(),
            WorkflowState.COMPLIANCE_ANALYSIS: ComplianceAdapter(),
            WorkflowState.RISK_ASSESSED: RiskAdapter(),
            WorkflowState.AUDIT_SEALED: AuditAdapter(),
            WorkflowState.REPORT_GENERATED: ReportAdapter(),
        }

    def start_workflow(self, workflow_id: str, document_id: str) -> Tuple[AnalysisWorkflow, WorkflowOutboxEvent]:
        """Initialize a new pipeline workflow and publish initial UPLOADED outbox event."""
        workflow, outbox_event = self.state_manager.create_workflow(workflow_id, document_id)
        self.outbox_worker.add_outbox_event(outbox_event)
        self.outbox_worker.process_pending()
        return workflow, outbox_event

    def dispatch(self, event: WorkflowEvent) -> Tuple[AnalysisWorkflow, Optional[WorkflowOutboxEvent]]:
        """Process an incoming WorkflowEvent envelope idempotently and execute stage logic.
        
        Returns:
            Tuple[AnalysisWorkflow, Optional[WorkflowOutboxEvent]]: Updated workflow & generated outbox event.
        """
        workflow_id = event.workflow_id
        logger.info(
            f"[WorkflowOrchestrator] Dispatching event '{event.event_type.value}' "
            f"for workflow '{workflow_id}' (Rev {event.workflow_revision})."
        )

        # Step 1: Check idempotency & revision bounds
        try:
            is_processed, cached_output = self.state_manager.check_idempotency(event)
            if is_processed:
                logger.info(
                    f"[WorkflowOrchestrator] Event '{event.get_logical_event_key()}' already processed. Returning cached result."
                )
                workflow = self.state_manager.get_workflow(workflow_id)
                return workflow, None
        except StaleEventError as stale_err:
            logger.info(f"[WorkflowOrchestrator] Dropping stale event: {stale_err}")
            workflow = self.state_manager.get_workflow(workflow_id)
            return workflow, None

        # Step 2: Retrieve workflow state
        workflow = self.state_manager.get_workflow(workflow_id)
        if not workflow:
            raise RuntimeError(f"Workflow '{workflow_id}' not found.")

        current_state = workflow.current_state

        # Terminal state check
        if current_state in (WorkflowState.COMPLETED, WorkflowState.FAILED, WorkflowState.ESCALATED):
            logger.warning(
                f"[WorkflowOrchestrator] Workflow '{workflow_id}' is in terminal state '{current_state.value}'. Rejecting dispatch."
            )
            return workflow, None

        # Step 3: Acquire worker execution claim lease
        logical_key = event.get_logical_event_key()
        self.state_manager.acquire_execution_claim(
            workflow_id=workflow_id,
            logical_event_key=logical_key,
            owner_id=self.owner_id,
            ttl_seconds=settings.lease_ttl_seconds,
        )

        # Step 4: Determine next operational state target
        next_target, next_event_type = STAGE_TRANSITION_MAP.get(
            current_state, (WorkflowState.COMPLETED, EventType.REPORT_COMPLETED)
        )

        # Step 5: Execute adapter if stage requires engine processing
        adapter = self.adapters.get(current_state)
        adapter_result = None

        if adapter:
            adapter_result = adapter.execute(
                workflow_id=workflow_id,
                document_id=event.document_id,
                payload=event.payload,
            )

        # Step 6: Evaluate AdapterResult & determine atomic transaction target
        if adapter and not adapter_result.success:
            classification = adapter_result.failure_classification
            if classification == FailureClassification.REQUIRES_REVIEW:
                target_state = WorkflowState.REQUIRES_REVIEW
                reason = adapter_result.failure_reason or "Adapter requested human review."
                next_evt = EventType.REVIEW_REQUESTED
            elif classification == FailureClassification.NON_RETRYABLE:
                target_state = WorkflowState.FAILED
                reason = adapter_result.failure_reason or "Non-retryable engine error."
                next_evt = EventType.WORKFLOW_FAILED
            else:  # RETRYABLE
                if event.attempt_number >= self.max_retries:
                    target_state = WorkflowState.ESCALATED
                    reason = f"Exhausted {self.max_retries} retries: {adapter_result.failure_reason}"
                    next_evt = EventType.WORKFLOW_ESCALATED
                else:
                    # Retry cleanly by re-enqueuing same state event
                    target_state = current_state
                    reason = f"Retry attempt {event.attempt_number}: {adapter_result.failure_reason}"
                    next_evt = event.event_type
        else:
            target_state = next_target
            reason = None
            next_evt = next_event_type

        # Step 7: Atomic Firestore Transaction commit
        output_ref = adapter_result.output_reference if adapter_result else None
        next_payload = {"document_id": event.document_id, "previous_output": output_ref} if output_ref else {"document_id": event.document_id}

        updated_workflow, outbox_event = self.state_manager.commit_transaction(
            workflow_id=workflow_id,
            expected_revision=event.workflow_revision,
            target_state=target_state,
            output_reference=output_ref,
            next_event_type=next_evt if target_state not in (WorkflowState.COMPLETED, WorkflowState.FAILED, WorkflowState.ESCALATED) else None,
            next_event_payload=next_payload,
            reason=reason,
        )

        # Step 8: Dispatch outbox worker
        if outbox_event:
            self.outbox_worker.add_outbox_event(outbox_event)
            self.outbox_worker.process_pending()

        return updated_workflow, outbox_event

    def resume_workflow(
        self,
        workflow_id: str,
        payload: HumanReviewPayload,
        reviewer_principal: str,
    ) -> Tuple[AnalysisWorkflow, Optional[WorkflowOutboxEvent]]:
        """Resume a workflow stalled in REQUIRES_REVIEW state after human review approval.
        
        Validates reviewer authentication principal and verifies requested target state
        against VALID_TRANSITIONS rules in app/core/state.py.
        """
        if not reviewer_principal or not isinstance(reviewer_principal, str):
            raise UnauthorizedReviewerError("Reviewer principal is unauthenticated or missing.")

        workflow = self.state_manager.get_workflow(workflow_id)
        if not workflow:
            raise RuntimeError(f"Workflow '{workflow_id}' not found.")

        if workflow.current_state != WorkflowState.REQUIRES_REVIEW:
            raise RuntimeError(
                f"Workflow '{workflow_id}' is in state '{workflow.current_state.value}', not REQUIRES_REVIEW."
            )

        # Parse requested target state
        try:
            target_enum = WorkflowState(payload.requested_target)
        except ValueError:
            raise RuntimeError(f"Requested target state '{payload.requested_target}' is invalid.")

        # Validate transition strictly using central state machine
        validate_transition(workflow.current_state, target_enum)

        current_rev = self.state_manager.get_workflow_revision(workflow_id)
        next_evt = EventType.ANALYSIS_TRIGGERED

        updated_workflow, outbox_event = self.state_manager.commit_transaction(
            workflow_id=workflow_id,
            expected_revision=current_rev,
            target_state=target_enum,
            output_reference={"human_review": payload.model_dump(mode="json"), "reviewer": reviewer_principal},
            next_event_type=next_evt,
            next_event_payload={"document_id": workflow.document_id, "review_id": payload.review_id},
            reason=f"Human review decision: {payload.decision.value} by {reviewer_principal}",
        )

        if outbox_event:
            self.outbox_worker.add_outbox_event(outbox_event)
            self.outbox_worker.process_pending()

        logger.info(
            f"[WorkflowOrchestrator] Resumed workflow '{workflow_id}' to state '{target_enum.value}' "
            f"by reviewer '{reviewer_principal}'."
        )
        return updated_workflow, outbox_event
