import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.models.analysis import AnalysisStatus, DocumentExtractionResult, GeminiExtractionPayload
from app.models.document import DocumentMetadata
from app.models.risk import RiskContext
from app.orchestration.adapters.base import (
    AdapterResult,
    BaseEngineAdapter,
    FailureClassification,
)
from app.risk.engine import RiskAssessmentEngine

logger = logging.getLogger(__name__)


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
        logger.info(
            f"[{self.adapter_name}] Executing risk assessment for workflow '{workflow_id}' / doc '{document_id}'"
        )
        try:
            ref_dt = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
            risk_context = RiskContext(reference_datetime=ref_dt)
            extraction_payload = GeminiExtractionPayload(
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

            result = self.engine.assess(
                extraction_result=extraction_result,
                metadata=doc_metadata,
                forensic_result=None,
                compliance_result=None,
                context=risk_context,
            )

            # High/critical risk triggers review
            if result.risk_level.value in ("CRITICAL", "HIGH"):
                return AdapterResult(
                    success=False,
                    failure_classification=FailureClassification.REQUIRES_REVIEW,
                    failure_reason=f"Risk assessment score ({result.composite_score:.2f}) indicates HIGH/CRITICAL risk.",
                    output_reference={"risk_result": result.model_dump(mode="json")},
                    observations={"risk_score": float(result.composite_score), "risk_level": result.risk_level.value},
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
            logger.error(f"[{self.adapter_name}] Unexpected error: {e}", exc_info=True)
            return AdapterResult(
                success=False,
                failure_classification=FailureClassification.RETRYABLE,
                failure_reason=f"RiskAdapter exception: {e}",
            )
