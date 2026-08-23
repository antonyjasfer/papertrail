from typing import Optional


class AuditError(Exception):
    """Base exception for all PaperTrail AI audit layer errors."""

    pass


class AuditIntegrityError(AuditError):
    """Raised when a cryptographic integrity check fails or slot hash mismatch occurs."""

    def __init__(
        self,
        message: str,
        event_id: Optional[str] = None,
        expected_hash: Optional[str] = None,
        observed_hash: Optional[str] = None,
    ):
        self.event_id = event_id
        self.expected_hash = expected_hash
        self.observed_hash = observed_hash
        super().__init__(message)


class AuditChainBrokenError(AuditError):
    """Raised when hash linkage between adjacent events in a chain fails."""

    def __init__(
        self,
        broken_at_event_id: str,
        expected_previous_hash: str,
        observed_previous_hash: str,
    ):
        self.broken_at_event_id = broken_at_event_id
        self.expected_previous_hash = expected_previous_hash
        self.observed_previous_hash = observed_previous_hash
        super().__init__(
            f"Audit chain broken at event '{broken_at_event_id}'. "
            f"Expected previous hash '{expected_previous_hash}', got '{observed_previous_hash}'."
        )


class AuditChainSealedError(AuditError):
    """Raised when attempting to append an event to a sealed audit chain."""

    def __init__(self, document_id: str, workflow_id: str):
        self.document_id = document_id
        self.workflow_id = workflow_id
        super().__init__(
            f"Audit chain for document '{document_id}' (workflow '{workflow_id}') is sealed. "
            "No subsequent audit events may be appended."
        )


class AuditDuplicateError(AuditError):
    """Raised when appending a conflicting event to an existing event slot."""

    def __init__(self, event_id: str, existing_payload_hash: str, new_payload_hash: str):
        self.event_id = event_id
        self.existing_payload_hash = existing_payload_hash
        self.new_payload_hash = new_payload_hash
        super().__init__(
            f"Conflict on event slot '{event_id}'. Existing payload hash '{existing_payload_hash}' "
            f"does not match new payload hash '{new_payload_hash}'."
        )


class AuditEventNotFoundError(AuditError):
    """Raised when a requested audit event document is not found."""

    def __init__(self, event_id: str):
        self.event_id = event_id
        super().__init__(f"Audit event with ID '{event_id}' was not found in storage.")


class AuditPersistenceError(AuditError):
    """Raised when a Firestore repository audit persistence operation fails."""

    def __init__(self, operation: str, event_id: str, message: str):
        self.operation = operation
        self.event_id = event_id
        super().__init__(f"Failed to {operation} audit event '{event_id}': {message}")


class UnsupportedAuditSchemaVersion(AuditError):
    """Raised when an audit event has an unrecognized schema version."""

    def __init__(self, schema_version: str):
        self.schema_version = schema_version
        super().__init__(f"Unsupported audit schema version: '{schema_version}'.")


class AuditSecurityError(AuditError):
    """Raised when prohibited security operations (e.g. update, delete) are attempted."""

    def __init__(self, operation: str):
        self.operation = operation
        super().__init__(f"Audit repository security violation: Operation '{operation}' is strictly prohibited.")


class AuditCanonicalizationError(AuditError):
    """Raised when canonical serialization encounters an unsupported or non-canonicalizable type."""

    def __init__(self, target_type: str, reason: str):
        self.target_type = target_type
        super().__init__(f"Canonicalization error for type '{target_type}': {reason}")
