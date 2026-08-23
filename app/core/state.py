from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional, Set
from pydantic import BaseModel, Field


class WorkflowState(str, Enum):
    """PaperTrail AI Analysis Workflow States."""

    # Operational States (Canonical Happy Path)
    UPLOADED = "UPLOADED"
    INGESTING = "INGESTING"
    EXTRACTING = "EXTRACTING"
    EXTRACTED = "EXTRACTED"
    FORENSIC_ANALYSIS = "FORENSIC_ANALYSIS"
    COMPLIANCE_ANALYSIS = "COMPLIANCE_ANALYSIS"
    RISK_ASSESSED = "RISK_ASSESSED"
    AUDIT_SEALED = "AUDIT_SEALED"
    REPORT_GENERATED = "REPORT_GENERATED"
    COMPLETED = "COMPLETED"

    # Exceptional States
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


# Terminal states that reject further state transitions
TERMINAL_STATES: Set[WorkflowState] = {
    WorkflowState.COMPLETED,
    WorkflowState.FAILED,
    WorkflowState.ESCALATED,
}

# Operational active states that can transition into exceptional states
ACTIVE_OPERATIONAL_STATES: Set[WorkflowState] = {
    WorkflowState.UPLOADED,
    WorkflowState.INGESTING,
    WorkflowState.EXTRACTING,
    WorkflowState.EXTRACTED,
    WorkflowState.FORENSIC_ANALYSIS,
    WorkflowState.COMPLIANCE_ANALYSIS,
    WorkflowState.RISK_ASSESSED,
    WorkflowState.AUDIT_SEALED,
    WorkflowState.REPORT_GENERATED,
}

# Explicit deterministic state transition matrix
VALID_TRANSITIONS: Dict[WorkflowState, Set[WorkflowState]] = {
    WorkflowState.UPLOADED: {
        WorkflowState.INGESTING,
        WorkflowState.FAILED,
        WorkflowState.ESCALATED,
    },
    WorkflowState.INGESTING: {
        WorkflowState.EXTRACTING,
        WorkflowState.FAILED,
        WorkflowState.ESCALATED,
    },
    WorkflowState.EXTRACTING: {
        WorkflowState.EXTRACTED,
        WorkflowState.FAILED,
        WorkflowState.ESCALATED,
        WorkflowState.REQUIRES_REVIEW,
    },
    WorkflowState.EXTRACTED: {
        WorkflowState.FORENSIC_ANALYSIS,
        WorkflowState.FAILED,
        WorkflowState.ESCALATED,
        WorkflowState.REQUIRES_REVIEW,
    },
    WorkflowState.FORENSIC_ANALYSIS: {
        WorkflowState.COMPLIANCE_ANALYSIS,
        WorkflowState.FAILED,
        WorkflowState.ESCALATED,
        WorkflowState.REQUIRES_REVIEW,
    },
    WorkflowState.COMPLIANCE_ANALYSIS: {
        WorkflowState.RISK_ASSESSED,
        WorkflowState.FAILED,
        WorkflowState.ESCALATED,
        WorkflowState.REQUIRES_REVIEW,
    },
    WorkflowState.RISK_ASSESSED: {
        WorkflowState.AUDIT_SEALED,
        WorkflowState.FAILED,
        WorkflowState.ESCALATED,
        WorkflowState.REQUIRES_REVIEW,
    },
    WorkflowState.AUDIT_SEALED: {
        WorkflowState.REPORT_GENERATED,
        WorkflowState.FAILED,
        WorkflowState.ESCALATED,
    },
    WorkflowState.REPORT_GENERATED: {
        WorkflowState.COMPLETED,
        WorkflowState.FAILED,
    },
    WorkflowState.REQUIRES_REVIEW: {
        WorkflowState.FORENSIC_ANALYSIS,
        WorkflowState.COMPLIANCE_ANALYSIS,
        WorkflowState.RISK_ASSESSED,
        WorkflowState.FAILED,
        WorkflowState.ESCALATED,
    },
    # Terminal states reject all target transitions
    WorkflowState.COMPLETED: set(),
    WorkflowState.FAILED: set(),
    WorkflowState.ESCALATED: set(),
}


class StateTransitionError(Exception):
    """Exception raised when an illegal or unsupported state transition is attempted."""

    def __init__(self, current_state: WorkflowState, target_state: WorkflowState, reason: str = ""):
        self.current_state = current_state
        self.target_state = target_state
        message = f"Invalid state transition: {current_state.value} -> {target_state.value}."
        if reason:
            message += f" Reason: {reason}"
        super().__init__(message)


def can_transition(current_state: WorkflowState, target_state: WorkflowState) -> bool:
    """Check if transitioning from current_state to target_state is valid."""
    allowed = VALID_TRANSITIONS.get(current_state, set())
    return target_state in allowed


def validate_transition(current_state: WorkflowState, target_state: WorkflowState) -> WorkflowState:
    """Validate state transition, raising StateTransitionError if invalid."""
    if not can_transition(current_state, target_state):
        if current_state in TERMINAL_STATES:
            raise StateTransitionError(
                current_state,
                target_state,
                f"State '{current_state.value}' is terminal and rejects further transitions.",
            )
        raise StateTransitionError(
            current_state,
            target_state,
            f"Transition from '{current_state.value}' to '{target_state.value}' is not permitted in transition matrix.",
        )
    return target_state


class AnalysisWorkflow(BaseModel):
    """Lightweight workflow state model tracking analysis lifecycle."""

    workflow_id: str
    document_id: str
    current_state: WorkflowState = WorkflowState.UPLOADED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    failure_reason: Optional[str] = None
    escalation_reason: Optional[str] = None
    review_reason: Optional[str] = None

    def transition_to(self, target_state: WorkflowState, reason: Optional[str] = None) -> WorkflowState:
        """Execute a state transition on the workflow instance.

        Validates the transition strictly. On success, updates state, refreshes updated_at,
        and sets optional exceptional reasons. On failure, raises StateTransitionError
        without mutating state, created_at, or updated_at.
        """
        validated_target = validate_transition(self.current_state, target_state)

        # Mutate state on valid transition
        self.current_state = validated_target
        self.updated_at = datetime.now(timezone.utc)

        if target_state == WorkflowState.FAILED and reason:
            self.failure_reason = reason
        elif target_state == WorkflowState.ESCALATED and reason:
            self.escalation_reason = reason
        elif target_state == WorkflowState.REQUIRES_REVIEW and reason:
            self.review_reason = reason

        return self.current_state
