from datetime import datetime, timezone
import uuid
from typing import Any, Dict, Optional

from app.audit.constants import (
    AUDIT_SCHEMA_VERSION,
    COMPLIANCE_ENGINE_VERSION,
    FORENSIC_ENGINE_VERSION,
    GENESIS_PREVIOUS_HASH,
    HASH_ALGORITHM,
    RISK_ENGINE_VERSION,
)
from app.audit.hashing import compute_event_hash, compute_payload_hash
from app.audit.models import AuditEvent, AuditEventType, AuditProvenance
from app.core.config import settings
from app.models.document import DocumentMetadata


class AuditChainBuilder:
    """Builder service constructing valid, cryptographically linked AuditEvent instances."""

    @staticmethod
    def build_provenance(
        event_type: AuditEventType,
        gemini_model: Optional[str] = None,
        policy_id: Optional[str] = None,
        policy_version: Optional[str] = None,
        risk_profile_id: Optional[str] = None,
        risk_profile_version: Optional[str] = None,
    ) -> AuditProvenance:
        """Construct AuditProvenance metadata with explicit DECLARED version status."""
        return AuditProvenance(
            app_version=settings.app_version,
            gemini_model=gemini_model if event_type == AuditEventType.EXTRACTION_COMPLETED else None,
            extraction_schema_version=settings.app_version if event_type == AuditEventType.EXTRACTION_COMPLETED else None,
            forensic_engine_version=FORENSIC_ENGINE_VERSION if event_type == AuditEventType.FORENSIC_ANALYSIS_COMPLETED else None,
            policy_id=policy_id,
            policy_version=policy_version,
            compliance_engine_version=COMPLIANCE_ENGINE_VERSION if event_type == AuditEventType.COMPLIANCE_ANALYSIS_COMPLETED else None,
            risk_profile_id=risk_profile_id,
            risk_profile_version=risk_profile_version,
            risk_engine_version=RISK_ENGINE_VERSION if event_type == AuditEventType.RISK_ASSESSMENT_COMPLETED else None,
            version_status="DECLARED",
            hash_algorithm=HASH_ALGORITHM,
        )

    @classmethod
    def create_genesis_event(
        cls,
        document_metadata: DocumentMetadata,
        workflow_id: str,
        event_timestamp: Optional[datetime] = None,
    ) -> AuditEvent:
        """Create the deterministic Genesis AuditEvent (DOCUMENT_REGISTERED) anchoring a document chain."""
        payload_hash = compute_payload_hash(document_metadata)
        ts = event_timestamp or document_metadata.created_at or datetime.now(timezone.utc)
        provenance = cls.build_provenance(AuditEventType.DOCUMENT_REGISTERED)

        event = AuditEvent(
            event_id=f"evt-gen-{document_metadata.document_id}",
            document_id=document_metadata.document_id,
            workflow_id=workflow_id,
            event_type=AuditEventType.DOCUMENT_REGISTERED,
            event_timestamp=ts,
            schema_version=AUDIT_SCHEMA_VERSION,
            source_phase="Phase 5",
            payload_hash=payload_hash,
            previous_event_hash=GENESIS_PREVIOUS_HASH,
            event_hash="",
            provenance=provenance,
            metadata={"checksum": document_metadata.checksum},
        )
        event.event_hash = compute_event_hash(event)
        return event

    @classmethod
    def create_event(
        cls,
        document_id: str,
        workflow_id: str,
        event_type: AuditEventType,
        source_phase: str,
        payload: Any,
        previous_event_hash: str,
        event_timestamp: Optional[datetime] = None,
        provenance: Optional[AuditProvenance] = None,
        metadata: Optional[Dict[str, str]] = None,
        event_id: Optional[str] = None,
    ) -> AuditEvent:
        """Create a cryptographically linked AuditEvent for an analysis phase."""
        payload_hash = compute_payload_hash(payload)
        ts = event_timestamp or datetime.now(timezone.utc)
        evt_id = event_id or f"evt-{uuid.uuid4().hex[:12]}"
        prov = provenance or cls.build_provenance(event_type)

        event = AuditEvent(
            event_id=evt_id,
            document_id=document_id,
            workflow_id=workflow_id,
            event_type=event_type,
            event_timestamp=ts,
            schema_version=AUDIT_SCHEMA_VERSION,
            source_phase=source_phase,
            payload_hash=payload_hash,
            previous_event_hash=previous_event_hash,
            event_hash="",
            provenance=prov,
            metadata=metadata or {},
        )
        event.event_hash = compute_event_hash(event)
        return event
