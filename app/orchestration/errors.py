from typing import Optional


class OrchestrationError(Exception):
    """Base exception for all orchestration errors."""
    pass


class StateSynchronizationError(OrchestrationError):
    """Raised when optimistic revision concurrency fails (expected_revision != stored_revision)."""

    def __init__(self, workflow_id: str, expected_revision: int, stored_revision: int):
        self.workflow_id = workflow_id
        self.expected_revision = expected_revision
        self.stored_revision = stored_revision
        super().__init__(
            f"State synchronization failed for workflow '{workflow_id}': "
            f"expected revision {expected_revision}, but stored revision is {stored_revision}."
        )


class IntegrityConflictError(OrchestrationError):
    """Raised when a duplicate event key is replayed with a differing payload hash or conflicting metadata."""
    pass


class StaleEventError(OrchestrationError):
    """Raised when an incoming event has a workflow_revision lower than current stored workflow_revision."""

    def __init__(self, workflow_id: str, event_revision: int, current_revision: int):
        self.workflow_id = workflow_id
        self.event_revision = event_revision
        self.current_revision = current_revision
        super().__init__(
            f"Stale event rejected for workflow '{workflow_id}': "
            f"event revision {event_revision} < current revision {current_revision}."
        )


class FutureEventError(OrchestrationError):
    """Raised when an incoming event attempts to skip workflow revisions (event_revision > current_revision)."""

    def __init__(self, workflow_id: str, event_revision: int, current_revision: int):
        self.workflow_id = workflow_id
        self.event_revision = event_revision
        self.current_revision = current_revision
        super().__init__(
            f"Future event rejected for workflow '{workflow_id}': "
            f"event revision {event_revision} > current revision {current_revision}."
        )


class EngineExecutionError(OrchestrationError):
    """Raised when an engine adapter encounters an unhandled internal exception during execution."""

    def __init__(self, adapter_name: str, message: str, original_error: Optional[Exception] = None):
        self.adapter_name = adapter_name
        self.original_error = original_error
        super().__init__(f"Engine execution error in '{adapter_name}': {message}")


class LeaseAcquisitionError(OrchestrationError):
    """Raised when an active execution lease claim is held by another worker instance."""

    def __init__(self, logical_event_key: str, owner_id: str, expires_at_str: str):
        self.logical_event_key = logical_event_key
        self.owner_id = owner_id
        self.expires_at_str = expires_at_str
        super().__init__(
            f"Execution lease claim for '{logical_event_key}' is actively held by owner '{owner_id}' "
            f"until {expires_at_str}."
        )


class UnauthorizedReviewerError(OrchestrationError):
    """Raised when an unauthenticated or unauthorized principal attempts to trigger human review resume."""
    pass
