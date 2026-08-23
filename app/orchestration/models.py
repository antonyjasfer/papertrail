from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
import uuid
from pydantic import BaseModel, Field


class ClaimStatus(str, Enum):
    """Status lifecycle for worker execution claims."""

    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class WorkflowExecutionClaim(BaseModel):
    """Execution lease record preventing concurrent workers from running the same adapter."""

    claim_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    logical_event_key: str  # workflow_id:workflow_revision:event_type
    execution_id: str
    owner_id: str          # Worker instance ID
    status: ClaimStatus = ClaimStatus.CLAIMED
    attempt_number: int = 1
    claimed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    lease_expires_at: datetime
    output_reference: Optional[Dict[str, Any]] = None
    completion_status: Optional[str] = None

    def is_expired(self, current_time: Optional[datetime] = None) -> bool:
        """Check if lease timestamp has expired."""
        now = current_time or datetime.now(timezone.utc)
        return now >= self.lease_expires_at


class ReviewDecision(str, Enum):
    """Decisions available during human review resolution."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RE_EVALUATE = "RE_EVALUATE"


class HumanReviewPayload(BaseModel):
    """Payload submitted when resolving a workflow in REQUIRES_REVIEW state."""

    review_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    reviewer_id: str
    decision: ReviewDecision
    decision_reason: str
    requested_target: str  # Must be validated against VALID_TRANSITIONS
    decision_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
