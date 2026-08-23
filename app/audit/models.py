from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from app.audit.constants import AUDIT_SCHEMA_VERSION, HASH_ALGORITHM


class AuditEventType(str, Enum):
    """Categorical types of audit events corresponding to analysis pipeline phases."""

    DOCUMENT_REGISTERED = "DOCUMENT_REGISTERED"
    EXTRACTION_COMPLETED = "EXTRACTION_COMPLETED"
    FORENSIC_ANALYSIS_COMPLETED = "FORENSIC_ANALYSIS_COMPLETED"
    COMPLIANCE_ANALYSIS_COMPLETED = "COMPLIANCE_ANALYSIS_COMPLETED"
    RISK_ASSESSMENT_COMPLETED = "RISK_ASSESSMENT_COMPLETED"
    AUDIT_SEALED = "AUDIT_SEALED"


class AuditProvenance(BaseModel):
    """Provenance metadata recording software, model, and policy version context."""

    app_version: str
    gemini_model: Optional[str] = None
    extraction_schema_version: Optional[str] = None
    forensic_engine_version: Optional[str] = None
    policy_id: Optional[str] = None
    policy_version: Optional[str] = None
    compliance_engine_version: Optional[str] = None
    risk_profile_id: Optional[str] = None
    risk_profile_version: Optional[str] = None
    risk_engine_version: Optional[str] = None
    version_status: str = "DECLARED"  # Explicit "DECLARED" vs "AUTHORITATIVE"
    hash_algorithm: str = HASH_ALGORITHM


class AuditEvent(BaseModel):
    """Immutable Audit Event tracking a single step in a document analysis provenance chain."""

    event_id: str
    document_id: str
    workflow_id: str
    event_type: AuditEventType
    event_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = AUDIT_SCHEMA_VERSION
    source_phase: str
    payload_hash: str
    previous_event_hash: str
    event_hash: str
    provenance: AuditProvenance
    metadata: Dict[str, str] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def validate_hardened_metadata(cls, v: Dict[str, str]) -> Dict[str, str]:
        if len(v) > 16:
            raise ValueError(f"Audit event metadata exceeds maximum allowed entry limit of 16 (got {len(v)}).")
        for key, val in v.items():
            if not isinstance(key, str) or not isinstance(val, str):
                raise ValueError("All audit event metadata keys and values must be strings.")
            if len(key) > 64:
                raise ValueError(f"Metadata key '{key}' exceeds maximum length of 64 characters.")
            if len(val) > 256:
                raise ValueError(f"Metadata value for '{key}' exceeds maximum length of 256 characters.")
        return v


class AnalysisEvidenceBundle(BaseModel):
    """Compact analysis evidence bundle sealing a completed document analysis workflow."""

    bundle_id: str
    document_id: str
    workflow_id: str
    document_checksum: str
    extraction_payload_hash: Optional[str] = None
    forensic_result_hash: Optional[str] = None
    compliance_result_hash: Optional[str] = None
    risk_assessment_hash: Optional[str] = None
    policy_ids: List[str] = Field(default_factory=list)
    policy_versions: List[str] = Field(default_factory=list)
    risk_profile_id: Optional[str] = None
    risk_profile_version: Optional[str] = None
    app_version: str
    version_status: str = "DECLARED"
    sealed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    bundle_hash: str = ""


class VerificationStatus(str, Enum):
    """Status of an audit chain or event verification operation."""

    VALID = "VALID"
    INVALID = "INVALID"


class DocumentChecksumVerification(str, Enum):
    """Status of raw document bytes checksum verification against stored anchor."""

    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class VerificationResult(BaseModel):
    """Detailed verification report returned by AuditVerificationService."""

    status: VerificationStatus
    chain_length: int = 0
    verified_events: int = 0
    missing_events: List[AuditEventType] = Field(default_factory=list)
    broken_at_event_id: Optional[str] = None
    expected_hash: Optional[str] = None
    observed_hash: Optional[str] = None
    document_checksum_status: DocumentChecksumVerification = DocumentChecksumVerification.NOT_AVAILABLE
    failure_reason: Optional[str] = None
