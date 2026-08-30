import logging
import time
from typing import Any, Dict, Optional, Tuple

from app.core.config import settings
from app.core.contracts.state_manager import IWorkflowStateManager
from app.core.errors import ErrorCategory
from app.core.logging import CorrelationContext, log_event
from app.core.metrics import (
    record_adapter_execution,
    record_claim_conflict,
    record_idempotency_duplicate,
    record_retry,
    record_workflow_complete,
    record_workflow_escalated,
    record_workflow_failed,
    record_workflow_start,
)
from app.core.state import AnalysisWorkflow, WorkflowState, validate_transition
from app.events.publisher import BasePublisher
from app.events.schemas import EventType, WorkflowEvent
from app.infrastructure.factory import get_event_publisher, get_state_manager
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
from app.orchestration.models import HumanReviewPayload
from app.orchestration.outbox import OutboxPublisherWorker, WorkflowOutboxEvent

logger = logging.getLogger("papertrail.orchestrator")


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
        with CorrelationContext(workflow_id=workflow_id, document_id=document_id):
            log_event(
                logger=logger,
                level=logging.INFO,
                message=f"Initializing workflow '{workflow_id}' for document '{document_id}'",
                component="orchestrator",
                operation="start_workflow",
                workflow_id=workflow_id,
                document_id=document_id,
                current_state=WorkflowState.UPLOADED.value,
                workflow_revision=1,
            )
            workflow, outbox_event = self.state_manager.create_workflow(workflow_id, document_id)
            record_workflow_start(workflow_id)
            self.outbox_worker.add_outbox_event(outbox_event)
            self.outbox_worker.process_pending()
            return workflow, outbox_event

    def dispatch(self, event: WorkflowEvent) -> Tuple[AnalysisWorkflow, Optional[WorkflowOutboxEvent]]:
        """Process an incoming WorkflowEvent envelope idempotently and execute stage logic."""
        workflow_id = event.workflow_id
        document_id = event.document_id

        with CorrelationContext(
            workflow_id=workflow_id,
            document_id=document_id,
            event_type=event.event_type.value,
            workflow_revision=event.workflow_revision,
        ):
            log_event(
                logger=logger,
                level=logging.INFO,
                message=f"Dispatching event '{event.event_type.value}' for workflow '{workflow_id}' (Rev {event.workflow_revision})",
                component="orchestrator",
                operation="dispatch_event",
                workflow_id=workflow_id,
                document_id=document_id,
                event_type=event.event_type.value,
                workflow_revision=event.workflow_revision,
                retry_count=event.attempt_number,
            )

            # Step 1: Check idempotency & revision bounds
            try:
                is_processed, cached_output = self.state_manager.check_idempotency(event)
                if is_processed:
                    log_event(
                        logger=logger,
                        level=logging.INFO,
                        message=f"Event '{event.get_logical_event_key()}' already processed. Returning cached result (Idempotency Hit).",
                        component="orchestrator",
                        operation="idempotency_check",
                        workflow_id=workflow_id,
                        outcome="SKIPPED_DUPLICATE",
                        idempotency_key=event.get_logical_event_key(),
                    )
                    record_idempotency_duplicate(workflow_id)
                    workflow = self.state_manager.get_workflow(workflow_id)
                    return workflow, None
            except StaleEventError as stale_err:
                log_event(
                    logger=logger,
                    level=logging.INFO,
                    message=f"Dropping stale event: {stale_err}",
                    component="orchestrator",
                    operation="stale_event_check",
                    workflow_id=workflow_id,
                    outcome="DROPPED_STALE",
                    error_category=ErrorCategory.IDEMPOTENCY_DUPLICATE.value,
                )
                record_idempotency_duplicate(workflow_id)
                workflow = self.state_manager.get_workflow(workflow_id)
                return workflow, None

            # Step 2: Retrieve workflow state
            workflow = self.state_manager.get_workflow(workflow_id)
            if not workflow:
                raise RuntimeError(f"Workflow '{workflow_id}' not found.")

            current_state = workflow.current_state

            # Terminal state check
            if current_state in (WorkflowState.COMPLETED, WorkflowState.FAILED, WorkflowState.ESCALATED):
                log_event(
                    logger=logger,
                    level=logging.WARNING,
                    message=f"Workflow '{workflow_id}' is in terminal state '{current_state.value}'. Rejecting dispatch.",
                    component="orchestrator",
                    operation="terminal_state_check",
                    workflow_id=workflow_id,
                    current_state=current_state.value,
                    outcome="TERMINAL_REJECTED",
                )
                return workflow, None

            # Step 3: Acquire worker execution claim lease
            logical_key = event.get_logical_event_key()
            try:
                self.state_manager.acquire_execution_claim(
                    workflow_id=workflow_id,
                    logical_event_key=logical_key,
                    owner_id=self.owner_id,
                    ttl_seconds=settings.lease_ttl_seconds,
                )
                log_event(
                    logger=logger,
                    level=logging.DEBUG,
                    message=f"Acquired execution claim for '{logical_key}' by '{self.owner_id}'",
                    component="orchestrator",
                    operation="acquire_claim",
                    workflow_id=workflow_id,
                    claim_id=logical_key,
                    outcome="CLAIM_ACQUIRED",
                )
            except LeaseAcquisitionError as lease_err:
                log_event(
                    logger=logger,
                    level=logging.WARNING,
                    message=f"Execution claim conflict: {lease_err}",
                    component="orchestrator",
                    operation="acquire_claim",
                    workflow_id=workflow_id,
                    claim_id=logical_key,
                    outcome="CLAIM_CONFLICT",
                    error_category=ErrorCategory.CLAIM_CONFLICT.value,
                    error_details=str(lease_err),
                )
                record_claim_conflict(workflow_id)
                raise lease_err

            # Step 4: Determine next operational state target
            next_target, next_event_type = STAGE_TRANSITION_MAP.get(
                current_state, (WorkflowState.COMPLETED, EventType.REPORT_COMPLETED)
            )

            # Step 5: Execute adapter if stage requires engine processing
            adapter = self.adapters.get(current_state)
            adapter_result = None

            if adapter:
                t0 = time.perf_counter()
                log_event(
                    logger=logger,
                    level=logging.INFO,
                    message=f"Executing adapter '{adapter.adapter_name}' for state '{current_state.value}'",
                    component="orchestrator",
                    operation="execute_adapter",
                    workflow_id=workflow_id,
                    adapter=adapter.adapter_name,
                    current_state=current_state.value,
                )
                adapter_result = adapter.execute(
                    workflow_id=workflow_id,
                    document_id=event.document_id,
                    payload=event.payload,
                )
                adapter_duration_sec = time.perf_counter() - t0
                record_adapter_execution(adapter.adapter_name, adapter_duration_sec, adapter_result.success)

                log_event(
                    logger=logger,
                    level=logging.INFO if adapter_result.success else logging.WARNING,
                    message=f"Adapter '{adapter.adapter_name}' completed in {adapter_duration_sec*1000:.2f}ms (Success={adapter_result.success})",
                    component="orchestrator",
                    operation="adapter_completed",
                    workflow_id=workflow_id,
                    adapter=adapter.adapter_name,
                    duration_ms=adapter_duration_sec * 1000,
                    outcome="SUCCESS" if adapter_result.success else "ADAPTER_FAILURE",
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
                    record_workflow_failed(workflow_id, reason)
                else:  # RETRYABLE
                    record_retry(component="orchestrator", reason=adapter_result.failure_reason)
                    if event.attempt_number >= self.max_retries:
                        target_state = WorkflowState.ESCALATED
                        reason = f"Exhausted {self.max_retries} retries: {adapter_result.failure_reason}"
                        next_evt = EventType.WORKFLOW_ESCALATED
                        record_workflow_escalated(workflow_id)
                    else:
                        # Retry cleanly by re-enqueuing same state event
                        target_state = current_state
                        reason = f"Retry attempt {event.attempt_number}: {adapter_result.failure_reason}"
                        next_evt = event.event_type
            else:
                target_state = next_target
                reason = None
                next_evt = next_event_type
                if target_state == WorkflowState.COMPLETED:
                    record_workflow_complete(workflow_id)

            # Step 7: Atomic Transaction commit
            output_ref = adapter_result.output_reference if adapter_result else None
            next_payload = dict(event.payload) if event.payload else {"document_id": event.document_id}
            if output_ref:
                next_payload["previous_output"] = output_ref
                for k, v in output_ref.items():
                    if k != "document_id":
                        next_payload[k] = v

            updated_workflow, outbox_event = self.state_manager.commit_transaction(
                workflow_id=workflow_id,
                expected_revision=event.workflow_revision,
                target_state=target_state,
                output_reference=output_ref,
                next_event_type=next_evt if target_state not in (WorkflowState.COMPLETED, WorkflowState.FAILED, WorkflowState.ESCALATED) else None,
                next_event_payload=next_payload,
                reason=reason,
            )

            new_rev = getattr(updated_workflow, "workflow_revision", event.workflow_revision + 1)
            log_event(
                logger=logger,
                level=logging.INFO,
                message=f"Workflow '{workflow_id}' transitioned {current_state.value} -> {target_state.value} (Rev {new_rev})",
                component="orchestrator",
                operation="state_transition",
                workflow_id=workflow_id,
                current_state=current_state.value,
                target_state=target_state.value,
                workflow_revision=new_rev,
                outcome="COMMITTED",
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
        """Resume a workflow stalled in REQUIRES_REVIEW state after human review approval."""
        if not reviewer_principal or not isinstance(reviewer_principal, str):
            raise UnauthorizedReviewerError("Reviewer principal is unauthenticated or missing.")

        with CorrelationContext(workflow_id=workflow_id, reviewer=reviewer_principal):
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

            resumed_rev = getattr(updated_workflow, "workflow_revision", current_rev + 1)
            log_event(
                logger=logger,
                level=logging.INFO,
                message=f"Resumed workflow '{workflow_id}' to state '{target_enum.value}' by reviewer '{reviewer_principal}'",
                component="orchestrator",
                operation="resume_workflow",
                workflow_id=workflow_id,
                target_state=target_enum.value,
                workflow_revision=resumed_rev,
                outcome="RESUMED",
            )
            return updated_workflow, outbox_event
