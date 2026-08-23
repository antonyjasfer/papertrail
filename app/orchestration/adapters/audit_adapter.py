import logging
from typing import Any, Dict, Optional

from app.audit.chain import AuditChainBuilder
from app.audit.constants import GENESIS_PREVIOUS_HASH
from app.audit.models import AuditEventType, AuditProvenance
from app.models.document import DocumentMetadata
from app.orchestration.adapters.base import (
    AdapterResult,
    BaseEngineAdapter,
    FailureClassification,
)

logger = logging.getLogger(__name__)


class AuditAdapter(BaseEngineAdapter):
    """Adapter wrapping Phase 11 Cryptographic Audit & Provenance Layer."""

    def __init__(self, chain_builder: Optional[AuditChainBuilder] = None) -> None:
        self.chain_builder = chain_builder or AuditChainBuilder()

    @property
    def adapter_name(self) -> str:
        return "AuditAdapter (Phase 11)"

    def execute(
        self,
        workflow_id: str,
        document_id: str,
        payload: Dict[str, Any],
    ) -> AdapterResult:
        logger.info(
            f"[{self.adapter_name}] Sealing audit chain for workflow '{workflow_id}' / doc '{document_id}'"
        )
        try:
            doc_metadata = DocumentMetadata(
                document_id=document_id,
                filename="document.pdf",
                content_type="application/pdf",
                size_bytes=1024,
                storage_bucket="papertrail-ai-documents-dev",
                storage_object=f"documents/{document_id}.pdf",
                checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            )
            # Create genesis event
            genesis_evt = AuditChainBuilder.create_genesis_event(
                document_metadata=doc_metadata,
                workflow_id=workflow_id,
            )

            # Create subsequent sealed audit event
            sealed_evt = AuditChainBuilder.create_event(
                document_id=document_id,
                workflow_id=workflow_id,
                event_type=AuditEventType.AUDIT_SEALED,
                source_phase="Phase 11",
                payload={"status": "SEALED", "chain_length": 2},
                previous_event_hash=genesis_evt.event_hash,
            )

            return AdapterResult(
                success=True,
                output_reference={
                    "sealed_hash": sealed_evt.event_hash,
                    "genesis_hash": genesis_evt.event_hash,
                    "event_count": 2,
                    "is_sealed": True,
                },
                observations={"sealed_hash": sealed_evt.event_hash, "total_events": 2},
            )
        except Exception as e:
            logger.error(f"[{self.adapter_name}] Unexpected error: {e}", exc_info=True)
            return AdapterResult(
                success=False,
                failure_classification=FailureClassification.RETRYABLE,
                failure_reason=f"AuditAdapter exception: {e}",
            )
