"""PaperTrail AI — Production Workflow Diagnostics & Stuck Workflow Detection.

Provides deterministic inspection and health diagnostics for workflow lifecycles,
detecting un-progressed workflows and surfacing operational health indicators.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.contracts.state_manager import IWorkflowStateManager
from app.core.state import AnalysisWorkflow, WorkflowState

TERMINAL_STATES = {
    WorkflowState.COMPLETED,
    WorkflowState.FAILED,
    WorkflowState.ESCALATED,
    WorkflowState.REQUIRES_REVIEW,
}



class StuckWorkflowReport:
    """Diagnostic report for a workflow detected as stuck in a non-terminal state."""

    def __init__(
        self,
        workflow_id: str,
        document_id: str,
        current_state: str,
        workflow_revision: int,
        last_updated_at: datetime,
        stuck_duration_seconds: float,
        threshold_seconds: int,
    ) -> None:
        self.workflow_id = workflow_id
        self.document_id = document_id
        self.current_state = current_state
        self.workflow_revision = workflow_revision
        self.last_updated_at = last_updated_at
        self.stuck_duration_seconds = stuck_duration_seconds
        self.threshold_seconds = threshold_seconds
        self.diagnostic_status = "STUCK"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "document_id": self.document_id,
            "current_state": self.current_state,
            "workflow_revision": self.workflow_revision,
            "last_updated_at": self.last_updated_at.isoformat(),
            "stuck_duration_seconds": round(self.stuck_duration_seconds, 2),
            "threshold_seconds": self.threshold_seconds,
            "diagnostic_status": "STUCK",
        }


def check_workflow_stuck(
    workflow: AnalysisWorkflow,
    threshold_seconds: int = 300,
    reference_time: Optional[datetime] = None,
) -> Optional[StuckWorkflowReport]:
    """Check if a specific workflow is stuck in a non-terminal state."""
    if workflow.current_state in TERMINAL_STATES:
        return None

    ref = reference_time or datetime.now(timezone.utc)
    updated_at = workflow.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    elapsed_seconds = (ref - updated_at).total_seconds()
    if elapsed_seconds > threshold_seconds:
        return StuckWorkflowReport(
            workflow_id=workflow.workflow_id,
            document_id=workflow.document_id,
            current_state=workflow.current_state.value,
            workflow_revision=getattr(workflow, "workflow_revision", 1),
            last_updated_at=updated_at,
            stuck_duration_seconds=elapsed_seconds,
            threshold_seconds=threshold_seconds,
        )
    return None
