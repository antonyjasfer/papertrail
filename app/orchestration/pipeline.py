from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional
import uuid

from app.core.contracts.state_manager import IWorkflowStateManager
from app.core.state import AnalysisWorkflow, WorkflowState
from app.events.publisher import BasePublisher, MockPubSubPublisher
from app.events.schemas import EventType, WorkflowEvent
from app.infrastructure.factory import get_event_publisher, get_state_manager
from app.orchestration.orchestrator import WorkflowOrchestrator

logger = logging.getLogger(__name__)


class PipelineRunner:
    """High-level coordinator for starting, executing, and inspecting pipeline workflows (for testing/local execution)."""

    def __init__(
        self,
        orchestrator: Optional[WorkflowOrchestrator] = None,
        state_manager: Optional[IWorkflowStateManager] = None,
        publisher: Optional[BasePublisher] = None,
    ) -> None:
        self.state_manager = state_manager or (orchestrator.state_manager if orchestrator else get_state_manager())
        self.publisher = publisher or (orchestrator.publisher if orchestrator else get_event_publisher())
        self.orchestrator = orchestrator or WorkflowOrchestrator(
            state_manager=self.state_manager,
            publisher=self.publisher,
        )

    def start_pipeline(self, document_id: str, workflow_id: Optional[str] = None) -> str:
        """Start a new document analysis pipeline and return workflow_id."""
        w_id = workflow_id or f"wf-{uuid.uuid4().hex[:8]}"
        self.orchestrator.start_workflow(workflow_id=w_id, document_id=document_id)
        logger.info(f"[PipelineRunner] Started pipeline '{w_id}' for document '{document_id}'.")
        return w_id

    def step(self, workflow_id: str) -> AnalysisWorkflow:
        """Execute one pipeline step by dispatching pending outbox event if available."""
        outbox_list = getattr(self.state_manager, "_outbox", [])
        pending = [
            r for r in outbox_list
            if r.workflow_id == workflow_id and getattr(r.status, "value", str(r.status)) in ("PUBLISHED", "PENDING")
        ]
        if not pending and hasattr(self.state_manager, "_items"):
            outbox_dict_items = [v for k, v in self.state_manager._items.items() if k.startswith(f"{workflow_id}:outbox:")]
            if outbox_dict_items:
                latest_item = sorted(outbox_dict_items, key=lambda x: x.get("workflow_revision", 1))[-1]
                event = WorkflowEvent(
                    event_id=latest_item["event_id"],
                    workflow_id=workflow_id,
                    document_id=latest_item["document_id"],
                    event_type=EventType(latest_item["event_type"]),
                    current_state="",
                    workflow_revision=latest_item["workflow_revision"],
                    payload_hash=latest_item.get("payload_hash", ""),
                    payload=latest_item.get("payload", {}),
                    event_timestamp=datetime.now(timezone.utc),
                    correlation_id=workflow_id,
                )
                workflow, _ = self.orchestrator.dispatch(event)
                return workflow

        if not pending:
            workflow = self.state_manager.get_workflow(workflow_id)
            return workflow

        latest_record = pending[-1]
        event = latest_record.to_workflow_event()
        workflow, _ = self.orchestrator.dispatch(event)
        return workflow

    def run_to_completion(self, workflow_id: str, max_steps: int = 15) -> AnalysisWorkflow:
        """Run pipeline steps synchronously until workflow reaches terminal or review state."""
        workflow = self.state_manager.get_workflow(workflow_id)
        if not workflow:
            raise RuntimeError(f"Workflow '{workflow_id}' not found.")

        steps_taken = 0
        while steps_taken < max_steps:
            if workflow.current_state in (
                WorkflowState.COMPLETED,
                WorkflowState.FAILED,
                WorkflowState.ESCALATED,
                WorkflowState.REQUIRES_REVIEW,
            ):
                logger.info(
                    f"[PipelineRunner] Workflow '{workflow_id}' reached state '{workflow.current_state.value}' "
                    f"after {steps_taken} step(s)."
                )
                return workflow

            prev_state = workflow.current_state
            workflow = self.step(workflow_id)
            steps_taken += 1

            if workflow.current_state == prev_state:
                # Break if state did not advance to prevent infinite loop
                break

        return workflow

    def get_pipeline_status(self, workflow_id: str) -> Dict[str, Any]:
        """Return pipeline status summary dictionary."""
        workflow = self.state_manager.get_workflow(workflow_id)
        if not workflow:
            return {"error": f"Workflow '{workflow_id}' not found."}

        revision = self.state_manager.get_workflow_revision(workflow_id)
        return {
            "workflow_id": workflow.workflow_id,
            "document_id": workflow.document_id,
            "current_state": workflow.current_state.value,
            "workflow_revision": revision,
            "created_at": workflow.created_at.isoformat(),
            "updated_at": workflow.updated_at.isoformat(),
            "failure_reason": workflow.failure_reason,
            "escalation_reason": workflow.escalation_reason,
            "review_reason": workflow.review_reason,
        }
