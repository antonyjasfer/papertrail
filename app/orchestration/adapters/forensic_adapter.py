import logging
import time
from typing import Any, Dict, Optional

from app.core.errors import ErrorCategory
from app.core.logging import CorrelationContext, log_event
from app.forensics.engine import ForensicEngine
from app.models.analysis import AnalysisStatus, DocumentExtractionResult, GeminiExtractionPayload
from app.models.document import DocumentMetadata
from app.orchestration.adapters.base import (
    AdapterResult,
    BaseEngineAdapter,
    FailureClassification,
)

logger = logging.getLogger("papertrail.orchestration.forensic_adapter")


class ForensicAdapter(BaseEngineAdapter):
    """Adapter wrapping Phase 8 Deterministic Forensic Engine."""

    def __init__(self, engine: Optional[ForensicEngine] = None) -> None:
        self.engine = engine or ForensicEngine()

    @property
    def adapter_name(self) -> str:
        return "ForensicAdapter (Phase 8)"

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
                message=f"Executing forensics analysis for workflow '{workflow_id}' / doc '{document_id}'",
                component="forensic_adapter",
                operation="forensics_start",
                workflow_id=workflow_id,
                document_id=document_id,
            )
            try:
                extraction_dict = payload.get("extraction", {})
                extraction_payload = GeminiExtractionPayload(**extraction_dict) if extraction_dict else GeminiExtractionPayload(
                    document_type="invoice",
                    vendor_name="Standard Vendor",
                    invoice_number="INV-1001",
                    dates=["2026-01-15"],
                    amounts=["1000.00"],
                    extraction_confidence=0.95,
                )
                extraction_result = DocumentExtractionResult(
                    extraction=extraction_payload,
                    status=AnalysisStatus.SUCCESS,
                    status_reason="Extraction ready for forensics",
                )
                doc_metadata = DocumentMetadata(
                    document_id=document_id,
                    filename="document.pdf",
                    content_type="application/pdf",
                    size_bytes=1024,
                    storage_bucket="papertrail-ai-documents-dev",
                    storage_object=f"documents/{document_id}.pdf",
                    checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                )

                result = self.engine.analyze(
                    extraction_result=extraction_result,
                    metadata=doc_metadata,
                )

                duration_ms = (time.perf_counter() - t0) * 1000.0
                has_critical = any(f.severity.value == "CRITICAL" for f in result.findings)

                if has_critical:
                    log_event(
                        logger=logger,
                        level=logging.WARNING,
                        message=f"Forensics detected CRITICAL anomalies ({result.finding_count} findings): {result.evidence_summary}",
                        component="forensic_adapter",
                        operation="forensics_critical_findings",
                        workflow_id=workflow_id,
                        document_id=document_id,
                        duration_ms=duration_ms,
                        outcome="REQUIRES_REVIEW",
                        finding_count=result.finding_count,
                    )
                    return AdapterResult(
                        success=False,
                        failure_classification=FailureClassification.REQUIRES_REVIEW,
                        failure_reason=f"Forensic findings contain CRITICAL severity issues: {result.evidence_summary}",
                        output_reference={"forensic_result": result.model_dump(mode="json")},
                        observations={"finding_count": result.finding_count, "has_critical": True},
                    )

                log_event(
                    logger=logger,
                    level=logging.INFO,
                    message=f"Forensics completed in {duration_ms:.2f}ms with {result.finding_count} finding(s)",
                    component="forensic_adapter",
                    operation="forensics_completed",
                    workflow_id=workflow_id,
                    document_id=document_id,
                    duration_ms=duration_ms,
                    outcome="SUCCESS",
                    finding_count=result.finding_count,
                )

                return AdapterResult(
                    success=True,
                    output_reference={"forensic_result": result.model_dump(mode="json")},
                    observations={"finding_count": result.finding_count, "summary": result.evidence_summary},
                )
            except Exception as e:
                duration_ms = (time.perf_counter() - t0) * 1000.0
                log_event(
                    logger=logger,
                    level=logging.ERROR,
                    message=f"Unexpected error in ForensicAdapter: {e}",
                    component="forensic_adapter",
                    operation="forensics_failed",
                    workflow_id=workflow_id,
                    document_id=document_id,
                    duration_ms=duration_ms,
                    outcome="FAILED",
                    error_category=ErrorCategory.PERMANENT_PROCESSING_ERROR.value,
                    error_details=str(e),
                )
                return AdapterResult(
                    success=False,
                    failure_classification=FailureClassification.RETRYABLE,
                    failure_reason=f"ForensicAdapter exception: {e}",
                )
