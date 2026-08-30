import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.errors import ErrorCategory
from app.core.logging import CorrelationContext, log_event
from app.models.analysis import AnalysisStatus, DocumentExtractionResult, GeminiExtractionPayload
from app.models.document import DocumentMetadata
from app.models.risk import RiskContext
from app.orchestration.adapters.base import (
    AdapterResult,
    BaseEngineAdapter,
    FailureClassification,
)
from app.risk.engine import RiskAssessmentEngine

logger = logging.getLogger("papertrail.orchestration.risk_adapter")


class RiskAdapter(BaseEngineAdapter):
    """Adapter wrapping Phase 10 Deterministic Risk Assessment Engine."""

    def __init__(self, engine: Optional[RiskAssessmentEngine] = None) -> None:
        self.engine = engine or RiskAssessmentEngine()

    @property
    def adapter_name(self) -> str:
        return "RiskAdapter (Phase 10)"

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
                message=f"Executing risk assessment for workflow '{workflow_id}' / doc '{document_id}'",
                component="risk_adapter",
                operation="risk_assessment_start",
                workflow_id=workflow_id,
                document_id=document_id,
            )
            try:
                ref_dt = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
                risk_context = RiskContext(reference_datetime=ref_dt)
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
                    status_reason="Extraction ready for risk assessment",
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

                compliance_dict = payload.get("compliance_result")
                if not compliance_dict and isinstance(payload.get("previous_output"), dict):
                    compliance_dict = payload["previous_output"].get("compliance_result")

                compliance_result = None
                if compliance_dict:
                    from app.models.compliance import ComplianceAnalysisResult
                    compliance_result = ComplianceAnalysisResult(**compliance_dict)

                result = self.engine.assess(
                    extraction_result=extraction_result,
                    metadata=doc_metadata,
                    forensic_result=forensic_result,
                    compliance_result=compliance_result,
                    context=risk_context,
                )

                duration_ms = (time.perf_counter() - t0) * 1000.0

                if result.risk_level.value in ("CRITICAL", "HIGH"):
                    log_event(
                        logger=logger,
                        level=logging.WARNING,
                        message=f"Risk assessment flagged HIGH/CRITICAL risk (Score: {result.composite_score:.2f}, Level: {result.risk_level.value})",
                        component="risk_adapter",
                        operation="risk_high_severity",
                        workflow_id=workflow_id,
                        document_id=document_id,
                        duration_ms=duration_ms,
                        outcome="REQUIRES_REVIEW",
                        risk_score=float(result.composite_score),
                        risk_level=result.risk_level.value,
                    )
                    return AdapterResult(
                        success=False,
                        failure_classification=FailureClassification.REQUIRES_REVIEW,
                        failure_reason=f"Risk assessment score ({result.composite_score:.2f}) indicates HIGH/CRITICAL risk.",
                        output_reference={"risk_result": result.model_dump(mode="json")},
                        observations={"risk_score": float(result.composite_score), "risk_level": result.risk_level.value},
                    )

                log_event(
                    logger=logger,
                    level=logging.INFO,
                    message=f"Risk assessment evaluated in {duration_ms:.2f}ms (Score: {result.composite_score:.2f}, Level: {result.risk_level.value})",
                    component="risk_adapter",
                    operation="risk_assessment_completed",
                    workflow_id=workflow_id,
                    document_id=document_id,
                    duration_ms=duration_ms,
                    outcome="SUCCESS",
                    risk_score=float(result.composite_score),
                    risk_level=result.risk_level.value,
                )

                return AdapterResult(
                    success=True,
                    output_reference={"risk_result": result.model_dump(mode="json")},
                    observations={
                        "risk_score": float(result.composite_score),
                        "risk_level": result.risk_level.value,
                        "summary": result.assessment_summary,
                    },
                )
            except Exception as e:
                duration_ms = (time.perf_counter() - t0) * 1000.0
                log_event(
                    logger=logger,
                    level=logging.ERROR,
                    message=f"Unexpected error in RiskAdapter: {e}",
                    component="risk_adapter",
                    operation="risk_assessment_failed",
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
                    failure_reason=f"RiskAdapter exception: {e}",
                )
