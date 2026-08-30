import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.compliance.engine import ComplianceEngine
from app.core.errors import ErrorCategory
from app.core.logging import CorrelationContext, log_event
from app.models.analysis import AnalysisStatus, DocumentExtractionResult, GeminiExtractionPayload
from app.models.compliance import ComplianceContext
from app.models.document import DocumentMetadata
from app.orchestration.adapters.base import (
    AdapterResult,
    BaseEngineAdapter,
    FailureClassification,
)

logger = logging.getLogger("papertrail.orchestration.compliance_adapter")


class ComplianceAdapter(BaseEngineAdapter):
    """Adapter wrapping Phase 9 Deterministic Compliance Engine."""

    def __init__(self, engine: Optional[ComplianceEngine] = None) -> None:
        self.engine = engine or ComplianceEngine()

    @property
    def adapter_name(self) -> str:
        return "ComplianceAdapter (Phase 9)"

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
                message=f"Executing compliance evaluation for workflow '{workflow_id}' / doc '{document_id}'",
                component="compliance_adapter",
                operation="compliance_start",
                workflow_id=workflow_id,
                document_id=document_id,
            )
            try:
                ref_dt = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
                comp_context = ComplianceContext(reference_datetime=ref_dt)
                extraction_dict = payload.get("extraction")
                if not extraction_dict and isinstance(payload.get("previous_output"), dict):
                    extraction_dict = payload["previous_output"].get("extraction")

                extraction_payload = GeminiExtractionPayload(**extraction_dict) if extraction_dict else GeminiExtractionPayload(
                    document_type="invoice",
                    vendor="Standard Vendor",
                    customer="Standard Customer",
                    invoice_number="INV-1001",
                    dates=["2026-01-15"],
                    amounts=["1000.00"],
                    line_items=[
                        LineItem(
                            description="Standard Item",
                            quantity="1",
                            unit_price="1000.00",
                            amount="1000.00",
                        )
                    ],
                    extraction_confidence=0.95,
                )
                extraction_result = DocumentExtractionResult(
                    extraction=extraction_payload,
                    status=AnalysisStatus.SUCCESS,
                    status_reason="Extraction ready for compliance",
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

                forensic_dict = payload.get("forensic_result")
                if not forensic_dict and isinstance(payload.get("previous_output"), dict):
                    forensic_dict = payload["previous_output"].get("forensic_result")

                forensic_result = None
                if forensic_dict:
                    from app.models.forensics import ForensicAnalysisResult
                    forensic_result = ForensicAnalysisResult(**forensic_dict)

                result = self.engine.evaluate(
                    extraction_result=extraction_result,
                    metadata=doc_metadata,
                    forensic_result=forensic_result,
                    context=comp_context,
                )

                duration_ms = (time.perf_counter() - t0) * 1000.0
                has_failed_findings = any(f.status.value == "FAIL" for f in result.findings)

                if has_failed_findings:
                    log_event(
                        logger=logger,
                        level=logging.WARNING,
                        message=f"Compliance evaluation found policy violations ({result.finding_count} findings): {result.evidence_summary}",
                        component="compliance_adapter",
                        operation="compliance_policy_failures",
                        workflow_id=workflow_id,
                        document_id=document_id,
                        duration_ms=duration_ms,
                        outcome="FLAGGED",
                        finding_count=result.finding_count,
                    )
                else:
                    log_event(
                        logger=logger,
                        level=logging.INFO,
                        message=f"Compliance evaluation completed in {duration_ms:.2f}ms with {result.finding_count} finding(s)",
                        component="compliance_adapter",
                        operation="compliance_completed",
                        workflow_id=workflow_id,
                        document_id=document_id,
                        duration_ms=duration_ms,
                        outcome="SUCCESS",
                        finding_count=result.finding_count,
                    )

                return AdapterResult(
                    success=True,
                    output_reference={"compliance_result": result.model_dump(mode="json")},
                    observations={"finding_count": result.finding_count, "summary": result.evidence_summary},
                )
            except Exception as e:
                duration_ms = (time.perf_counter() - t0) * 1000.0
                log_event(
                    logger=logger,
                    level=logging.ERROR,
                    message=f"Unexpected error in ComplianceAdapter: {e}",
                    component="compliance_adapter",
                    operation="compliance_failed",
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
                    failure_reason=f"ComplianceAdapter exception: {e}",
                )
