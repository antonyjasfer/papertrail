import logging
import time
from typing import Any, Dict, Optional

from app.core.errors import ErrorCategory
from app.core.logging import CorrelationContext, log_event
from app.models.analysis import (
    AnalysisStatus,
    DocumentExtractionResult,
    GeminiExtractionPayload,
    LineItem,
)
from app.orchestration.adapters.base import (
    AdapterResult,
    BaseEngineAdapter,
    FailureClassification,
)
from app.services.document_intelligence import DocumentIntelligenceService

logger = logging.getLogger("papertrail.orchestration.doc_intel_adapter")


class DocIntelAdapter(BaseEngineAdapter):
    """Adapter wrapping Phase 7 Document Intelligence Service (Ingestion & Extraction)."""

    def __init__(self, doc_service: Optional[DocumentIntelligenceService] = None) -> None:
        self.doc_service = doc_service or DocumentIntelligenceService()

    @property
    def adapter_name(self) -> str:
        return "DocIntelAdapter (Phase 7)"

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
                message=f"Executing document extraction for workflow '{workflow_id}' / doc '{document_id}'",
                component="doc_intel_adapter",
                operation="extract_document_start",
                workflow_id=workflow_id,
                document_id=document_id,
            )
            try:
                result = self.doc_service.analyze_document(document_id)
                duration_ms = (time.perf_counter() - t0) * 1000.0

                if result.status.value == "SUCCESS":
                    confidence = result.extraction.extraction_confidence if result.extraction else 1.0
                    log_event(
                        logger=logger,
                        level=logging.INFO,
                        message=f"Document extraction succeeded in {duration_ms:.2f}ms (Confidence: {confidence:.2f})",
                        component="doc_intel_adapter",
                        operation="extraction_completed",
                        workflow_id=workflow_id,
                        document_id=document_id,
                        duration_ms=duration_ms,
                        outcome="SUCCESS",
                    )
                    return AdapterResult(
                        success=True,
                        output_reference={
                            "document_id": document_id,
                            "extraction": result.extraction.model_dump(mode="json") if result.extraction else {},
                            "status_reason": result.status_reason,
                        },
                        observations={"confidence": confidence},
                    )
                elif result.status.value == "NEEDS_REVIEW":
                    log_event(
                        logger=logger,
                        level=logging.WARNING,
                        message=f"Document extraction requires review: {result.status_reason}",
                        component="doc_intel_adapter",
                        operation="extraction_needs_review",
                        workflow_id=workflow_id,
                        document_id=document_id,
                        duration_ms=duration_ms,
                        outcome="REQUIRES_REVIEW",
                        error_category=ErrorCategory.VALIDATION_ERROR.value,
                    )
                    return AdapterResult(
                        success=False,
                        failure_classification=FailureClassification.REQUIRES_REVIEW,
                        failure_reason=result.status_reason,
                        observations={"confidence": result.extraction.extraction_confidence if result.extraction else 0.0},
                    )
                else:
                    err_msg = (result.status_reason or "").lower()
                    is_transient = any(
                        term in err_msg
                        for term in ("timeout", "rate limit", "429", "503", "resource_exhausted", "quota")
                    )
                    failure_classification = (
                        FailureClassification.RETRYABLE if is_transient else FailureClassification.NON_RETRYABLE
                    )
                    log_event(
                        logger=logger,
                        level=logging.ERROR,
                        message=f"Document extraction failed ({result.status_reason})",
                        component="doc_intel_adapter",
                        operation="extraction_failed",
                        workflow_id=workflow_id,
                        document_id=document_id,
                        duration_ms=duration_ms,
                        outcome="EXTRACTION_FAILED",
                        error_category=ErrorCategory.TRANSIENT_DEPENDENCY_ERROR.value if is_transient else ErrorCategory.PERMANENT_PROCESSING_ERROR.value,
                    )
                    return AdapterResult(
                        success=False,
                        failure_classification=failure_classification,
                        failure_reason=result.status_reason or "Document extraction failed.",
                        output_reference={
                            "document_id": document_id,
                            "extraction": None,
                            "status_reason": result.status_reason,
                        },
                        observations={"confidence": 0.0},
                    )
            except Exception as e:
                duration_ms = (time.perf_counter() - t0) * 1000.0
                err_msg = str(e).lower()
                is_transient = any(
                    term in err_msg
                    for term in ("timeout", "rate limit", "429", "503", "resource_exhausted", "quota", "connection", "unavailable")
                )
                failure_classification = (
                    FailureClassification.RETRYABLE if is_transient else FailureClassification.NON_RETRYABLE
                )
                log_event(
                    logger=logger,
                    level=logging.ERROR,
                    message=f"Exception during document extraction: {e}",
                    component="doc_intel_adapter",
                    operation="extraction_exception",
                    workflow_id=workflow_id,
                    document_id=document_id,
                    duration_ms=duration_ms,
                    error_details=str(e),
                    error_category=ErrorCategory.TRANSIENT_DEPENDENCY_ERROR.value if is_transient else ErrorCategory.PERMANENT_PROCESSING_ERROR.value,
                )
                return AdapterResult(
                    success=False,
                    failure_classification=failure_classification,
                    failure_reason=f"Document extraction error: {e}",
                    output_reference={
                        "document_id": document_id,
                        "extraction": None,
                        "status_reason": str(e),
                    },
                    observations={"confidence": 0.0},
                )
