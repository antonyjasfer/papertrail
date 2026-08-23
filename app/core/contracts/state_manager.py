from typing import Any, Dict, Optional, Protocol, Tuple, runtime_checkable

from app.core.state import AnalysisWorkflow, WorkflowState
from app.events.schemas import EventType, WorkflowEvent
from app.orchestration.models import WorkflowExecutionClaim
from app.orchestration.outbox import WorkflowOutboxEvent


@runtime_checkable
class IWorkflowStateManager(Protocol):
    """Protocol for state managers (Firestore, Cosmos DB, In-Memory)."""

    def get_workflow(self, workflow_id: str) -> Optional[AnalysisWorkflow]: ...

    def get_workflow_revision(self, workflow_id: str) -> int: ...

    def create_workflow(
        self, workflow_id: str, document_id: str
    ) -> Tuple[AnalysisWorkflow, WorkflowOutboxEvent]: ...

    def check_idempotency(
        self, event: WorkflowEvent
    ) -> Tuple[bool, Optional[Dict[str, Any]]]: ...

    def acquire_execution_claim(
        self,
        workflow_id: str,
        logical_event_key: str,
        owner_id: str,
        ttl_seconds: int = 300,
    ) -> WorkflowExecutionClaim: ...

    def commit_transaction(
        self,
        workflow_id: str,
        expected_revision: int,
        target_state: WorkflowState,
        output_reference: Optional[Dict[str, Any]] = None,
        next_event_type: Optional[EventType] = None,
        next_event_payload: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
    ) -> Tuple[AnalysisWorkflow, Optional[WorkflowOutboxEvent]]: ...
