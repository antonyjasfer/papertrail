from app.audit.bundle import build_evidence_bundle, compute_bundle_hash
from app.audit.canonical import canonicalize, canonicalize_datetime
from app.audit.chain import AuditChainBuilder
from app.audit.constants import (
    AUDIT_SCHEMA_VERSION,
    COMPLIANCE_ENGINE_VERSION,
    EXPECTED_AUDIT_EVENT_SEQUENCE,
    FORENSIC_ENGINE_VERSION,
    GENESIS_MARKER,
    GENESIS_PREVIOUS_HASH,
    HASH_ALGORITHM,
    RISK_ENGINE_VERSION,
)
from app.audit.errors import (
    AuditCanonicalizationError,
    AuditChainBrokenError,
    AuditChainSealedError,
    AuditDuplicateError,
    AuditEventNotFoundError,
    AuditError,
    AuditIntegrityError,
    AuditPersistenceError,
    AuditSecurityError,
    UnsupportedAuditSchemaVersion,
)
from app.audit.hashing import compute_event_hash, compute_hash, compute_payload_hash
from app.audit.models import (
    AnalysisEvidenceBundle,
    AuditEvent,
    AuditEventType,
    AuditProvenance,
    DocumentChecksumVerification,
    VerificationResult,
    VerificationStatus,
)
from app.audit.verifier import AuditVerificationService

__all__ = [
    # Models
    "AuditEvent",
    "AuditEventType",
    "AuditProvenance",
    "AnalysisEvidenceBundle",
    "VerificationResult",
    "VerificationStatus",
    "DocumentChecksumVerification",
    # Services & Builders
    "AuditChainBuilder",
    "AuditVerificationService",
    "build_evidence_bundle",
    "compute_bundle_hash",
    # Serialization & Hashing
    "canonicalize",
    "canonicalize_datetime",
    "compute_hash",
    "compute_payload_hash",
    "compute_event_hash",
    # Constants
    "AUDIT_SCHEMA_VERSION",
    "FORENSIC_ENGINE_VERSION",
    "COMPLIANCE_ENGINE_VERSION",
    "RISK_ENGINE_VERSION",
    "GENESIS_MARKER",
    "GENESIS_PREVIOUS_HASH",
    "HASH_ALGORITHM",
    "EXPECTED_AUDIT_EVENT_SEQUENCE",
    # Errors
    "AuditError",
    "AuditIntegrityError",
    "AuditChainBrokenError",
    "AuditChainSealedError",
    "AuditDuplicateError",
    "AuditEventNotFoundError",
    "AuditPersistenceError",
    "UnsupportedAuditSchemaVersion",
    "AuditSecurityError",
    "AuditCanonicalizationError",
]
