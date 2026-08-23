import time
import pytest
from app.core.state import (
    WorkflowState,
    StateTransitionError,
    AnalysisWorkflow,
    can_transition,
    validate_transition,
)


def test_transition_uploaded_to_ingesting():
    """Test 1: Verify UPLOADED -> INGESTING transition succeeds."""
    wf = AnalysisWorkflow(workflow_id="wf-001", document_id="doc-001")
    assert wf.current_state == WorkflowState.UPLOADED
    wf.transition_to(WorkflowState.INGESTING)
    assert wf.current_state == WorkflowState.INGESTING


def test_transition_extracted_to_forensic_analysis():
    """Test 2: Verify EXTRACTED -> FORENSIC_ANALYSIS transition succeeds."""
    wf = AnalysisWorkflow(
        workflow_id="wf-002",
        document_id="doc-002",
        current_state=WorkflowState.EXTRACTED,
    )
    wf.transition_to(WorkflowState.FORENSIC_ANALYSIS)
    assert wf.current_state == WorkflowState.FORENSIC_ANALYSIS


def test_transition_audit_sealed_to_report_generated():
    """Test 3: Verify AUDIT_SEALED -> REPORT_GENERATED transition succeeds."""
    wf = AnalysisWorkflow(
        workflow_id="wf-003",
        document_id="doc-003",
        current_state=WorkflowState.AUDIT_SEALED,
    )
    wf.transition_to(WorkflowState.REPORT_GENERATED)
    assert wf.current_state == WorkflowState.REPORT_GENERATED


def test_transition_uploaded_to_completed_fails():
    """Test 4: Verify UPLOADED -> COMPLETED fails with StateTransitionError."""
    wf = AnalysisWorkflow(workflow_id="wf-004", document_id="doc-004")
    with pytest.raises(StateTransitionError) as exc_info:
        wf.transition_to(WorkflowState.COMPLETED)
    assert "Invalid state transition: UPLOADED -> COMPLETED" in str(exc_info.value)
    assert wf.current_state == WorkflowState.UPLOADED


def test_transition_risk_assessed_to_extracting_fails():
    """Test 5: Verify RISK_ASSESSED -> EXTRACTING fails with StateTransitionError."""
    wf = AnalysisWorkflow(
        workflow_id="wf-005",
        document_id="doc-005",
        current_state=WorkflowState.RISK_ASSESSED,
    )
    with pytest.raises(StateTransitionError):
        wf.transition_to(WorkflowState.EXTRACTING)
    assert wf.current_state == WorkflowState.RISK_ASSESSED


def test_terminal_state_rejects_transitions():
    """Test 6: Verify terminal states reject all target transitions."""
    terminal_states = [WorkflowState.COMPLETED, WorkflowState.FAILED, WorkflowState.ESCALATED]
    for state in terminal_states:
        wf = AnalysisWorkflow(
            workflow_id=f"wf-term-{state.value}",
            document_id="doc-term",
            current_state=state,
        )
        assert can_transition(state, WorkflowState.FORENSIC_ANALYSIS) is False
        with pytest.raises(StateTransitionError) as exc_info:
            wf.transition_to(WorkflowState.FORENSIC_ANALYSIS)
        assert "terminal" in str(exc_info.value).lower()
        assert wf.current_state == state


def test_valid_transition_to_failed():
    """Test 7: Verify valid transition into FAILED state."""
    wf = AnalysisWorkflow(
        workflow_id="wf-007",
        document_id="doc-007",
        current_state=WorkflowState.EXTRACTING,
    )
    wf.transition_to(WorkflowState.FAILED, reason="OCR extraction service timeout")
    assert wf.current_state == WorkflowState.FAILED
    assert wf.failure_reason == "OCR extraction service timeout"


def test_valid_transition_to_escalated():
    """Test 8: Verify valid transition into ESCALATED state."""
    wf = AnalysisWorkflow(
        workflow_id="wf-008",
        document_id="doc-008",
        current_state=WorkflowState.FORENSIC_ANALYSIS,
    )
    wf.transition_to(WorkflowState.ESCALATED, reason="High anomaly score detected")
    assert wf.current_state == WorkflowState.ESCALATED
    assert wf.escalation_reason == "High anomaly score detected"


def test_valid_transition_to_requires_review():
    """Test 9: Verify valid transition into REQUIRES_REVIEW state."""
    wf = AnalysisWorkflow(
        workflow_id="wf-009",
        document_id="doc-009",
        current_state=WorkflowState.COMPLIANCE_ANALYSIS,
    )
    wf.transition_to(WorkflowState.REQUIRES_REVIEW, reason="Policy threshold breach")
    assert wf.current_state == WorkflowState.REQUIRES_REVIEW
    assert wf.review_reason == "Policy threshold breach"


def test_full_canonical_happy_path():
    """Test 10: Verify the full canonical happy path workflow lifecycle."""
    happy_path = [
        WorkflowState.UPLOADED,
        WorkflowState.INGESTING,
        WorkflowState.EXTRACTING,
        WorkflowState.EXTRACTED,
        WorkflowState.FORENSIC_ANALYSIS,
        WorkflowState.COMPLIANCE_ANALYSIS,
        WorkflowState.RISK_ASSESSED,
        WorkflowState.AUDIT_SEALED,
        WorkflowState.REPORT_GENERATED,
        WorkflowState.COMPLETED,
    ]

    wf = AnalysisWorkflow(workflow_id="wf-happy", document_id="doc-happy")
    assert wf.current_state == happy_path[0]

    for next_state in happy_path[1:]:
        previous_state = wf.current_state
        assert can_transition(previous_state, next_state) is True
        wf.transition_to(next_state)
        assert wf.current_state == next_state

    assert wf.current_state == WorkflowState.COMPLETED


def test_invalid_transition_does_not_mutate_state():
    """Test 11: Verify invalid transition leaves state unchanged."""
    wf = AnalysisWorkflow(
        workflow_id="wf-011",
        document_id="doc-011",
        current_state=WorkflowState.FORENSIC_ANALYSIS,
    )
    with pytest.raises(StateTransitionError):
        wf.transition_to(WorkflowState.UPLOADED)
    assert wf.current_state == WorkflowState.FORENSIC_ANALYSIS


def test_valid_transition_updates_updated_at():
    """Test 12: Verify valid transition refreshes updated_at timestamp."""
    wf = AnalysisWorkflow(workflow_id="wf-012", document_id="doc-012")
    initial_updated_at = wf.updated_at
    time.sleep(0.01)
    wf.transition_to(WorkflowState.INGESTING)
    assert wf.updated_at > initial_updated_at


def test_valid_transition_preserves_created_at():
    """Test 13: Verify valid transition leaves created_at immutable."""
    wf = AnalysisWorkflow(workflow_id="wf-013", document_id="doc-013")
    initial_created_at = wf.created_at
    time.sleep(0.01)
    wf.transition_to(WorkflowState.INGESTING)
    assert wf.created_at == initial_created_at
