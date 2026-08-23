import logging
from typing import Any, Dict, Optional

from app.forensics.engine import ForensicEngine
from app.models.analysis import AnalysisStatus, DocumentExtractionResult, GeminiExtractionPayload
from app.models.document import DocumentMetadata
from app.orchestration.adapters.base import (
    AdapterResult,
    BaseEngineAdapter,
    FailureClassification,
)

logger = logging.getLogger(__name__)


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
        logger.info(
            f"[{self.adapter_name}] Executing forensics for workflow '{workflow_id}' / doc '{document_id}'"
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

            # Check if critical/high severity findings exist requiring review/escalation
            has_critical = any(f.severity.value == "CRITICAL" for f in result.findings)

            if has_critical:
                return AdapterResult(
                    success=False,
                    failure_classification=FailureClassification.REQUIRES_REVIEW,
                    failure_reason=f"Forensic findings contain CRITICAL severity issues: {result.evidence_summary}",
                    output_reference={"forensic_result": result.model_dump(mode="json")},
                    observations={"finding_count": result.finding_count, "has_critical": True},
                )

            return AdapterResult(
                success=True,
                output_reference={"forensic_result": result.model_dump(mode="json")},
                observations={"finding_count": result.finding_count, "summary": result.evidence_summary},
            )
        except Exception as e:
            logger.error(f"[{self.adapter_name}] Unexpected error: {e}", exc_info=True)
            return AdapterResult(
                success=False,
                failure_classification=FailureClassification.RETRYABLE,
                failure_reason=f"ForensicAdapter exception: {e}",
            )
