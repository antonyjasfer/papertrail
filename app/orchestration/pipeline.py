import logging
from typing import Any, Dict, Optional
import uuid

from app.core.state import AnalysisWorkflow, WorkflowState
from app.events.publisher import MockPubSubPublisher
from app.events.schemas import EventType, WorkflowEvent
from app.orchestration.orchestrator import WorkflowOrchestrator
from app.orchestration.state_manager import FirestoreStateManager

logger = logging.getLogger(__name__)


class PipelineRunner:
    """High-level coordinator for starting, executing, and inspecting pipeline workflows."""

    def __init__(
        self,
        orchestrator: Optional[WorkflowOrchestrator] = None,
        state_manager: Optional[FirestoreStateManager] = None,
    ) -> None:
        self.state_manager = state_manager or FirestoreStateManager()
        self.publisher = MockPubSubPublisher()
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
        outbox_list = self.orchestrator.state_manager._outbox
        pending = [r for r in outbox_list if r.workflow_id == workflow_id and r.status.value == "PUBLISHED"]
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
