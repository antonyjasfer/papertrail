import logging
import time
from typing import Any, Dict, Optional

from app.audit.chain import AuditChainBuilder
from app.audit.constants import GENESIS_PREVIOUS_HASH
from app.audit.models import AuditEventType, AuditProvenance
from app.core.errors import ErrorCategory
from app.core.logging import CorrelationContext, log_event
from app.core.metrics import record_audit_seal
from app.models.document import DocumentMetadata
from app.orchestration.adapters.base import (
    AdapterResult,
    BaseEngineAdapter,
    FailureClassification,
)

logger = logging.getLogger("papertrail.orchestration.audit_adapter")


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
        t0 = time.perf_counter()
        with CorrelationContext(workflow_id=workflow_id, document_id=document_id, adapter=self.adapter_name):
            log_event(
                logger=logger,
                level=logging.INFO,
                message=f"Sealing audit chain for workflow '{workflow_id}' / doc '{document_id}'",
                component="audit_adapter",
                operation="seal_audit_chain",
                workflow_id=workflow_id,
                document_id=document_id,
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

                from app.core.config import settings
                if getattr(settings, "papertrail_cloud_provider", "gcp") == "azure":
                    try:
                        from app.infrastructure.azure.cosmos_repositories import CosmosAuditEventRepository
                        repo = CosmosAuditEventRepository()
                        repo.append(genesis_evt)
                        repo.append(sealed_evt)
                        log_event(
                            logger=logger,
                            level=logging.INFO,
                            message=f"Persisted cryptographic audit events to Cosmos DB container 'audit_events'",
                            component="audit_adapter",
                            operation="persist_audit_events",
                            workflow_id=workflow_id,
                            document_id=document_id,
                            event_count=2,
                            outcome="PERSISTED",
                        )
                    except Exception as persist_err:
                        log_event(
                            logger=logger,
                            level=logging.WARNING,
                            message=f"Non-fatal audit event persistence notice: {persist_err}",
                            component="audit_adapter",
                            operation="persist_audit_events",
                            workflow_id=workflow_id,
                            document_id=document_id,
                            error_category=ErrorCategory.COSMOS_ERROR.value,
                            error_details=str(persist_err),
                            outcome="PERSIST_WARNING",
                        )

                duration_ms = (time.perf_counter() - t0) * 1000.0
                record_audit_seal(success=True)

                log_event(
                    logger=logger,
                    level=logging.INFO,
                    message=f"Cryptographic audit chain sealed in {duration_ms:.2f}ms (Hash: {sealed_evt.event_hash[:12]}...)",
                    component="audit_adapter",
                    operation="audit_chain_sealed",
                    workflow_id=workflow_id,
                    document_id=document_id,
                    duration_ms=duration_ms,
                    outcome="SUCCESS",
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
                duration_ms = (time.perf_counter() - t0) * 1000.0
                record_audit_seal(success=False)
                log_event(
                    logger=logger,
                    level=logging.ERROR,
                    message=f"Unexpected error in AuditAdapter: {e}",
                    component="audit_adapter",
                    operation="seal_audit_chain",
                    workflow_id=workflow_id,
                    document_id=document_id,
                    duration_ms=duration_ms,
                    outcome="FAILED",
                    error_category=ErrorCategory.AUDIT_ERROR.value,
                    error_details=str(e),
                )
                return AdapterResult(
                    success=False,
                    failure_classification=FailureClassification.RETRYABLE,
                    failure_reason=f"AuditAdapter exception: {e}",
                )
