from datetime import datetime, timezone
import pytest

from app.core.state import WorkflowState
from app.events.schemas import EventType, WorkflowEvent
from app.orchestration.models import HumanReviewPayload, ReviewDecision
from app.orchestration.orchestrator import WorkflowOrchestrator
from app.orchestration.state_manager import FirestoreStateManager


def test_orchestrator_start_workflow():
    orchestrator = WorkflowOrchestrator()
    workflow, outbox = orchestrator.start_workflow("wf-e2e-1", "doc-e2e-1")
    assert workflow.workflow_id == "wf-e2e-1"
    assert workflow.current_state == WorkflowState.UPLOADED
    assert orchestrator.state_manager.get_workflow_revision("wf-e2e-1") == 1


def test_orchestrator_dispatch_happy_path_step():
    orchestrator = WorkflowOrchestrator()
    orchestrator.start_workflow("wf-step-1", "doc-step-1")

    event = WorkflowEvent(
        workflow_id="wf-step-1",
        document_id="doc-step-1",
        event_type=EventType.DOCUMENT_UPLOADED,
        current_state="UPLOADED",
        workflow_revision=1,
        payload={"document_id": "doc-step-1"},
        event_timestamp=datetime.now(timezone.utc),
        correlation_id="corr-1",
    )

    updated, outbox = orchestrator.dispatch(event)
    assert updated.current_state == WorkflowState.INGESTING
    assert orchestrator.state_manager.get_workflow_revision("wf-step-1") == 2
    assert outbox is not None
    assert outbox.event_type == EventType.INGESTION_COMPLETED


def test_human_review_resume_flow():
    state_manager = FirestoreStateManager()
    orchestrator = WorkflowOrchestrator(state_manager=state_manager)

    workflow, _ = state_manager.create_workflow("wf-review", "doc-review")
    state_manager.commit_transaction("wf-review", 1, WorkflowState.INGESTING)
    state_manager.commit_transaction("wf-review", 2, WorkflowState.EXTRACTING)
    state_manager.commit_transaction("wf-review", 3, WorkflowState.REQUIRES_REVIEW, reason="Policy ambiguity")
    assert workflow.current_state == WorkflowState.REQUIRES_REVIEW

    payload = HumanReviewPayload(
        workflow_id="wf-review",
        reviewer_id="rev-007",
        decision=ReviewDecision.APPROVED,
        decision_reason="Verified manually",
        requested_target="FORENSIC_ANALYSIS",
    )

    resumed_wf, outbox = orchestrator.resume_workflow(
        workflow_id="wf-review",
        payload=payload,
        reviewer_principal="compliance_admin@papertrail.ai",
    )

    assert resumed_wf.current_state == WorkflowState.FORENSIC_ANALYSIS
    assert outbox is not None
